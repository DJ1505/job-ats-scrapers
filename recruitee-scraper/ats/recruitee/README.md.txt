# Recruitee ATS Scraper

## What this does
Scrapes job listings from companies using **Recruitee ATS**
using internal JSON APIs (no HTML scraping).

## How it works (simple)
1. Calls Recruitee jobs API
2. Fetches paginated job listings
3. Normalizes data using schema
4. Saves output as JSON

## How to run
```bash
python ats/recruitee/scraper.py
