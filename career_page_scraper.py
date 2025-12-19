"""Career page job extraction for various ATS providers."""
import asyncio
import hashlib
import re
from typing import AsyncGenerator
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console

from schemas import JobPosting, JobSource, ATSProvider
from ats_detector import detect_ats_from_url
from network_interceptor import InterceptedData, setup_network_interception

console = Console()


class CareerPageScraper:
    """Scraper for extracting jobs from company career pages and ATS portals."""
    
    ATS_API_PATTERNS = {
        ATSProvider.GREENHOUSE: [
            r"/embed/job_board/js",
            r"/boards/.*/jobs",
        ],
        ATSProvider.LEVER: [
            r"/v0/postings/",
        ],
        ATSProvider.WORKDAY: [
            r"/wday/cxs/.*/jobs",
        ],
    }
    
    def __init__(self, context: BrowserContext):
        self.context = context
        self.intercepted = InterceptedData()
    
    async def scrape_career_page(
        self,
        career_url: str,
        company_name: str,
        max_jobs: int = 50,
    ) -> AsyncGenerator[JobPosting, None]:
        """Scrape jobs from a career page URL."""
        ats_provider = detect_ats_from_url(career_url)
        
        if ats_provider == ATSProvider.GREENHOUSE:
            async for job in self._scrape_greenhouse(career_url, company_name, max_jobs):
                yield job
        elif ats_provider == ATSProvider.LEVER:
            async for job in self._scrape_lever(career_url, company_name, max_jobs):
                yield job
        elif ats_provider == ATSProvider.WORKDAY:
            async for job in self._scrape_workday(career_url, company_name, max_jobs):
                yield job
        else:
            async for job in self._scrape_generic(career_url, company_name, max_jobs):
                yield job
    
    async def _scrape_greenhouse(
        self,
        url: str,
        company_name: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """Scrape Greenhouse job board."""
        page = await self.context.new_page()
        jobs_found = 0
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            
            job_elements = await page.query_selector_all(".opening, [data-job-id], .job-post")
            
            for element in job_elements[:max_jobs]:
                if jobs_found >= max_jobs:
                    break
                
                try:
                    title_el = await element.query_selector("a, .job-title, h3")
                    location_el = await element.query_selector(".location, .job-location")
                    
                    if not title_el:
                        continue
                    
                    title = (await title_el.inner_text()).strip()
                    location = (await location_el.inner_text()).strip() if location_el else None
                    
                    href = await title_el.get_attribute("href")
                    job_id = ""
                    if href:
                        match = re.search(r"/jobs/(\d+)", href)
                        if match:
                            job_id = match.group(1)
                    
                    if not job_id:
                        job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                    
                    job_url = href if href and href.startswith("http") else f"{url.rstrip('/')}/{href}" if href else url
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.CAREER_PAGE,
                        source_url=job_url,
                        ats_provider=ATSProvider.GREENHOUSE,
                    )
                    jobs_found += 1
                
                except Exception as e:
                    console.print(f"[yellow]Greenhouse job extraction error: {e}[/yellow]")
                    continue
        
        finally:
            await page.close()
    
    async def _scrape_lever(
        self,
        url: str,
        company_name: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """Scrape Lever job board."""
        page = await self.context.new_page()
        jobs_found = 0
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            
            job_elements = await page.query_selector_all(".posting, [data-qa='posting-name']")
            
            for element in job_elements[:max_jobs]:
                if jobs_found >= max_jobs:
                    break
                
                try:
                    title_el = await element.query_selector("h5, .posting-title, a")
                    location_el = await element.query_selector(".location, .posting-categories .sort-by-location")
                    link_el = await element.query_selector("a.posting-btn-submit, a[href*='/apply']")
                    
                    if not title_el:
                        title_el = await element.query_selector("a")
                    
                    if not title_el:
                        continue
                    
                    title = (await title_el.inner_text()).strip()
                    location = (await location_el.inner_text()).strip() if location_el else None
                    
                    href = await link_el.get_attribute("href") if link_el else None
                    if not href:
                        href = await title_el.get_attribute("href")
                    
                    job_id = ""
                    if href:
                        match = re.search(r"/([a-f0-9-]{36})", href)
                        if match:
                            job_id = match.group(1)
                    
                    if not job_id:
                        job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                    
                    job_url = href if href and href.startswith("http") else url
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.CAREER_PAGE,
                        source_url=job_url,
                        ats_provider=ATSProvider.LEVER,
                    )
                    jobs_found += 1
                
                except Exception as e:
                    console.print(f"[yellow]Lever job extraction error: {e}[/yellow]")
                    continue
        
        finally:
            await page.close()
    
    async def _scrape_workday(
        self,
        url: str,
        company_name: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """Scrape Workday job board using network interception."""
        page = await self.context.new_page()
        jobs_found = 0
        api_jobs: list[dict] = []
        
        async def capture_workday_api(response):
            if "/wday/cxs/" in response.url and "/jobs" in response.url:
                try:
                    if response.status == 200:
                        data = await response.json()
                        if "jobPostings" in data:
                            api_jobs.extend(data["jobPostings"])
                except Exception:
                    pass
        
        page.on("response", capture_workday_api)
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            await asyncio.sleep(2)
            
            for job_data in api_jobs[:max_jobs]:
                if jobs_found >= max_jobs:
                    break
                
                try:
                    title = job_data.get("title", "")
                    location = job_data.get("locationsText", "") or job_data.get("location", "")
                    job_id = job_data.get("bulletFields", [""])[0] if job_data.get("bulletFields") else ""
                    
                    if not job_id:
                        job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                    
                    external_path = job_data.get("externalPath", "")
                    job_url = f"{url.split('/d/')[0]}{external_path}" if external_path else url
                    
                    if title:
                        yield JobPosting(
                            job_id=job_id,
                            title=title,
                            company_name=company_name,
                            location=location,
                            source=JobSource.CAREER_PAGE,
                            source_url=job_url,
                            ats_provider=ATSProvider.WORKDAY,
                        )
                        jobs_found += 1
                
                except Exception as e:
                    console.print(f"[yellow]Workday job extraction error: {e}[/yellow]")
                    continue
            
            if jobs_found == 0:
                job_elements = await page.query_selector_all("[data-automation-id='jobTitle'], .css-19uc56f")
                
                for element in job_elements[:max_jobs]:
                    try:
                        title = (await element.inner_text()).strip()
                        if title:
                            job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                            yield JobPosting(
                                job_id=job_id,
                                title=title,
                                company_name=company_name,
                                source=JobSource.CAREER_PAGE,
                                source_url=url,
                                ats_provider=ATSProvider.WORKDAY,
                            )
                            jobs_found += 1
                    except Exception:
                        continue
        
        finally:
            await page.close()
    
    async def _scrape_generic(
        self,
        url: str,
        company_name: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """Generic career page scraper for unknown ATS or custom pages."""
        page = await self.context.new_page()
        jobs_found = 0
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            
            job_selectors = [
                ".job-listing",
                ".job-card",
                ".job-item",
                ".career-listing",
                "[class*='job']",
                "article",
                ".position",
                ".opening",
            ]
            
            job_elements = []
            for selector in job_selectors:
                elements = await page.query_selector_all(selector)
                if elements:
                    job_elements = elements
                    break
            
            for element in job_elements[:max_jobs]:
                if jobs_found >= max_jobs:
                    break
                
                try:
                    title_el = await element.query_selector("h2, h3, h4, a, .title, .job-title")
                    location_el = await element.query_selector(".location, .job-location, [class*='location']")
                    
                    if not title_el:
                        continue
                    
                    title = (await title_el.inner_text()).strip()
                    if len(title) < 3 or len(title) > 200:
                        continue
                    
                    location = (await location_el.inner_text()).strip() if location_el else None
                    
                    href = await title_el.get_attribute("href")
                    job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                    
                    job_url = href if href and href.startswith("http") else url
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.CAREER_PAGE,
                        source_url=job_url,
                        ats_provider=detect_ats_from_url(job_url),
                    )
                    jobs_found += 1
                
                except Exception as e:
                    continue
        
        finally:
            await page.close()
