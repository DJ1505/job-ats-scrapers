"""
Universal LinkedIn Job Scraper
==============================
A ready-to-use scraper for LinkedIn jobs that works with:
- Company URLs (e.g., linkedin.com/jobs/search/?f_C=1283)
- Direct job URLs with embedded job IDs
- Company pages (e.g., linkedin.com/company/infosys)
- Keyword searches

Features:
- Extracts full job details (title, description, requirements, etc.)
- Filters out inactive/closed jobs automatically
- Exports to JSON and CSV formats
- Rate limiting to avoid blocks

Usage:
    python linkedin_scraper.py --url "https://www.linkedin.com/jobs/search/?f_C=1283"
    python linkedin_scraper.py --company 1283 --max-jobs 50
    python linkedin_scraper.py --keywords "Python Developer" --location "India"
    python linkedin_scraper.py --job-ids 4323740671,4360099992,4323369504
"""

import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict, field
from typing import List, Optional
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote
import json
import csv
import time
import re
import argparse
import sys


@dataclass
class Job:
    """Data class representing a LinkedIn job posting"""
    job_id: str
    title: str
    company: str
    location: str
    linkedin_url: str
    posted_time: str
    description: Optional[str] = None
    description_html: Optional[str] = None
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    salary: Optional[str] = None
    applicants: Optional[str] = None
    is_active: bool = True
    job_state: Optional[str] = None
    scraped_at: str = ""
    
    def __post_init__(self):
        if not self.scraped_at:
            self.scraped_at = datetime.now().isoformat()


