# BOUN Course Scraper

This tool scrapes course schedule data from the Boğaziçi University registration website and saves it as a structured JSON file.
This file is used for Kılıç Baran's Course Planner and its forks.

## Requirements

- Google Chrome or Mozilla Firefox installed
- Python installed

## Installation

1. Clone this repository:
```bash
    git clone https://github.com/mil3ri/boun_course_scraper.git
    cd boun_course_scraper
```

2. Install dependencies:

```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use `.venv\Scripts\activate`
    pip install -r requirements.txt
```

## Usage

Run the scraper from the command line:

```bash
python boun_course_scraper.py
python boun_course_scraper.py --nogui # For headless mode
```

- The script will fetch available semesters from the website.
- You will be prompted to select a semester by number.
- The script will scrape all department schedules for the selected semester and save the results as a JSON file named after the semester (e.g., `2024-2025-2.json`).
