"""
Production-grade Recruitee ATS scraper using Playwright with network-first strategy.

Uses network interception to capture JSON API responses instead of DOM scraping.
"""
import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from playwright.async_api import async_playwright, Page, Response, Route, Request
from pydantic import ValidationError

from schemas import NormalizedJob, Location, Department

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class NetworkCapture:
    """Stores captured network responses."""
    offers_list: Optional[dict] = None
    offer_details: dict = field(default_factory=dict)
    api_base_url: Optional[str] = None


class RecruiteeScraper:
    """
    Recruitee ATS scraper using network interception.
    
    Captures JSON API responses directly instead of parsing DOM.
    """
    
    # Known Recruitee API patterns
    OFFERS_LIST_PATTERN = re.compile(r"/api/offers/?(\?.*)?$")
    OFFER_DETAIL_PATTERN = re.compile(r"/api/offers/([^/\?]+)(\?.*)?$")
    
    def __init__(self, company_slug: str, headless: bool = True, timeout: int = 30000):
        """
        Initialize the scraper.
        
        Args:
            company_slug: The Recruitee company subdomain (e.g., 'acme' for acme.recruitee.com)
            headless: Run browser in headless mode
            timeout: Default timeout in milliseconds
        """
        self.company_slug = company_slug
        self.headless = headless
        self.timeout = timeout
        self.base_url = f"https://{company_slug}.recruitee.com"
        self.api_base = f"{self.base_url}/api"
        self.capture = NetworkCapture()
        self._page: Optional[Page] = None
        self._http_client: Optional[httpx.AsyncClient] = None
    
    async def _handle_response(self, response: Response) -> None:
        """
        Handle intercepted network responses.
        
        Captures JSON API responses for offers list and details.
        """
        url = response.url
        
        # Skip non-API responses
        if "/api/" not in url:
            return
        
        # Skip non-successful responses
        if response.status < 200 or response.status >= 300:
            logger.debug(f"Skipping non-success response: {url} ({response.status})")
            return
        
        try:
            # Check content type
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return
            
            # Parse JSON
            body = await response.json()
            
            # Match against known patterns
            if self.OFFERS_LIST_PATTERN.search(url):
                logger.info(f"Captured offers list from: {url}")
                self.capture.offers_list = body
                self.capture.api_base_url = url.split("/api/")[0] + "/api"
            
            elif match := self.OFFER_DETAIL_PATTERN.search(url):
                offer_slug = match.group(1)
                logger.info(f"Captured offer detail for: {offer_slug}")
                self.capture.offer_details[offer_slug] = body
                
        except Exception as e:
            logger.debug(f"Error processing response {url}: {e}")
    
    async def _check_for_blocking(self, page: Page) -> bool:
        """
        Check for CAPTCHA, login walls, or other blocking mechanisms.
        
        Returns True if blocked, False otherwise.
        """
        url = page.url.lower()
        
        # Check for common blocking indicators in URL
        blocking_patterns = ["captcha", "login", "signin", "auth", "challenge"]
        if any(pattern in url for pattern in blocking_patterns):
            logger.warning(f"Potential blocking detected in URL: {url}")
            return True
        
        return False
    
    async def _fetch_api_direct(self, endpoint: str) -> Optional[dict]:
        """
        Fetch from API using httpx client (bypasses browser).
        
        This is a fallback when browser-based fetch fails.
        """
        url = f"{self.api_base}/{endpoint}".rstrip("/") + "/"
        logger.debug(f"Fetching via httpx: {url}")
        
        try:
            if not self._http_client:
                self._http_client = httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=self.timeout / 1000,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    }
                )
            
            response = await self._http_client.get(url)
            if response.status_code == 200:
                return response.json()
            else:
                logger.debug(f"HTTP {response.status_code} from {url}")
                return None
        except Exception as e:
            logger.debug(f"httpx error for {url}: {e}")
            return None
    
    async def _fetch_offer_detail_direct(self, offer_slug: str) -> Optional[dict]:
        """
        Fetch offer detail directly via API call.
        
        Tries browser context first, falls back to httpx.
        """
        endpoint = f"offers/{offer_slug}" if offer_slug else "offers"
        api_url = f"{self.api_base}/{endpoint}".rstrip("/")
        if not offer_slug:
            api_url += "/"
        
        logger.info(f"Fetching: {api_url}")
        
        # Try browser-based fetch first (preserves cookies/session)
        if self._page:
            try:
                result = await self._page.evaluate(
                    """async (url) => {
                        try {
                            const response = await fetch(url, {
                                method: 'GET',
                                headers: { 'Accept': 'application/json' }
                            });
                            if (!response.ok) {
                                return { error: response.status };
                            }
                            return await response.json();
                        } catch (e) {
                            return { error: e.message };
                        }
                    }""",
                    api_url
                )
                
                if isinstance(result, dict) and "error" not in result:
                    return result
                    
                logger.debug(f"Browser fetch failed: {result.get('error', 'unknown')}")
            except Exception as e:
                logger.debug(f"Browser fetch exception: {e}")
        
        # Fallback to httpx
        return await self._fetch_api_direct(endpoint)
    
    def _normalize_job(self, raw_offer: dict, from_detail: bool = False) -> Optional[NormalizedJob]:
        """
        Normalize raw Recruitee offer data to standard schema.
        
        Args:
            raw_offer: Raw offer data from API
            from_detail: Whether this is from detail endpoint (has more fields)
        """
        try:
            # Extract offer data - detail endpoint wraps in 'offer' key
            offer = raw_offer.get("offer", raw_offer) if from_detail else raw_offer
            
            # Parse locations
            locations = []
            for loc in offer.get("locations", []):
                locations.append(Location(
                    city=loc.get("city"),
                    country=loc.get("country"),
                    country_code=loc.get("country_code"),
                    region=loc.get("region"),
                ))
            
            # Check remote option
            remote_option = offer.get("remote")
            if remote_option:
                # Add remote as a location indicator
                for loc in locations:
                    loc.remote = True
            
            # Parse department - can be dict or string
            department = None
            if dept := offer.get("department"):
                if isinstance(dept, dict):
                    department = Department(
                        id=dept.get("id"),
                        name=dept.get("name")
                    )
                elif isinstance(dept, str):
                    department = Department(name=dept)
            
            # Parse dates - handles formats like "2025-01-02 14:22:42 UTC" and ISO format
            def parse_date(date_str: str) -> Optional[datetime]:
                if not date_str:
                    return None
                try:
                    # Try ISO format first
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    pass
                try:
                    # Try "YYYY-MM-DD HH:MM:SS UTC" format
                    return datetime.strptime(date_str.replace(" UTC", ""), "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass
                return None
            
            created_at = parse_date(offer.get("created_at"))
            published_at = parse_date(offer.get("published_at"))
            
            # Build careers and apply URLs
            offer_slug = offer.get("slug", "")
            careers_url = f"{self.base_url}/o/{offer_slug}" if offer_slug else None
            apply_url = offer.get("careers_apply_url") or (f"{careers_url}/c/new" if careers_url else None)
            
            # Extract salary info if available
            salary_min = offer.get("min_salary")
            salary_max = offer.get("max_salary")
            salary_currency = offer.get("salary_currency")
            
            return NormalizedJob(
                id=offer.get("id"),
                slug=offer_slug,
                title=offer.get("title", ""),
                description=offer.get("description"),
                requirements=offer.get("requirements"),
                department=department,
                locations=locations,
                employment_type=offer.get("employment_type_code"),
                experience_level=offer.get("experience_code"),
                education_level=offer.get("education_code"),
                remote_option=remote_option,
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency=salary_currency,
                created_at=created_at,
                published_at=published_at,
                careers_url=careers_url,
                apply_url=apply_url,
                company_slug=self.company_slug,
                raw_data=offer if from_detail else None
            )
            
        except (ValidationError, KeyError, TypeError) as e:
            logger.error(f"Failed to normalize offer: {e}")
            return None
    
    async def scrape(self, fetch_details: bool = True) -> list[NormalizedJob]:
        """
        Scrape all jobs from the Recruitee careers site.
        
        Args:
            fetch_details: Whether to fetch full details for each job
            
        Returns:
            List of normalized job data
        """
        jobs: list[NormalizedJob] = []
        
        async with async_playwright() as p:
            # Launch browser
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            self._page = await context.new_page()
            self._page.set_default_timeout(self.timeout)
            
            # Set up network interception
            self._page.on("response", self._handle_response)
            
            try:
                # Navigate to careers page - this should trigger API calls
                logger.info(f"Navigating to {self.base_url}")
                await self._page.goto(self.base_url, wait_until="networkidle")
                
                # Check for blocking
                if await self._check_for_blocking(self._page):
                    logger.error("Blocked by CAPTCHA or login wall. Aborting.")
                    await browser.close()
                    return jobs
                
                # Wait a bit for any lazy-loaded API calls
                await self._page.wait_for_timeout(1000)
                
                # If we didn't capture the offers list via network, try direct API call
                if not self.capture.offers_list:
                    logger.info("Offers list not captured via network, trying direct API call")
                    self.capture.offers_list = await self._fetch_offer_detail_direct("")
                    # The direct call to /api/offers/ returns the list
                    if not self.capture.offers_list:
                        # Try the base offers endpoint
                        result = await self._page.evaluate(
                            """async (url) => {
                                try {
                                    const response = await fetch(url, {
                                        method: 'GET',
                                        headers: { 'Accept': 'application/json' }
                                    });
                                    if (!response.ok) return null;
                                    return await response.json();
                                } catch (e) {
                                    return null;
                                }
                            }""",
                            f"{self.api_base}/offers/"
                        )
                        self.capture.offers_list = result
                
                if not self.capture.offers_list:
                    logger.error("Failed to capture offers list")
                    await browser.close()
                    return jobs
                
                # Extract offers from the list response
                offers = self.capture.offers_list.get("offers", [])
                logger.info(f"Found {len(offers)} job offers")
                
                if fetch_details:
                    # Fetch details for each offer
                    for offer in offers:
                        offer_slug = offer.get("slug")
                        if not offer_slug:
                            continue
                        
                        # Check if we already captured this detail
                        if offer_slug not in self.capture.offer_details:
                            detail = await self._fetch_offer_detail_direct(offer_slug)
                            if detail:
                                self.capture.offer_details[offer_slug] = detail
                        
                        # Normalize the job data
                        detail_data = self.capture.offer_details.get(offer_slug)
                        if detail_data:
                            normalized = self._normalize_job(detail_data, from_detail=True)
                        else:
                            # Fall back to list data
                            normalized = self._normalize_job(offer, from_detail=False)
                        
                        if normalized:
                            jobs.append(normalized)
                else:
                    # Just normalize from list data
                    for offer in offers:
                        normalized = self._normalize_job(offer, from_detail=False)
                        if normalized:
                            jobs.append(normalized)
                
            except Exception as e:
                logger.error(f"Scraping failed: {e}")
                raise
            finally:
                await browser.close()
                if self._http_client:
                    await self._http_client.aclose()
                    self._http_client = None
        
        logger.info(f"Successfully scraped {len(jobs)} jobs")
        return jobs


async def main():
    """Example usage of the scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape jobs from Recruitee ATS")
    parser.add_argument("company_slug", help="Recruitee company subdomain (e.g., 'acme' for acme.recruitee.com)")
    parser.add_argument("--no-details", action="store_true", help="Skip fetching job details")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--timeout", type=int, default=30000, help="Timeout in milliseconds")
    
    args = parser.parse_args()
    
    scraper = RecruiteeScraper(
        company_slug=args.company_slug,
        headless=not args.visible,
        timeout=args.timeout
    )
    
    jobs = await scraper.scrape(fetch_details=not args.no_details)
    
    # Output results
    output_data = [job.model_dump(mode="json") for job in jobs]
    
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Results written to {args.output}")
    else:
        print(json.dumps(output_data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
