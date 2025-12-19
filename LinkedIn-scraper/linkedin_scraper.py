"""LinkedIn job data extraction using Playwright with network interception."""
import asyncio
import hashlib
import re
from datetime import datetime
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
from rich.console import Console

from schemas import JobPosting, JobSource, ATSProvider
from network_interceptor import (
    InterceptedData,
    setup_network_interception,
    extract_jobs_from_api_response,
    extract_apply_url_from_job,
)
from ats_detector import detect_ats_from_url

console = Console()


class LinkedInScraper:
    """Production-grade LinkedIn job scraper using network interception."""
    
    LINKEDIN_JOBS_SEARCH = "https://www.linkedin.com/jobs/search"
    LINKEDIN_JOBS_GUEST = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    LOGIN_INDICATORS = [
        "login",
        "signin",
        "sign-in",
        "checkpoint",
        "authwall",
    ]
    
    CAPTCHA_INDICATORS = [
        "captcha",
        "challenge",
        "security-verification",
    ]
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.intercepted = InterceptedData()
        self._stopped = False
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self) -> None:
        """Initialize browser and context."""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
    
    async def close(self) -> None:
        """Clean up browser resources."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
    
    def _check_blocked(self, url: str) -> tuple[bool, str]:
        """Check if we hit a login wall or captcha."""
        url_lower = url.lower()
        
        for indicator in self.LOGIN_INDICATORS:
            if indicator in url_lower:
                return True, "login_required"
        
        for indicator in self.CAPTCHA_INDICATORS:
            if indicator in url_lower:
                return True, "captcha_detected"
        
        return False, ""
    
    async def _wait_for_content(self, page: Page, selector: str, timeout: int = 10000) -> bool:
        """Wait for content to load without hard-coded sleeps."""
        try:
            await page.wait_for_selector(selector, timeout=timeout, state="attached")
            return True
        except Exception:
            return False
    
    async def search_jobs_guest(
        self,
        keywords: str = "",
        location: str = "",
        max_jobs: int = 25,
    ) -> AsyncGenerator[JobPosting, None]:
        """
        Search LinkedIn jobs using guest API (no login required).
        Uses network interception to capture job data.
        """
        if not self.context:
            raise RuntimeError("Scraper not initialized. Use 'async with' or call start()")
        
        page = await self.context.new_page()
        await setup_network_interception(page, self.intercepted)
        
        try:
            params = []
            if keywords:
                params.append(f"keywords={keywords}")
            if location:
                params.append(f"location={location}")
            params.append("position=1")
            params.append("pageNum=0")
            
            search_url = f"{self.LINKEDIN_JOBS_SEARCH}?{'&'.join(params)}"
            console.print(f"[blue]Navigating to:[/blue] {search_url}")
            
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            
            blocked, reason = self._check_blocked(page.url)
            if blocked:
                console.print(f"[red]Blocked: {reason}[/red]")
                self._stopped = True
                return
            
            await self._wait_for_content(page, ".jobs-search__results-list, .base-card, .job-search-card", timeout=20000)
            
            job_cards = await page.query_selector_all(".base-card, .base-search-card, .job-search-card")
            console.print(f"[green]Found {len(job_cards)} job cards on page[/green]")
            
            jobs_yielded = 0
            
            for card in job_cards[:max_jobs]:
                if self._stopped:
                    break
                
                try:
                    job = await self._extract_job_from_card(page, card)
                    if job:
                        jobs_yielded += 1
                        yield job
                except Exception as e:
                    console.print(f"[yellow]Error extracting job: {e}[/yellow]")
                    continue
            
            for api_response in self.intercepted.jobs_api_responses:
                if jobs_yielded >= max_jobs:
                    break
                
                api_jobs = extract_jobs_from_api_response(api_response.get("data", {}))
                for job_data in api_jobs:
                    if jobs_yielded >= max_jobs:
                        break
                    
                    job = self._parse_api_job_data(job_data)
                    if job:
                        jobs_yielded += 1
                        yield job
        
        finally:
            await page.close()
    
    async def _extract_job_from_card(self, page: Page, card) -> JobPosting | None:
        """Extract job posting data from a job card element."""
        try:
            title_el = await card.query_selector(".base-search-card__title")
            company_el = await card.query_selector(".base-search-card__subtitle")
            location_el = await card.query_selector(".job-search-card__location")
            link_el = await card.query_selector("a.base-card__full-link")
            
            if not title_el or not company_el:
                return None
            
            title = (await title_el.inner_text()).strip()
            company = (await company_el.inner_text()).strip()
            location = (await location_el.inner_text()).strip() if location_el else None
            
            job_url = await link_el.get_attribute("href") if link_el else None
            
            job_id = ""
            if job_url:
                match = re.search(r"/view/([^/?]+)", job_url)
                if match:
                    job_id = match.group(1)
                else:
                    job_id = hashlib.md5(f"{title}{company}".encode()).hexdigest()[:12]
            
            apply_url = None
            ats_provider = None
            external_apply = False
            
            if job_url and not self._stopped:
                apply_url, ats_provider = await self._get_apply_info(page, job_url)
                external_apply = apply_url is not None and "linkedin.com" not in apply_url
            
            return JobPosting(
                job_id=job_id,
                title=title,
                company_name=company,
                location=location,
                source=JobSource.LINKEDIN,
                source_url=job_url or "",
                apply_url=apply_url,
                ats_provider=ats_provider,
                external_apply=external_apply,
                easy_apply=not external_apply,
            )
        
        except Exception as e:
            console.print(f"[yellow]Card extraction error: {e}[/yellow]")
            return None
    
    async def _get_apply_info(self, page: Page, job_url: str) -> tuple[str | None, ATSProvider | None]:
        """Navigate to job detail and extract apply URL and ATS info."""
        detail_page = await self.context.new_page()
        
        try:
            await detail_page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
            
            blocked, reason = self._check_blocked(detail_page.url)
            if blocked:
                console.print(f"[red]Blocked on job detail: {reason}[/red]")
                self._stopped = True
                return None, None
            
            await self._wait_for_content(
                detail_page, 
                ".apply-button, .jobs-apply-button, .top-card-layout__cta-container, .jobs-s-apply", 
                timeout=10000
            )
            
            apply_selectors = [
                "a.apply-button",
                "a.jobs-apply-button", 
                ".top-card-layout__cta-container a",
                ".jobs-s-apply a",
                "[data-tracking-control-name*='apply'] a",
                ".jobs-apply-button--top-card a",
                "a[href*='externalApply']",
                "a[href*='applyUrl']",
                ".apply-button",
            ]
            
            for selector in apply_selectors:
                apply_button = await detail_page.query_selector(selector)
                if apply_button:
                    href = await apply_button.get_attribute("href")
                    if href and not href.startswith("javascript") and "linkedin.com" not in href:
                        console.print(f"[cyan]Found external apply: {href[:60]}...[/cyan]")
                        ats = detect_ats_from_url(href)
                        return href, ats
            
            all_links = await detail_page.query_selector_all("a[href]")
            for link in all_links:
                href = await link.get_attribute("href")
                if href:
                    ats = detect_ats_from_url(href)
                    if ats != ATSProvider.UNKNOWN:
                        console.print(f"[cyan]Found ATS link: {ats.value} - {href[:50]}...[/cyan]")
                        return href, ats
            
            external_link = await detail_page.query_selector(
                "a[href*='greenhouse'], a[href*='lever'], a[href*='workday'], "
                "a[href*='icims'], a[href*='taleo'], a[href*='jobvite']"
            )
            
            if external_link:
                href = await external_link.get_attribute("href")
                if href:
                    ats = detect_ats_from_url(href)
                    return href, ats
            
            return None, None
        
        except Exception as e:
            console.print(f"[yellow]Apply info error: {e}[/yellow]")
            return None, None
        
        finally:
            await detail_page.close()
    
    def _parse_api_job_data(self, job_data: dict) -> JobPosting | None:
        """Parse job posting from API response data."""
        try:
            job_id = job_data.get("entityUrn", "").split(":")[-1] or job_data.get("jobPostingId", "")
            if not job_id:
                job_id = hashlib.md5(str(job_data).encode()).hexdigest()[:12]
            
            title = job_data.get("title", "")
            
            company_name = ""
            company_data = job_data.get("companyDetails", {}) or job_data.get("company", {})
            if isinstance(company_data, dict):
                company_name = company_data.get("name", "") or company_data.get("companyName", "")
            
            if not title or not company_name:
                return None
            
            location = ""
            location_data = job_data.get("formattedLocation") or job_data.get("location", {})
            if isinstance(location_data, str):
                location = location_data
            elif isinstance(location_data, dict):
                location = location_data.get("defaultLocalizedName", "")
            
            apply_url = extract_apply_url_from_job(job_data)
            ats_provider = detect_ats_from_url(apply_url) if apply_url else None
            
            description = job_data.get("description", {})
            description_text = ""
            if isinstance(description, dict):
                description_text = description.get("text", "")
            elif isinstance(description, str):
                description_text = description
            
            description_hash = None
            if description_text:
                description_hash = hashlib.md5(description_text.encode()).hexdigest()
            
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
                easy_apply="easyApply" in str(job_data.get("applyMethod", "")),
                external_apply=apply_url is not None and "linkedin.com" not in (apply_url or ""),
            )
        
        except Exception as e:
            console.print(f"[yellow]API job parse error: {e}[/yellow]")
            return None