class LinkedInScraper:
    """
    Universal LinkedIn Job Scraper
    
    Supports multiple input methods:
    - URL with company filter (f_C parameter)
    - URL with embedded job IDs (originToLandingJobPostings)
    - Direct company ID
    - Keyword search
    - List of job IDs
    """
    
    SEARCH_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    JOB_DETAIL_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
    SEARCH_PAGE = "https://www.linkedin.com/jobs/search"
    
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    
    INACTIVE_INDICATORS = [
        "no longer accepting applications",
        "this job is no longer available",
        "job has been filled",
        "position has been filled",
        "job posting has expired",
        "this position is closed",
        "no longer active",
        "applications are closed",
        "job closed",
        "posting closed",
    ]
    
    def __init__(self, delay: float = 1.0, filter_inactive: bool = True):
        """
        Initialize the scraper
        
        Args:
            delay: Seconds to wait between requests (default: 1.0)
            filter_inactive: Whether to filter out inactive jobs (default: True)
        """
        self.delay = delay
        self.filter_inactive = filter_inactive
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
    
    # =========================================================================
    # Main Entry Points
    # =========================================================================
    
    def scrape_from_url(self, url: str, max_jobs: int = 100) -> List[Job]:
        """
        Scrape jobs from any LinkedIn URL
        
        Automatically detects the URL type and uses the appropriate method.
        
        Args:
            url: LinkedIn URL (search page, company page, or job listing)
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List of Job objects
        """
        print(f"\nAnalyzing URL: {url[:80]}...")
        
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        
        # Method 1: URL contains explicit job IDs
        if "originToLandingJobPostings" in params:
            job_ids_str = params["originToLandingJobPostings"][0]
            job_ids = [jid.strip() for jid in unquote(job_ids_str).split(",") if jid.strip()]
            print(f"Found {len(job_ids)} job IDs embedded in URL")
            return self.scrape_job_ids(job_ids[:max_jobs])
        
        # Method 2: URL has company filter
        if "f_C" in params:
            company_id = params["f_C"][0]
            geo_id = params.get("geoId", ["92000000"])[0]
            print(f"Found company filter: {company_id}")
            return self.scrape_company(company_id, geo_id, max_jobs)
        
        # Method 3: URL is a company page
        if "/company/" in url:
            company_slug = url.split("/company/")[1].split("/")[0].split("?")[0]
            print(f"Company page detected: {company_slug}")
            print("Note: Company pages require finding the company ID first.")
            print("Please use the jobs search URL instead (with f_C parameter).")
            return []
        
        # Method 4: URL has a current job ID - fetch that job
        if "currentJobId" in params:
            job_id = params["currentJobId"][0]
            print(f"Found current job ID: {job_id}")
            jobs = self.scrape_job_ids([job_id])
            
            # Also try to get more jobs from search
            if "f_C" not in params:
                print("Attempting to find more jobs from search...")
                additional = self._search_jobs_from_page(url, max_jobs - 1)
                for job in additional:
                    if job.job_id != job_id:
                        jobs.append(job)
            return jobs[:max_jobs]
        
        # Method 5: General search URL
        print("General search URL detected, extracting jobs...")
        return self._search_jobs_from_page(url, max_jobs)
    
    def scrape_company(self, company_id: str, geo_id: str = "92000000", max_jobs: int = 100) -> List[Job]:
        """
        Scrape jobs for a specific company by ID
        
        Args:
            company_id: LinkedIn company ID (e.g., "1283" for Infosys)
            geo_id: Geographic region ID (default: "92000000" for Worldwide)
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List of Job objects
        """
        print(f"\nScraping jobs for company ID: {company_id}")
        print(f"Region: {'Worldwide' if geo_id == '92000000' else geo_id}")
        print(f"Max jobs: {max_jobs}")
        
        job_ids = self._collect_job_ids_from_search(company_id, geo_id, max_jobs)
        
        if not job_ids:
            print("No jobs found via search API")
            return []
        
        return self.scrape_job_ids(job_ids)
    
    def scrape_keywords(self, keywords: str, location: str = "", max_jobs: int = 100) -> List[Job]:
        """
        Scrape jobs by keyword search
        
        Args:
            keywords: Search keywords (e.g., "Python Developer")
            location: Location filter (e.g., "India", "New York")
            max_jobs: Maximum number of jobs to scrape
            
        Returns:
            List of Job objects
        """
        print(f"\nSearching for: {keywords}")
        if location:
            print(f"Location: {location}")
        print(f"Max jobs: {max_jobs}")
        
        job_ids = self._collect_job_ids_by_keywords(keywords, location, max_jobs)
        
        if not job_ids:
            print("No jobs found")
            return []
        
        return self.scrape_job_ids(job_ids)
    
    def scrape_job_ids(self, job_ids: List[str]) -> List[Job]:
        """
        Scrape jobs by their IDs
        
        Args:
            job_ids: List of LinkedIn job IDs
            
        Returns:
            List of Job objects
        """
        jobs = []
        inactive_count = 0
        
        print(f"\nFetching details for {len(job_ids)} jobs...")
        print(f"Filter: {'Active jobs only' if self.filter_inactive else 'All jobs'}")
        
        for i, job_id in enumerate(job_ids, 1):
            print(f"  [{i}/{len(job_ids)}] Fetching job {job_id}...", end=" ")
            
            job = self._fetch_job_details(job_id)
            
            if job is None:
                print("[SKIPPED - inactive/unavailable]")
                inactive_count += 1
            elif not job.is_active and self.filter_inactive:
                print(f"[CLOSED] {job.title[:40]}...")
                inactive_count += 1
            else:
                status = "[ACTIVE]" if job.is_active else "[CLOSED]"
                print(f"{status} {job.title[:40]}...")
                jobs.append(job)
            
            if i < len(job_ids):
                time.sleep(self.delay)
        
        print(f"\nSummary: {len(jobs)} active jobs, {inactive_count} inactive/skipped")
        return jobs
    
    # =========================================================================
    # Internal Methods - Job ID Collection
    # =========================================================================
    
    def _collect_job_ids_from_search(self, company_id: str, geo_id: str, max_jobs: int) -> List[str]:
        """Collect job IDs from company search"""
        job_ids = []
        start = 0
        
        while len(job_ids) < max_jobs:
            params = {
                "f_C": company_id,
                "geoId": geo_id,
                "start": start
            }
            
            print(f"  Fetching search results (start={start})...", end=" ")
            
            try:
                # Try search API first
                response = self.session.get(self.SEARCH_API, params=params, timeout=30)
                
                if response.status_code != 200:
                    print(f"HTTP {response.status_code}")
                    break
                
                page_ids = self._extract_job_ids_from_html(response.text)
                
                if not page_ids:
                    # Try the main search page
                    response = self.session.get(self.SEARCH_PAGE, params=params, timeout=30)
                    if response.status_code == 200:
                        page_ids = self._extract_job_ids_from_html(response.text)
                
                if not page_ids:
                    print("No more jobs")
                    break
                
                # Add unique IDs
                new_ids = [jid for jid in page_ids if jid not in job_ids]
                job_ids.extend(new_ids)
                print(f"Found {len(new_ids)} new jobs (total: {len(job_ids)})")
                
                start += 25
                time.sleep(self.delay)
                
                if start >= 975:  # LinkedIn limit
                    print("  Reached LinkedIn pagination limit")
                    break
                    
            except Exception as e:
                print(f"Error: {e}")
                break
        
        return job_ids[:max_jobs]
    
    def _collect_job_ids_by_keywords(self, keywords: str, location: str, max_jobs: int) -> List[str]:
        """Collect job IDs from keyword search"""
        job_ids = []
        start = 0
        
        while len(job_ids) < max_jobs:
            params = {
                "keywords": keywords,
                "start": start
            }
            if location:
                params["location"] = location
            
            print(f"  Fetching search results (start={start})...", end=" ")
            
            try:
                response = self.session.get(self.SEARCH_API, params=params, timeout=30)
                
                if response.status_code != 200:
                    print(f"HTTP {response.status_code}")
                    break
                
                page_ids = self._extract_job_ids_from_html(response.text)
                
                if not page_ids:
                    print("No more jobs")
                    break
                
                new_ids = [jid for jid in page_ids if jid not in job_ids]
                job_ids.extend(new_ids)
                print(f"Found {len(new_ids)} new jobs (total: {len(job_ids)})")
                
                start += 25
                time.sleep(self.delay)
                
                if start >= 975:
                    break
                    
            except Exception as e:
                print(f"Error: {e}")
                break
        
        return job_ids[:max_jobs]
    
    def _search_jobs_from_page(self, url: str, max_jobs: int) -> List[Job]:
        """Extract jobs from a search page URL"""
        job_ids = []
        
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                job_ids = self._extract_job_ids_from_html(response.text)
        except Exception as e:
            print(f"Error fetching page: {e}")
        
        if not job_ids:
            return []
        
        return self.scrape_job_ids(job_ids[:max_jobs])
    
    def _extract_job_ids_from_html(self, html: str) -> List[str]:
        """Extract job IDs from HTML content"""
        job_ids = []
        soup = BeautifulSoup(html, "lxml")
        
        # Method 1: data-entity-urn attributes
        cards = soup.find_all(attrs={"data-entity-urn": lambda x: x and "jobPosting" in str(x)})
        for card in cards:
            urn = card.get("data-entity-urn", "")
            match = re.search(r':(\d+)$', urn)
            if match and match.group(1) not in job_ids:
                job_ids.append(match.group(1))
        
        # Method 2: /jobs/view/ links
        links = soup.find_all("a", href=lambda x: x and "/jobs/view/" in str(x))
        for link in links:
            href = link.get("href", "")
            match = re.search(r'/jobs/view/(\d+)', href)
            if match and match.group(1) not in job_ids:
                job_ids.append(match.group(1))
        
        return job_ids
    
    # =========================================================================
    # Internal Methods - Job Details
    # =========================================================================
    
    def _fetch_job_details(self, job_id: str) -> Optional[Job]:
        """Fetch full details for a single job"""
        url = self.JOB_DETAIL_API.format(job_id=job_id)
        
        try:
            response = self.session.get(url, timeout=30)
            
            # 404 means job doesn't exist
            if response.status_code == 404:
                return None
            
            if response.status_code != 200:
                return None
            
            html = response.text
            
            # Check for inactive indicators
            is_active = True
            job_state = "LISTED"
            html_lower = html.lower()
            
            for indicator in self.INACTIVE_INDICATORS:
                if indicator in html_lower:
                    is_active = False
                    job_state = "CLOSED"
                    break
            
            # Parse HTML
            soup = BeautifulSoup(html, "lxml")
            
            # Check for closed banner
            closed_banner = soup.find(class_=lambda x: x and "closed" in str(x).lower())
            if closed_banner:
                is_active = False
                job_state = "CLOSED"
            
            # Check data-job-state attribute
            state_elem = soup.find(attrs={"data-job-state": True})
            if state_elem:
                job_state = state_elem.get("data-job-state", job_state)
                if job_state.upper() in ["CLOSED", "EXPIRED", "FILLED"]:
                    is_active = False
            
            # Skip if filtering inactive and job is inactive
            if self.filter_inactive and not is_active:
                return None
            
            # Extract job details
            title = self._extract_text(soup, "h1", "top-card-layout__title") or \
                    self._extract_text(soup, "h2", "top-card-layout__title") or "Unknown"
            
            company = self._extract_text(soup, "a", "topcard__org-name-link") or \
                      self._extract_text(soup, "span", "topcard__flavor") or "Unknown"
            
            location = self._extract_text(soup, "span", "topcard__flavor--bullet") or \
                       self._extract_text(soup, "span", "topcard__flavor") or "Unknown"
            
            posted_time = self._extract_text(soup, "span", "posted-time-ago__text") or \
                          self._extract_text(soup, "span", "topcard__flavor--metadata") or "Unknown"
            
            # Description
            desc_elem = soup.find("div", class_="description__text")
            description = desc_elem.get_text(separator="\n", strip=True) if desc_elem else None
            description_html = str(desc_elem) if desc_elem else None
            
            # Job criteria
            criteria = {}
            criteria_items = soup.find_all("li", class_="description__job-criteria-item")
            for item in criteria_items:
                header = item.find("h3")
                value = item.find("span", class_="description__job-criteria-text")
                if header and value:
                    key = header.get_text(strip=True).lower()
                    criteria[key] = value.get_text(strip=True)
            
            employment_type = criteria.get("employment type")
            experience_level = criteria.get("seniority level")
            
            # Salary
            salary_elem = soup.find("div", class_="salary-main-rail__data-body") or \
                          soup.find(class_=lambda x: x and "compensation" in str(x).lower())
            salary = salary_elem.get_text(strip=True) if salary_elem else None
            
            # Applicants
            applicants_elem = soup.find("span", class_="num-applicants__caption") or \
                              soup.find(class_=lambda x: x and "applicant" in str(x).lower())
            applicants = applicants_elem.get_text(strip=True) if applicants_elem else None
            
            return Job(
                job_id=job_id,
                title=title.strip(),
                company=company.strip(),
                location=location.strip(),
                linkedin_url=f"https://www.linkedin.com/jobs/view/{job_id}/",
                posted_time=posted_time.strip(),
                description=description,
                description_html=description_html,
                employment_type=employment_type,
                experience_level=experience_level,
                salary=salary,
                applicants=applicants,
                is_active=is_active,
                job_state=job_state
            )
            
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def _extract_text(self, soup: BeautifulSoup, tag: str, class_name: str) -> Optional[str]:
        """Helper to extract text from an element"""
        elem = soup.find(tag, class_=class_name)
        return elem.get_text(strip=True) if elem else None


