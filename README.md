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

### License

MIT License - For research and educational purposes only.
