# Job ATS Scrapers

Production-ready job scrapers for multiple ATS using JSON APIs

## Available Scrapers

### LinkedIn Job Duplication Research Tool

A production-grade Playwright Python script that researches whether LinkedIn jobs are duplicates from company career pages/ATS systems or exclusive to LinkedIn.

**Location:** `LinkedIn-scraper/`

**Key Features:**
- Network interception for LinkedIn API responses
- ATS detection for Workday, Greenhouse, Lever, iCIMS, Taleo, etc.
- Career page scraping with duplicate detection
- Rich reporting (JSON, CSV, console output)

**Quick Start:**
```bash
cd LinkedIn-scraper
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python main.py --keywords "software engineer" --max-jobs 10
```

**Research Finding:** LinkedIn jobs are NOT exclusive - they originate from company ATS systems and are syndicated to LinkedIn.

For detailed documentation, see: [LinkedIn-scraper/README.md](LinkedIn-scraper/README.md)

---

### SmartRecruiter ATS Scraper

Production-grade SmartRecruiter ATS scraper with API-first approach and DOM scraping fallback. Built to work like the Workday Scraper with full ATS job schema compliance.

**Location:** `smartrecruiter/`

**Key Features:**
- API-first approach with SmartRecruiter's public API
- DOM scraping fallback for failed API calls
- Pattern-based CSS selectors (45+ patterns)
- Full ATS job schema compliance (60+ fields)
- Workday-style interface compatibility
- Pagination and quality assessment
- AI processing metadata and confidence scoring

**Quick Start:**
```bash
cd smartrecruiter
pip install -r requirements.txt
playwright install
python scraper.py smartrecruiters --max-pages 3 --output jobs.json
```

**Example Usage:**
```python
from scraper import SmartRecruiterScraper

async def scrape_jobs():
    scraper = SmartRecruiterScraper('company_identifier')
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=5)
    
    if result['success']:
        print(f"Found {result['total_jobs']} jobs")
        for job in result['jobs']:
            print(f"Title: {job['job_title']}")
            print(f"Location: {job['job_location']}")

import asyncio
asyncio.run(scrape_jobs())
```

For detailed documentation, see: [smartrecruiter/README.md](smartrecruiter/README.md)

---

### License

MIT License - For research and educational purposes only.
