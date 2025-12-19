# Recruitee ATS Scraper

Production-grade Playwright scraper for Recruitee ATS using a **network-first strategy**.

## Features

- **Network interception** - Captures JSON API responses directly instead of DOM scraping
- **Schema-first extraction** - Uses Pydantic models for data validation and normalization
- **Defensive design** - Handles blocking detection (CAPTCHA/login walls)
- **Headless by default** - Runs without visible browser window
- **Modular architecture** - Easy to extend and maintain

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

### Command Line

```bash
# Basic usage - scrape all jobs with details
python scraper.py acme

# Output to JSON file
python scraper.py acme -o jobs.json

# Skip fetching individual job details (faster, less data)
python scraper.py acme --no-details

# Run with visible browser (for debugging)
python scraper.py acme --visible

# Custom timeout (milliseconds)
python scraper.py acme --timeout 60000
```

### As a Module

```python
import asyncio
from scraper import RecruiteeScraper

async def main():
    scraper = RecruiteeScraper(
        company_slug="acme",  # for acme.recruitee.com
        headless=True,
        timeout=30000
    )
    
    jobs = await scraper.scrape(fetch_details=True)
    
    for job in jobs:
        print(f"{job.title} - {job.careers_url}")
        print(f"  Department: {job.department.name if job.department else 'N/A'}")
        print(f"  Locations: {[loc.city for loc in job.locations]}")

asyncio.run(main())
```

## Output Schema

Each job is normalized to the following structure:

```json
{
  "id": 12345,
  "slug": "software-engineer",
  "title": "Software Engineer",
  "description": "<html>...",
  "requirements": "<html>...",
  "department": {
    "id": 1,
    "name": "Engineering"
  },
  "locations": [
    {
      "city": "New York",
      "country": "United States",
      "country_code": "US",
      "region": "NY",
      "remote": false
    }
  ],
  "employment_type": "full_time",
  "experience_level": "mid_senior",
  "education_level": null,
  "remote_option": "hybrid",
  "salary_min": 100000,
  "salary_max": 150000,
  "salary_currency": "USD",
  "created_at": "2024-01-15T10:30:00+00:00",
  "published_at": "2024-01-16T08:00:00+00:00",
  "careers_url": "https://acme.recruitee.com/o/software-engineer",
  "apply_url": "https://acme.recruitee.com/o/software-engineer/c/new",
  "company_slug": "acme"
}
```

## How It Works

1. **Launches Playwright** in headless Chromium mode
2. **Sets up network interception** to capture all XHR/fetch responses
3. **Navigates to careers page** which triggers the Recruitee API
4. **Captures JSON responses** from `/api/offers/` (job list) and `/api/offers/{slug}` (job details)
5. **Falls back to direct API calls** if network interception misses any data
6. **Normalizes data** using Pydantic schemas
7. **Outputs structured JSON** with all job information

## API Endpoints Used

- `GET https://{slug}.recruitee.com/api/offers/` - List all published jobs
- `GET https://{slug}.recruitee.com/api/offers/{job_slug}` - Get job details

These are public Careers Site API endpoints that don't require authentication.

## Error Handling

- Detects CAPTCHA and login walls, stops gracefully
- Validates all data through Pydantic schemas
- Logs warnings for malformed data without crashing
- Respects robots.txt (uses standard browser behavior)

## License

MIT