# =============================================================================
# Export Functions
# =============================================================================

def export_to_json(jobs: List[Job], filename: str) -> str:
    """Export jobs to JSON file"""
    if not filename.endswith('.json'):
        filename += '.json'
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump([asdict(job) for job in jobs], f, indent=2, ensure_ascii=False)
    
    print(f"Exported to {filename}")
    return filename


def export_to_csv(jobs: List[Job], filename: str) -> str:
    """Export jobs to CSV file"""
    if not filename.endswith('.csv'):
        filename += '.csv'
    
    if not jobs:
        print("No jobs to export")
        return filename
    
    # Priority field order
    priority_fields = [
        "job_id", "title", "company", "location", "is_active", "job_state",
        "posted_time", "employment_type", "experience_level", "salary",
        "applicants", "linkedin_url", "description", "scraped_at"
    ]
    
    # Get all fields
    all_fields = list(asdict(jobs[0]).keys())
    fieldnames = [f for f in priority_fields if f in all_fields]
    fieldnames.extend([f for f in all_fields if f not in fieldnames and f != "description_html"])
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for job in jobs:
            row = asdict(job)
            row.pop("description_html", None)  # Skip HTML in CSV
            writer.writerow(row)
    
    print(f"Exported to {filename}")
    return filename


def export_jobs(jobs: List[Job], base_filename: str) -> tuple:
    """Export jobs to both JSON and CSV"""
    json_file = export_to_json(jobs, base_filename)
    csv_file = export_to_csv(jobs, base_filename)
    return json_file, csv_file


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Universal LinkedIn Job Scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape from a LinkedIn URL
  python linkedin_scraper.py --url "https://www.linkedin.com/jobs/search/?f_C=1283"
  
  # Scrape by company ID
  python linkedin_scraper.py --company 1283 --max-jobs 50
  
  # Scrape by keywords
  python linkedin_scraper.py --keywords "Python Developer" --location "India"
  
  # Scrape specific job IDs
  python linkedin_scraper.py --job-ids 4323740671,4360099992
  
  # Include inactive jobs
  python linkedin_scraper.py --url "..." --include-inactive
  
  # Custom output filename
  python linkedin_scraper.py --url "..." --output my_jobs
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--url", "-u", help="LinkedIn URL to scrape")
    input_group.add_argument("--company", "-c", help="LinkedIn company ID")
    input_group.add_argument("--keywords", "-k", help="Search keywords")
    input_group.add_argument("--job-ids", "-j", help="Comma-separated job IDs")
    
    # Additional options
    parser.add_argument("--location", "-l", help="Location filter (for keyword search)")
    parser.add_argument("--max-jobs", "-m", type=int, default=50, help="Maximum jobs to scrape (default: 50)")
    parser.add_argument("--delay", "-d", type=float, default=1.0, help="Delay between requests in seconds (default: 1.0)")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive/closed jobs")
    parser.add_argument("--output", "-o", help="Output filename (without extension)")
    parser.add_argument("--json-only", action="store_true", help="Export only JSON (skip CSV)")
    parser.add_argument("--csv-only", action="store_true", help="Export only CSV (skip JSON)")
    
    args = parser.parse_args()
    
    # Initialize scraper
    scraper = LinkedInScraper(
        delay=args.delay,
        filter_inactive=not args.include_inactive
    )
    
    # Run scraper based on input type
    print("=" * 70)
    print("LinkedIn Job Scraper")
    print("=" * 70)
    
    jobs = []
    
    if args.url:
        jobs = scraper.scrape_from_url(args.url, args.max_jobs)
    elif args.company:
        jobs = scraper.scrape_company(args.company, max_jobs=args.max_jobs)
    elif args.keywords:
        jobs = scraper.scrape_keywords(args.keywords, args.location or "", args.max_jobs)
    elif args.job_ids:
        job_ids = [jid.strip() for jid in args.job_ids.split(",")]
        jobs = scraper.scrape_job_ids(job_ids)
    
    # Export results
    if jobs:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = args.output or f"linkedin_jobs_{timestamp}"
        
        print("\n" + "=" * 70)
        print(f"Scraping Complete! Found {len(jobs)} jobs")
        print("=" * 70)
        
        if args.json_only:
            export_to_json(jobs, base_filename)
        elif args.csv_only:
            export_to_csv(jobs, base_filename)
        else:
            export_jobs(jobs, base_filename)
        
        # Print summary
        print("\nJob Summary:")
        print("-" * 50)
        for i, job in enumerate(jobs[:10], 1):
            print(f"{i}. {job.title[:45]}")
            print(f"   {job.company} | {job.location}")
        
        if len(jobs) > 10:
            print(f"\n... and {len(jobs) - 10} more jobs")
    else:
        print("\nNo jobs found.")
    
    return jobs


if __name__ == "__main__":
    main()
