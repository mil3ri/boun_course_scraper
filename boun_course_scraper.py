import json
import argparse
from selenium import webdriver
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager
import time as pytime
import re
import os

# --- Helper Functions for Parsing ---

def parse_credits(credit_str):
    """Safely parses a string into an integer for credits."""
    try:
        return int(credit_str)
    except (ValueError, TypeError):
        return 0

def parse_ects(ects_str):
    """Safely parses a string into a float for ECTS."""
    try:
        return float(ects_str)
    except (ValueError, TypeError):
        return 0.0

def parse_list_of_strings(s):
    """Splits a newline-separated string into a list of non-empty strings."""
    if not s or not s.strip():
        return []
    return [item for item in s.strip().split('\n') if item]

def parse_days(days_str):
    """
    Parses a string like 'WWWThThTh' into ['W', 'W', 'W', 'Th', 'Th', 'Th'].
    """
    if not days_str or not days_str.strip():
        return []
    # Match 'Th' and 'W', 'M', 'F', etc.
    pattern = r'(Th|W|M|F|T|S)'
    return re.findall(pattern, days_str.strip())

def parse_hours(hours_str):
    """
    Parses a string like '12391011' into ['1', '2', '3', '9', '10', '11'].
    Only '10' and '11' are valid two-digit hours; all others are single digits.
    """
    if not hours_str or not hours_str.strip():
        return []
    pattern = r'(10|11|[1-9])'
    return re.findall(pattern, hours_str.strip())

# --- WebDriver Setup ---

def get_webdriver(headless=False):
    """
    Tries to initialize Chrome WebDriver, falls back to Firefox if Chrome is unavailable.
    Returns (driver, browser_name) or (None, None) if both fail.
    """
    # Try Chrome first
    chrome_options = webdriver.ChromeOptions()
    if headless:
        chrome_options.add_argument('--headless')
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Using Chrome WebDriver.")
        return driver, "chrome"
    except Exception as e:
        print(f"Chrome WebDriver not available: {e}")

    # Fallback to Firefox
    firefox_options = webdriver.FirefoxOptions()
    if headless:
        firefox_options.add_argument('-headless')
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=firefox_options)
        print("Using Firefox WebDriver.")
        return driver, "firefox"
    except Exception as e:
        print(f"Firefox WebDriver not available: {e}")

    print("Neither Chrome nor Firefox WebDriver could be initialized.")
    return None, None

# --- Main Scraping Logic ---

def scrape_boun_schedule(semester, headless=False):
    """
    Scrapes the course schedule for a given semester from the BOUN registration site.
    """
    driver, browser_name = get_webdriver(headless)
    if not driver:
        print("Please ensure you have Chrome or Firefox and their drivers installed.")
        return {}

    results = {}
    base_url = "https://registration.bogazici.edu.tr/buis/general/"
    
    try:
        driver.get(base_url + "schedule.aspx?p=semester")
        wait = WebDriverWait(driver, 30)

        # Wait for loading overlay to disappear before interacting
        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "grec-loading-container")))

        # Select the semester
        select = Select(wait.until(EC.presence_of_element_located((By.ID, "ctl00_cphMainContent_ddlSemester"))))
        select.select_by_value(semester)
        
        # Click the search button
        wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "grec-loading-container")))
        driver.find_element(By.ID, "ctl00_cphMainContent_btnSearch").click()

        # Get all department links
        department_links_elements = wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, "//a[contains(@href, '/scripts/sch.asp?donem=')]")
        ))
        department_urls = [link.get_attribute('href') for link in department_links_elements]

        print(f"Found {len(department_urls)} department schedules to scrape.")

        last_course_key = None

        for url in department_urls:
            driver.get(url)
            try:
                # Wait up to 5 seconds for the table to appear, else skip
                try:
                    table = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "table[border='1']"))
                    )
                except Exception:
                    print(f"Skipping department {url} (no table found after 3 seconds).")
                    continue

                rows = table.find_elements(By.TAG_NAME, "tr")[1:]  # Skip header row
                
                dept_code_match = re.search(r"kisaadi=([A-Z]+)", url)
                dept_code = dept_code_match.group(1) if dept_code_match else "UNKNOWN"
                print(f"Scraping department: {dept_code} - {len(rows)} lessons found.")

                for row in rows:
                    cols = [td for td in row.find_elements(By.TAG_NAME, "td")]
                    
                    if len(cols) < 10:
                        continue
                    
                    course_code_raw = cols[0].text.strip()

                    # Handle multi-line course entries
                    if not course_code_raw and last_course_key and last_course_key in results:
                        # Days, Hours, Rooms handling for multi-line
                        if cols[7].text.strip():
                            results[last_course_key]["days"].extend(parse_days(cols[7].text))
                        if cols[8].text.strip():
                            results[last_course_key]["hours"].extend(parse_hours(cols[8].text))
                        # Rooms logic
                        room_cell = cols[9]
                        room_text = room_cell.text.strip()
                        # Check for "Online" in the cell
                        if "Online" in room_text:
                            results[last_course_key]["rooms"].extend(["Online"])
                        elif room_text:
                            results[last_course_key]["rooms"].extend(parse_list_of_strings(room_text))
                        else:
                            # Try to extract from <span> tags if present
                            spans = room_cell.find_elements(By.TAG_NAME, "span")
                            if spans:
                                results[last_course_key]["rooms"].extend([span.text.strip() for span in spans if span.text.strip()])
                        continue

                    if not course_code_raw:
                        continue

                    # This is a new course entry
                    course_name_raw = cols[2].text.strip()
                    section_part = cols[1].text.strip().replace(" ", "")
                    unique_key = course_code_raw.replace(" ", "")

                    # Create a more unique key for labs/ps to avoid overwriting
                    if "LAB" in course_name_raw.upper() or "P.S." in course_name_raw.upper():
                        if section_part:
                            unique_key = f"{unique_key}.{section_part}"

                    last_course_key = unique_key
                    
                    course_data = {
                        "code": course_code_raw,
                        "name": course_name_raw,
                        "credits": parse_credits(cols[3].text.strip()),
                        "ects": parse_ects(cols[4].text.strip()),
                        "instructor": cols[6].text.strip(),
                    }

                    # Add optional fields only if they contain data
                    if cols[5].text.strip():
                        course_data["requiredForDept"] = parse_list_of_strings(cols[5].text)
                    if cols[7].text.strip():
                        course_data["days"] = parse_days(cols[7].text)
                    if cols[8].text.strip():
                        course_data["hours"] = parse_hours(cols[8].text)
                    
                    # Rooms logic
                    room_cell = cols[9]
                    room_text = room_cell.text.strip()
                    if "Online" in room_text:
                        course_data["rooms"] = ["Online"]
                    elif room_text:
                        course_data["rooms"] = parse_list_of_strings(room_text)
                    else:
                        # Try to extract from <span> tags if present
                        spans = room_cell.find_elements(By.TAG_NAME, "span")
                        if spans:
                            course_data["rooms"] = [span.text.strip() for span in spans if span.text.strip()]
                        else:
                            course_data["rooms"] = ["N/A"]
                    
                    results[unique_key] = course_data
            
            except Exception as e:
                print(f"Could not process department {dept_code}. Error: {e}")
                continue
    
    finally:
        driver.quit()

    return results

