# LinkedIn Job Duplication Research Tool

A production-grade Playwright Python script that researches whether LinkedIn jobs are duplicates from company career pages/ATS systems or exclusive to LinkedIn.

## Purpose

Extract LinkedIn jobs **without login**, **without brittle HTML scraping**, and with **minimal browser interaction** — while correctly handling ATS-based companies and LinkedIn-only startups.

## Architecture

### API-First Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                    Job Ingestion Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. LINKEDIN DISCOVERY (Network Interception)                   │
│     └── Guest APIs: /jobs-guest/jobs/api/*, /voyager/api/*     │
│                                                                  │
│  2. JOB CLASSIFICATION                                          │
│     ├── ATS Jobs (external apply URL) → Fetch from ATS API     │
│     └── LinkedIn-Native (Easy Apply) → Accept as final         │
│                                                                  │
│  3. ATS INGESTION (JSON APIs - No Browser)                      │
│     ├── Greenhouse API                                          │
│     ├── Lever API                                               │
│     ├── Workday API                                             │
│     ├── Ashby API                                               │
│     └── SmartRecruiters API                                     │
│                                                                  │
│  4. DEDUPLICATION & NORMALIZATION                               │
│     └── Unified job schema with job_origin classification       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

- **LinkedIn Guest APIs** are the PRIMARY data source
- **No DOM scraping** for job data (only for triggering API calls)
- **Immediate abort** on authwall/login/captcha detection
- **Rate limiting** between requests
- **ATS JSON APIs** are source of truth for ATS companies

## Job Origin Classification

Every job is classified as:

| Origin | Description | Handling |
|--------|-------------|----------|
| `ATS` | External apply URL redirects to ATS | Fetch from ATS JSON API |
| `LINKEDIN_NATIVE` | Easy Apply or no external URL | Accept LinkedIn API data |

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## Usage

```bash
# Basic search
python main.py --keywords "software engineer" --location "San Francisco"

# More jobs
python main.py --keywords "data scientist" --max-jobs 30

# Skip ATS fetching (LinkedIn only)
python main.py --keywords "product manager" --no-ats

# Debug mode (visible browser)
python main.py --no-headless
```

## Output Schema

Each extracted job includes:

```json
{
  "job_id": "12345",
  "title": "Software Engineer",
  "company_name": "Tech Corp",
  "location": "San Francisco, CA",
  "apply_url": "https://boards.greenhouse.io/techcorp/jobs/12345",
  "ats_provider": "greenhouse",
  "job_origin": "ATS",
  "source_url": "https://linkedin.com/jobs/view/12345",
  "extracted_at": "2024-01-15T10:30:00Z",
  "extraction_method": "ats_api"
}
```

## Safety Controls

| Control | Implementation |
|---------|---------------|
| No Login | Guest APIs only |
| No Cookies | No credential storage |
| Block Detection | Immediate abort on authwall/captcha |
| Rate Limiting | 2000ms between requests |
| Headless Mode | Default for stealth |
| Minimal Navigation | Search page only |

## Supported ATS Providers

| Provider | API Support | Detection Pattern |
|----------|-------------|-------------------|
| Greenhouse | ✅ JSON API | `boards.greenhouse.io` |
| Lever | ✅ JSON API | `jobs.lever.co` |
| Workday | ✅ JSON API | `*.myworkdayjobs.com` |
| Ashby | ✅ JSON API | `jobs.ashbyhq.com` |
| SmartRecruiters | ✅ JSON API | `jobs.smartrecruiters.com` |
| iCIMS | Network only | `*.icims.com` |
| Taleo | Network only | `*.taleo.net` |
| BambooHR | Network only | `*.bamboohr.com` |
| Jobvite | Network only | `*.jobvite.com` |

## Test Cases

Run tests with:
```bash
python -m pytest test_pipeline.py -v
```

| Test | Description |
|------|-------------|
| ATS (Greenhouse) | Jobs fetched via JSON API, marked as ATS |
| ATS (Workday) | Network interception captures API |
| LinkedIn-Native | Easy Apply accepted, no external scraping |
| Block Detection | Authwall/captcha triggers immediate stop |
| Mixed Companies | ATS + LinkedIn-native handled correctly |

## Project Structure

```
├── main.py                 # CLI entry point
├── job_pipeline.py         # Pipeline orchestrator
├── linkedin_scraper.py     # LinkedIn network interception
├── ats_scraper.py          # ATS scraping (API-first)
├── ats_clients.py          # JSON API clients
├── ats_detector.py         # ATS provider detection
├── network_interceptor.py  # Network capture + block detection
├── schemas.py              # Pydantic data models
├── job_comparator.py       # Duplicate detection
├── test_pipeline.py        # Test cases
└── requirements.txt        # Dependencies
```

## Troubleshooting

**No jobs found:**
- LinkedIn may be blocking automated requests
- Try `--no-headless` to see what's happening
- Wait and retry later

**Block detected:**
- The tool stops immediately on authwall/captcha
- Partial results are preserved
- Wait before retrying

## License

MIT License - For research and educational purposes only.
