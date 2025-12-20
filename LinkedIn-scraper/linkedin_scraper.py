"""LinkedIn job data extraction using Playwright with network interception.

ARCHITECTURE: API-FIRST, ZERO-LOGIN
- Uses network interception as the PRIMARY data source
- NO DOM scraping for job data (only for triggering API calls)
- Immediately aborts on authwall/login/captcha detection
- Rate limiting between requests
"""
import asyncio
import hashlib
import re
from datetime import datetime
from typing import AsyncGenerator, Callable
from urllib.parse import urlencode
from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright
from rich.console import Console

from schemas import JobPosting, JobSource, JobOrigin, ATSProvider, ScraperState, BlockReason
from network_interceptor import (
    InterceptedData,
    setup_network_interception,
    extract_jobs_from_api_response,
    extract_apply_url_from_job,
    detect_block_from_url,
)
from ats_detector import detect_ats_from_url

console = Console()


class LinkedInScraper:
    """
    Production-grade LinkedIn job scraper using PURE network interception.
    
    Key principles:
    - API responses are the source of truth
    - No DOM scraping for job data
    - Minimal page interactions (search page only)
    - Immediate abort on block detection
    - Rate limiting between requests
    """
    
    LINKEDIN_JOBS_SEARCH = "https://www.linkedin.com/jobs/search"
    LINKEDIN_GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    DEFAULT_RATE_LIMIT_MS = 2000
    MAX_RETRIES = 2
    
    def __init__(
        self,
        headless: bool = True,
        rate_limit_ms: int = DEFAULT_RATE_LIMIT_MS,
    ):
        self.headless = headless
        self.rate_limit_ms = rate_limit_ms
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.intercepted = InterceptedData()
        self.state = ScraperState()
        self._on_block: Callable[[BlockReason], None] | None = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self) -> None:
        """Initialize browser and context with safe defaults."""
        self._playwright = await async_playwright().start()
        self.browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            java_script_enabled=True,
        )
        self.state = ScraperState()
        self.intercepted.clear()
    
    async def close(self) -> None:
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self._playwright:
            await self._playwright.stop()
    
    def set_block_callback(self, callback: Callable[[BlockReason], None]) -> None:
        """Set callback for when block is detected."""
        self._on_block = callback
    
    def _handle_block(self, reason: BlockReason) -> None:
        """Handle block detection."""
        self.state.is_blocked = True
        self.state.block_reason = reason
        console.print(f"[red bold]BLOCKED: {reason.value}[/red bold]")
        if self._on_block:
            self._on_block(reason)
    
    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.rate_limit_ms > 0:
            await asyncio.sleep(self.rate_limit_ms / 1000)
    
    async def _check_page_blocked(self, page: Page) -> bool:
        """Check if current page indicates a block."""
        block_reason = detect_block_from_url(page.url)
        if block_reason:
            self._handle_block(block_reason)
            return True
        return False
    
    async def search_jobs(
        self,
        keywords: str = "",
        location: str = "",
        max_jobs: int = 25,
    ) -> AsyncGenerator[JobPosting, None]:
        """
        Search LinkedIn jobs using network interception.
        
        This method:
        1. Navigates to search page to trigger API calls
        2. Captures job data from network responses
        3. Does NOT scrape DOM for job data
        4. Immediately stops on block detection
        """
        if not self.context:
            raise RuntimeError("Scraper not initialized. Use 'async with' or call start()")
        
        if self.state.is_blocked:
            console.print("[red]Scraper is blocked. Cannot continue.[/red]")
            return
        
        page = await self.context.new_page()
        
        await setup_network_interception(
            page,
            self.intercepted,
            self.state,
            on_block_detected=self._handle_block,
        )
        
        try:
            params = {}
            if keywords:
                params["keywords"] = keywords
            if location:
                params["location"] = location
            params["position"] = "1"
            params["pageNum"] = "0"
            
            search_url = f"{self.LINKEDIN_JOBS_SEARCH}?{urlencode(params)}"
            console.print(f"[blue]Navigating to search page...[/blue]")
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            
            if await self._check_page_blocked(page):
                return
            
            await self._wait_for_api_responses(page, timeout_ms=15000)
            
            if self.state.is_blocked:
                return
            
            jobs_yielded = 0
            seen_job_ids: set[str] = set()
            
            for api_response in self.intercepted.jobs_api_responses:
                if jobs_yielded >= max_jobs or self.state.is_blocked:
                    break
                
                api_jobs = extract_jobs_from_api_response(api_response.get("data", {}))
                
                for job_data in api_jobs:
                    if jobs_yielded >= max_jobs or self.state.is_blocked:
                        break
                    
                    job = self._parse_api_job(job_data)
                    if job and job.job_id not in seen_job_ids:
                        seen_job_ids.add(job.job_id)
                        jobs_yielded += 1
                        self.state.jobs_collected += 1
                        yield job
            
            console.print(f"[green]Extracted {jobs_yielded} jobs from API responses[/green]")
            
            if jobs_yielded < max_jobs and not self.state.is_blocked:
                async for job in self._fetch_more_jobs(page, max_jobs - jobs_yielded, seen_job_ids, params):
                    yield job
        
        finally:
            await page.close()
    
    async def _wait_for_api_responses(self, page: Page, timeout_ms: int = 10000) -> None:
        """Wait for API responses to be captured."""
        start = datetime.utcnow()
        initial_count = len(self.intercepted.jobs_api_responses)
        
        while (datetime.utcnow() - start).total_seconds() * 1000 < timeout_ms:
            if self.state.is_blocked:
                return
            
            if len(self.intercepted.jobs_api_responses) > initial_count:
                await asyncio.sleep(0.5)
                if len(self.intercepted.jobs_api_responses) == len(self.intercepted.jobs_api_responses):
                    return
            
            await asyncio.sleep(0.2)
    
    async def _fetch_more_jobs(
        self,
        page: Page,
        remaining: int,
        seen_ids: set[str],
        params: dict,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch additional jobs by scrolling to trigger more API calls."""
        jobs_yielded = 0
        page_num = 1
        max_pages = 3
        
        while jobs_yielded < remaining and page_num <= max_pages and not self.state.is_blocked:
            await self._rate_limit()
            
            initial_count = len(self.intercepted.jobs_api_responses)
            
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self._wait_for_api_responses(page, timeout_ms=8000)
            
            if len(self.intercepted.jobs_api_responses) == initial_count:
                break
            
            for api_response in self.intercepted.jobs_api_responses[initial_count:]:
                if jobs_yielded >= remaining or self.state.is_blocked:
                    break
                
                api_jobs = extract_jobs_from_api_response(api_response.get("data", {}))
                
                for job_data in api_jobs:
                    if jobs_yielded >= remaining or self.state.is_blocked:
                        break
                    
                    job = self._parse_api_job(job_data)
                    if job and job.job_id not in seen_ids:
                        seen_ids.add(job.job_id)
                        jobs_yielded += 1
                        self.state.jobs_collected += 1
                        yield job
            
            page_num += 1
    
    def _parse_api_job(self, job_data: dict) -> JobPosting | None:
        """Parse job posting from API response data."""
        try:
            job_id = self._extract_job_id(job_data)
            if not job_id:
                return None
            
            title = job_data.get("title", "")
            company_name = self._extract_company_name(job_data)
            
            if not title or not company_name:
                return None
            
            location = self._extract_location(job_data)
            apply_url = extract_apply_url_from_job(job_data)
            ats_provider = detect_ats_from_url(apply_url) if apply_url else None
            
            is_easy_apply = self._is_easy_apply(job_data)
            external_apply = apply_url is not None and "linkedin.com" not in (apply_url or "")
            
            job_origin = JobOrigin.LINKEDIN_NATIVE
            if external_apply and ats_provider and ats_provider != ATSProvider.UNKNOWN:
                job_origin = JobOrigin.ATS
            
            description_text, description_hash = self._extract_description(job_data)
            
            return JobPosting(
                job_id=job_id,
                title=title,
                company_name=company_name,
                location=location,
                description_hash=description_hash,
                description_snippet=description_text[:500] if description_text else None,
                source=JobSource.LINKEDIN,
                source_url=f"https://www.linkedin.com/jobs/view/{job_id}",
                apply_url=apply_url,
                ats_provider=ats_provider,
                job_origin=job_origin,
                easy_apply=is_easy_apply,
                external_apply=external_apply,
                extraction_method="api",
            )
        
        except Exception as e:
            console.print(f"[yellow]API job parse error: {e}[/yellow]")
            return None
    
    def _extract_job_id(self, job_data: dict) -> str:
        """Extract job ID from job data."""
        entity_urn = job_data.get("entityUrn", "")
        if entity_urn:
            job_id = entity_urn.split(":")[-1]
            if job_id:
                return job_id
        
        job_id = job_data.get("jobPostingId", "") or job_data.get("id", "")
        if job_id:
            return str(job_id)
        
        tracking_urn = job_data.get("trackingUrn", "")
        if tracking_urn:
            return tracking_urn.split(":")[-1]
        
        return ""
    
    def _extract_company_name(self, job_data: dict) -> str:
        """Extract company name from job data."""
        company_data = job_data.get("companyDetails", {}) or job_data.get("company", {})
        
        if isinstance(company_data, dict):
            name = company_data.get("name", "") or company_data.get("companyName", "")
            if name:
                return name
            
            company = company_data.get("company", {})
            if isinstance(company, dict):
                return company.get("name", "")
        
        if isinstance(company_data, str):
            return company_data
        
        return job_data.get("companyName", "")
    
    def _extract_location(self, job_data: dict) -> str:
        """Extract location from job data."""
        location_data = job_data.get("formattedLocation") or job_data.get("location", {})
        
        if isinstance(location_data, str):
            return location_data
        
        if isinstance(location_data, dict):
            return location_data.get("defaultLocalizedName", "") or location_data.get("name", "")
        
        return job_data.get("locationName", "")
    
    def _is_easy_apply(self, job_data: dict) -> bool:
        """Check if job supports Easy Apply."""
        apply_method = job_data.get("applyMethod", {})
        
        if isinstance(apply_method, dict):
            type_str = apply_method.get("$type", "") or apply_method.get("type", "")
            if "easyApply" in type_str.lower() or "SimpleOnSiteApply" in type_str:
                return True
        
        if isinstance(apply_method, str):
            return "easyApply" in apply_method.lower()
        
        return job_data.get("easyApply", False)
    
    def _extract_description(self, job_data: dict) -> tuple[str, str | None]:
        """Extract description text and hash from job data."""
        description = job_data.get("description", {})
        description_text = ""
        
        if isinstance(description, dict):
            description_text = description.get("text", "") or description.get("rawText", "")
        elif isinstance(description, str):
            description_text = description
        
        description_hash = None
        if description_text:
            description_hash = hashlib.md5(description_text.encode()).hexdigest()
        
        return description_text, description_hash
    
    def get_state(self) -> ScraperState:
        """Get current scraper state."""
        return self.state
    
    def get_intercepted_data(self) -> InterceptedData:
        """Get intercepted network data."""
        return self.intercepted