def save_json(data, semester):
    """
    Saves the scraped data to a JSON file in the 'data' folder, sorted alphabetically by course code.
    """
    if not data:
        print("No data was scraped. JSON file will not be created.")
        return

    # Ensure the 'data' directory exists
    os.makedirs("data", exist_ok=True)
    filename = os.path.join("data", f"{semester.replace('/', '-')}.json")

    # Sort the dictionary by its keys (course codes) before saving
    sorted_data = dict(sorted(data.items()))

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(sorted_data, f, ensure_ascii=False, indent=4)

    print(f"\nSuccessfully saved {len(data)} course sections to {filename}")

def fetch_semesters_from_website(headless=False):
    """
    Fetches the list of available semesters from the website.
    """
    driver, browser_name = get_webdriver(headless)
    if not driver:
        print("Please ensure you have Chrome or Firefox and their drivers installed.")
        return []
        
    semesters = []
    try:
        driver.get("https://registration.bogazici.edu.tr/buis/general/schedule.aspx?p=semester")
        select = Select(driver.find_element(By.ID, "ctl00_cphMainContent_ddlSemester"))
        for option in select.options:
            if option.get_attribute("value"):
                semesters.append(option.get_attribute("value"))
    finally:
        driver.quit()
    return semesters

def prompt_semester(semesters):
    """
    Prompts the user to select a semester from the available list.
    Pressing 0 will quit the application.
    """
    if not semesters:
        print("Could not fetch the semester list.")
        return None
        
    print("\nAvailable semesters:")
    for idx, sem in enumerate(reversed(semesters)):
        print(f"{len(semesters) - idx}. {sem}")
        
    while True:
        choice = input("Select a semester by number (or 0 to quit): ")
        if choice == "0":
            print("Quitting application.")
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(semesters):
                return semesters[idx]
        except ValueError:
            pass
        print("Invalid selection. Please enter a number from the list or 0 to quit.")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Scrape BOUN course schedule to a structured JSON file.")
    parser.add_argument('--nogui', action='store_true', help="Run in headless mode (no browser GUI).")
    args = parser.parse_args()

    # Step 1: Get the list of semesters
    semesters = fetch_semesters_from_website(headless=args.nogui)
    
    # Step 2: Have the user choose one
    selected_semester = prompt_semester(semesters)
    
    if selected_semester:
        # Step 3: Scrape the data for the chosen semester
        print(f"\nStarting to scrape data for semester: {selected_semester}...")
        data = scrape_boun_schedule(selected_semester, headless=args.nogui)
        
        # Step 4: Save the data to a JSON file
        save_json(data, selected_semester)