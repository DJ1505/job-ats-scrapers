# LinkedIn Job Duplication Research Tool

A production-grade Playwright Python script that researches whether LinkedIn jobs are duplicates from company career pages/ATS systems or exclusive to LinkedIn.

## Purpose

This tool helps answer the question: **Are LinkedIn job postings mostly duplicates from company career pages/ATS, or are they LinkedIn-exclusive?**

Based on research findings:
- LinkedIn has two job types: **Basic Jobs** (free, aggregated from ATS/career pages) and **Promoted Jobs** (paid)
- Most LinkedIn jobs come from external sources via API integrations or XML feeds
- This tool empirically verifies this by comparing LinkedIn listings with company career pages

## Features

- **Network Interception**: Captures LinkedIn API responses instead of brittle DOM scraping
- **ATS Detection**: Identifies Greenhouse, Lever, Workday, iCIMS, Taleo, and more
- **Career Page Scraping**: Extracts jobs from detected ATS providers
- **Fuzzy Matching**: Compares job titles and descriptions to detect duplicates
- **Defensive Design**: Handles login walls, captchas, and dynamic content
- **Rich Reporting**: JSON, CSV, and summary outputs with console visualization

## Installation

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Usage

```bash
# Basic usage
python main.py --keywords "software engineer" --max-jobs 10

# With location filter
python main.py --keywords "data scientist" --location "New York" --max-jobs 20

# Debug mode (visible browser)
python main.py --keywords "product manager" --no-headless

# Custom output directory
python main.py --keywords "devops" --output-dir my_results
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--keywords` | Job search keywords | "software engineer" |
| `--location` | Location filter | "" (any) |
| `--max-jobs` | Maximum jobs to analyze | 10 |
| `--no-headless` | Show browser window | False |
| `--output-dir` | Output directory | "results" |

## Output Files

The tool generates three output files in the results directory:

1. **research_report_TIMESTAMP.json** - Full structured report
2. **jobs_analysis_TIMESTAMP.csv** - Tabular job data for spreadsheet analysis
3. **summary_TIMESTAMP.txt** - Human-readable summary

## Architecture

```
linkedin-job-research/
├── main.py              # Entry point and CLI
├── schemas.py           # Pydantic data models
├── linkedin_scraper.py  # LinkedIn job extraction
├── career_page_scraper.py  # ATS/career page extraction
├── job_comparator.py    # Duplicate detection logic
├── ats_detector.py      # ATS provider detection
├── network_interceptor.py  # API response capture
└── requirements.txt     # Dependencies
```

## ATS Providers Detected

- Workday
- Greenhouse
- Lever
- iCIMS
- Taleo/Oracle
- BambooHR
- Jobvite
- SmartRecruiters
- Ashby

## Important Notes

1. **Respect robots.txt**: This tool is for research purposes only
2. **Rate Limiting**: LinkedIn may block requests if too aggressive
3. **Login Walls**: The tool uses guest/public APIs when possible
4. **Captcha Detection**: Stops automatically when captcha is detected

## Expected Results

Based on industry data, you should typically see:
- **70-90%** of jobs with external apply URLs (pointing to ATS/career pages)
- **High duplication rates** for jobs with external apply
- **Lower duplication** for Easy Apply jobs (may still exist on career pages)

## Troubleshooting

**No jobs found:**
- LinkedIn may be blocking automated requests
- Try `--no-headless` to see what's happening
- Wait and retry later

**Career page scraping fails:**
- Some ATS providers have anti-bot protection
- The tool gracefully skips failed pages

**Low duplication rate:**
- Career pages may have different job counts
- Title variations may affect matching
- Some companies post LinkedIn-exclusive jobs

## License

MIT License - For research and educational purposes only.
