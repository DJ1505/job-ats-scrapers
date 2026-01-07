#!/usr/bin/env python3
"""
Comeet ATS Job Scraper
Production-grade script that uses only Comeet Careers API v2.
Never scrapes HTML, never uses LinkedIn URLs/IDs.
"""

import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
COMPANY_ID = "72.008"
BASE_DOMAIN = "https://www.comeet.co"
API_BASE = f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}"
MAX_REQUESTS_PER_SECOND = 3
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter to enforce max 3 requests per second."""
    
    def __init__(self, max_per_second: float = 3.0):
        self.min_interval = 1.0 / max_per_second
        self.last_request_time = 0.0
    
    def wait(self):
        """Wait if necessary to respect rate limit."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()


class ComeetScraper:
    """Scraper for Comeet ATS using Careers API v2."""
    
    def __init__(self, company_id: str, base_domain: str, token: Optional[str] = None, company_slug: Optional[str] = None):
        self.company_id = company_id
        self.base_domain = base_domain
        self.api_base = f"{base_domain}/careers-api/2.0/company/{company_id}"
        self.rate_limiter = RateLimiter(MAX_REQUESTS_PER_SECOND)
        self.session = self._create_session()
        self.rejected_jobs = []
        self.valid_jobs = []
        self.token = token  # Can be provided or extracted automatically
        self.company_slug = company_slug or company_id.replace(".", "_")  # Default slug from company_id
    
    def _create_session(self) -> requests.Session:
        """Create a session with retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _extract_token_from_url(self, url: str) -> Optional[str]:
        """Extract token from URL query parameters."""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            token = params.get("token", [None])[0]
            return token
        except Exception:
            return None
    
    def _make_request(self, url: str, use_token: bool = True) -> Optional[Dict[str, Any]]:
        """Make HTTP request with rate limiting and error handling."""
        self.rate_limiter.wait()
        
        # Add token if available and not already in URL
        if use_token and self.token and "token=" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}token={self.token}"
        
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from {url}: {e}")
            return None
    
    def _validate_position_url(self, url: str) -> bool:
        """Validate that position_url returns HTTP 200."""
        if not url:
            return False
        
        self.rate_limiter.wait()
        
        try:
            # Use GET instead of HEAD as some APIs don't support HEAD properly
            # Also ensure token is in URL if we have it
            if self.token and "token=" not in url:
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}token={self.token}"
            
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            # Accept 200-299 range as valid
            return 200 <= response.status_code < 300
        except requests.exceptions.RequestException:
            return False
    
    def _extract_location_string(self, location_obj: Optional[Dict]) -> str:
        """Extract location string from nested location object."""
        if not location_obj:
            return "Remote"
        
        city = location_obj.get("city", "")
        country = location_obj.get("country", "")
        
        parts = [p for p in [city, country] if p]
        return ", ".join(parts) if parts else "Remote"
    
    def _extract_description_from_details(self, details: List[Dict]) -> tuple[str, str]:
        """Extract description and requirements from details array."""
        description_html = ""
        requirements_html = ""
        
        for detail in details:
            detail_name = detail.get("name", "")
            detail_value = detail.get("value", "")
            
            if detail_name == "Description":
                description_html = detail_value
            elif detail_name == "Requirements":
                requirements_html = detail_value
        
        return description_html, requirements_html
    
    def _should_reject_job(self, job_data: Dict[str, Any]) -> tuple[bool, str]:
        """Check if job should be rejected based on filtering rules."""
        # Reject if uid is missing
        uid = job_data.get("uid")
        if not uid:
            return True, "Missing uid"
        
        # Reject if position_url is missing or non-200
        position_url = job_data.get("position_url")
        if not position_url:
            return True, "Missing position_url"
        
        if not self._validate_position_url(position_url):
            return True, "position_url returns non-200 status"
        
        # Reject if details[] does NOT contain "Description"
        # Note: If details is not in the response, we'll still process the job
        # but mark description as missing (the API may not always return details)
        details = job_data.get("details", [])
        if details:  # Only check if details array exists
            has_description = any(
                detail.get("name") == "Description" 
                for detail in details
            )
            if not has_description:
                return True, "details[] does not contain 'Description'"
        # If no details array, we'll still process but job_description_raw will be None
        
        # Reject if job title contains "General application"
        title = job_data.get("name", "")
        if "General application" in title:
            return True, "Title contains 'General application'"
        
        return False, ""
    
    def _transform_job(self, job_data: Dict[str, Any], company_slug: str) -> Optional[Dict[str, Any]]:
        """Transform job data to match ats_jobs schema."""
        uid = job_data.get("uid")
        name = job_data.get("name", "")
        department = job_data.get("department", "")
        location_obj = job_data.get("location")
        employment_type = job_data.get("employment_type", "")
        experience_level = job_data.get("experience_level", "")
        position_url = job_data.get("position_url", "")
        details = job_data.get("details", [])
        time_updated = job_data.get("time_updated")
        company_name = job_data.get("company_name", "")
        workplace_type = job_data.get("workplace_type", "")
        categories = job_data.get("categories", [])
        
        # Extract description and requirements from details
        description_html, requirements_html = self._extract_description_from_details(details)
        
        # Combine description and requirements for job_description_raw
        job_description_raw = ""
        if description_html:
            job_description_raw = description_html
        if requirements_html:
            if job_description_raw:
                job_description_raw += "\n\n" + requirements_html
            else:
                job_description_raw = requirements_html
        
        # Parse location
        city = location_obj.get("city") if location_obj else None
        state = location_obj.get("state") if location_obj else None
        country = location_obj.get("country") if location_obj else None
        postal_code = location_obj.get("postal_code") if location_obj else None
        
        # Build location string
        location_parts = []
        if city:
            location_parts.append(city)
        if state:
            location_parts.append(state)
        if country:
            location_parts.append(country)
        job_location = ", ".join(location_parts) if location_parts else None
        
        # Map workplace_type to work_location_type
        work_location_type_map = {
            "Remote": "remote",
            "Hybrid": "hybrid",
            "On-site": "on-site",
        }
        work_location_type = work_location_type_map.get(workplace_type, "not_specified")
        
        # Parse time_updated
        updated_date = None
        if time_updated:
            try:
                updated_date = datetime.fromisoformat(time_updated.replace('Z', '+00:00'))
            except:
                pass
        
        # Extract job_function from categories
        job_function = None
        for cat in categories:
            if cat.get("name") == "Function":
                job_function = cat.get("value")
                break
        
        # Build raw_data JSONB
        raw_data = {
            "uid": uid,
            "name": name,
            "department": department,
            "employment_type": employment_type,
            "experience_level": experience_level,
            "workplace_type": workplace_type,
            "categories": categories,
            "details": details,
            "location": location_obj,
            "position_url": position_url,
            "time_updated": time_updated,
        }
        
        return {
            "ats_source": "Comeet",
            "company_slug": company_slug,
            "job_id": uid,
            "job_title": name,
            "job_url": job_data.get("url_active_page") or job_data.get("url_comeet_hosted_page") or position_url,
            "apply_url": position_url,
            "job_description_raw": job_description_raw if job_description_raw else None,
            "job_description_cleaned": None,  # Will be processed later
            "published_date": None,  # Not available in API
            "updated_date": updated_date.isoformat() if updated_date else None,
            "job_location": job_location,
            "city": city,
            "state": state,
            "country": country,
            "postal_code": postal_code,
            "work_location_type": work_location_type,
            "experience_level": experience_level,
            "employment_type": employment_type,
            "job_function": job_function,
            "company_name": company_name,
            "raw_data": raw_data,
            "processing_status": "scraped",
            "job_status": "active"
        }
    
    def _get_token_from_careers_page(self) -> Optional[str]:
        """Try to extract token from company's public careers page."""
        # Try common careers page URLs
        careers_urls = [
            f"{self.base_domain}/jobs/{self.company_id}",
            f"{self.base_domain}/careers-api/2.0/company/{self.company_id}",
        ]
        
        import re
        for url in careers_urls:
            try:
                self.rate_limiter.wait()
                response = self.session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                if response.status_code == 200:
                    html = response.text
                    # Look for token in JavaScript/API calls
                    token_match = re.search(r'token=([A-F0-9]{32})', html, re.IGNORECASE)
                    if token_match:
                        return token_match.group(1)
            except Exception:
                continue
        return None
    
    def fetch_job_list(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch list of all job positions."""
        # Try to get token from careers page if not already set
        if not self.token:
            logger.info("Attempting to extract token from careers page...")
            self.token = self._get_token_from_careers_page()
            if self.token:
                logger.info("Successfully extracted token from careers page")
            else:
                logger.warning("Could not extract token automatically. API may require manual token.")
        
        url = f"{self.api_base}/positions"
        logger.info(f"Fetching job list from {url}")
        
        data = self._make_request(url, use_token=True)
        if not data:
            return None
        
        # API may return data in "data" array or directly as a list
        if isinstance(data, list):
            positions = data
        else:
            positions = data.get("data", [])
        
        # Extract token from first position_url if available (fallback)
        if positions and not self.token:
            first_position = positions[0]
            position_url = first_position.get("position_url", "")
            if position_url:
                self.token = self._extract_token_from_url(position_url)
                if self.token:
                    logger.info("Extracted token from API response")
        
        logger.info(f"Found {len(positions)} positions")
        return positions
    
    def fetch_job_details(self, uid: str) -> Optional[Dict[str, Any]]:
        """Fetch detailed information for a specific job."""
        url = f"{self.api_base}/positions/{uid}"
        logger.debug(f"Fetching job details for {uid}")
        
        return self._make_request(url, use_token=True)
    
    def scrape(self) -> List[Dict[str, Any]]:
        """Main scraping method."""
        logger.info("Starting Comeet job scraping...")
        
        # Fetch job list
        positions = self.fetch_job_list()
        if not positions:
            logger.error("Failed to fetch job list")
            return []
        
        # Deduplicate by uid
        seen_uids = set()
        unique_positions = []
        for pos in positions:
            uid = pos.get("uid")
            if uid and uid not in seen_uids:
                seen_uids.add(uid)
                unique_positions.append(pos)
        
        logger.info(f"Processing {len(unique_positions)} unique jobs")
        
        # Process each job
        for idx, position in enumerate(unique_positions, 1):
            uid = position.get("uid")
            logger.info(f"Processing job {idx}/{len(unique_positions)}: {uid}")
            
            # The list endpoint already returns complete job data with details
            # Only fetch individual details if list data seems incomplete
            job_data = position
            
            # Optionally fetch individual details for verification (but list usually has everything)
            # Individual fetch might return different structure, so use list data as primary
            individual_data = self.fetch_job_details(uid)
            if individual_data:
                # If individual fetch returns a dict (not list), use it
                if isinstance(individual_data, dict) and individual_data.get("uid") == uid:
                    # Merge individual data, but prefer list data for details
                    job_data = {**individual_data, **position}
                elif isinstance(individual_data, list) and len(individual_data) > 0:
                    # If it returns a list, take first item
                    job_data = individual_data[0]
            
            # Check if job should be rejected
            should_reject, reason = self._should_reject_job(job_data)
            if should_reject:
                self.rejected_jobs.append({
                    "uid": uid,
                    "title": job_data.get("name", ""),
                    "reason": reason
                })
                logger.warning(f"Rejected job {uid}: {reason}")
                continue
            
            # Transform and add to valid jobs
            transformed_job = self._transform_job(job_data, self.company_slug)
            if transformed_job:
                self.valid_jobs.append(transformed_job)
                logger.info(f"Valid job added: {transformed_job['job_title']}")
        
        return self.valid_jobs
    
    def print_summary(self):
        """Print final summary of scraping results."""
        total_fetched = len(self.valid_jobs) + len(self.rejected_jobs)
        total_valid = len(self.valid_jobs)
        total_rejected = len(self.rejected_jobs)
        
        print("\n" + "="*60)
        print("SCRAPING SUMMARY")
        print("="*60)
        print(f"Total fetched: {total_fetched}")
        print(f"Total valid jobs: {total_valid}")
        print(f"Rejected: {total_rejected}")
        
        if self.rejected_jobs:
            print("\nRejection reasons:")
            rejection_reasons = defaultdict(int)
            for job in self.rejected_jobs:
                rejection_reasons[job["reason"]] += 1
            
            for reason, count in rejection_reasons.items():
                print(f"  - {reason}: {count}")
        
        print("="*60 + "\n")


def main():
    """Main entry point."""
    # Token can be provided via environment variable or will be extracted automatically
    import os
    token = os.environ.get("COMEET_TOKEN")
    company_slug = os.environ.get("COMPANY_SLUG", "zim")  # Default to 'zim' for company 72.008
    
    scraper = ComeetScraper(COMPANY_ID, BASE_DOMAIN, token=token, company_slug=company_slug)
    jobs = scraper.scrape()
    
    # Print summary
    scraper.print_summary()
    
    # Output JSON
    output = json.dumps(jobs, indent=2, ensure_ascii=False)
    print(output)
    
    return jobs


if __name__ == "__main__":
    main()

