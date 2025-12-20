"""ATS job extraction with API-first approach and Playwright fallback.

ARCHITECTURE: API-FIRST
- JSON APIs are the PRIMARY source for ATS job data
- Playwright/network interception is FALLBACK ONLY
- HTML scraping is LAST RESORT with explicit warnings
"""
import asyncio
import hashlib
import re
from typing import AsyncGenerator
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page
from rich.console import Console

from schemas import JobPosting, JobSource, JobOrigin, ATSProvider, ATSCompanyInfo
from ats_detector import detect_ats_from_url
from ats_clients import (
    get_ats_client,
    GreenhouseClient,
    LeverClient,
    AshbyClient,
    WorkdayClient,
    SmartRecruitersClient,
)
from network_interceptor import InterceptedData

console = Console()


class ATSScraper:
    """
    ATS job scraper with API-first architecture.
    
    Priority order:
    1. JSON API (preferred - no browser needed)
    2. Network interception (Playwright captures API responses)
    3. HTML scraping (last resort with warnings)
    """
    
    SUPPORTED_API_PROVIDERS = {
        ATSProvider.GREENHOUSE,
        ATSProvider.LEVER,
        ATSProvider.ASHBY,
        ATSProvider.SMART_RECRUITERS,
        ATSProvider.WORKDAY,
    }
    
    def __init__(self, context: BrowserContext | None = None):
        """
        Initialize ATS scraper.
        
        Args:
            context: Optional Playwright browser context for fallback scraping
        """
        self.context = context
        self._ats_cache: dict[str, ATSCompanyInfo] = {}
    
    async def scrape_company(
        self,
        apply_url: str,
        company_name: str,
        max_jobs: int = 50,
    ) -> AsyncGenerator[JobPosting, None]:
        """
        Scrape jobs from an ATS using the best available method.
        
        Args:
            apply_url: URL from LinkedIn job apply button
            company_name: Company name for the jobs
            max_jobs: Maximum jobs to fetch
        """
        ats_provider = detect_ats_from_url(apply_url)
        
        if ats_provider == ATSProvider.UNKNOWN:
            console.print(f"[yellow]Unknown ATS for URL: {apply_url}[/yellow]")
            return
        
        console.print(f"[blue]Detected ATS: {ats_provider.value} for {company_name}[/blue]")
        
        if ats_provider in self.SUPPORTED_API_PROVIDERS:
            jobs_count = 0
            async for job in self._fetch_via_api(ats_provider, apply_url, company_name):
                if jobs_count >= max_jobs:
                    break
                jobs_count += 1
                yield job
            
            if jobs_count > 0:
                self._update_cache(company_name, ats_provider, apply_url, jobs_count)
                console.print(f"[green]Fetched {jobs_count} jobs via {ats_provider.value} API[/green]")
                return
            
            console.print(f"[yellow]API returned no jobs, trying network interception...[/yellow]")
        
        if self.context:
            jobs_count = 0
            async for job in self._fetch_via_network_interception(ats_provider, apply_url, company_name, max_jobs):
                jobs_count += 1
                yield job
            
            if jobs_count > 0:
                self._update_cache(company_name, ats_provider, apply_url, jobs_count)
                return
        
        console.print(f"[red]Could not fetch jobs from {ats_provider.value} for {company_name}[/red]")
    
    async def _fetch_via_api(
        self,
        provider: ATSProvider,
        apply_url: str,
        company_name: str,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs directly from ATS JSON API."""
        client = get_ats_client(provider)
        if not client:
            return
        
        slug = client.extract_slug_from_url(apply_url)
        if not slug:
            console.print(f"[yellow]Could not extract company slug from {apply_url}[/yellow]")
            return
        
        try:
            async with client:
                async for job in client.fetch_jobs(slug, company_name, apply_url):
                    yield job
        except Exception as e:
            console.print(f"[red]API fetch error: {e}[/red]")
    
    async def _fetch_via_network_interception(
        self,
        provider: ATSProvider,
        url: str,
        company_name: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs via Playwright network interception (fallback)."""
        if not self.context:
            return
        
        console.print(f"[yellow]FALLBACK: Using network interception for {provider.value}[/yellow]")
        
        page = await self.context.new_page()
        intercepted = InterceptedData()
        api_jobs: list[dict] = []
        
        async def capture_api_response(response):
            try:
                if response.status == 200:
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = await response.json()
                        api_jobs.append({"url": response.url, "data": data})
            except Exception:
                pass
        
        page.on("response", capture_api_response)
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            
            await asyncio.sleep(1)
            
            jobs_found = 0
            
            for api_response in api_jobs:
                if jobs_found >= max_jobs:
                    break
                
                jobs = self._extract_jobs_from_response(api_response["data"], provider, company_name, url)
                for job in jobs:
                    if jobs_found >= max_jobs:
                        break
                    jobs_found += 1
                    yield job
            
            if jobs_found == 0:
                console.print(f"[yellow]WARNING: Falling back to HTML scraping for {company_name}[/yellow]")
                async for job in self._html_fallback(page, provider, company_name, url, max_jobs):
                    yield job
        
        finally:
            await page.close()
    
    def _extract_jobs_from_response(
        self,
        data: dict,
        provider: ATSProvider,
        company_name: str,
        base_url: str,
    ) -> list[JobPosting]:
        """Extract jobs from intercepted API response based on provider."""
        jobs = []
        
        if provider == ATSProvider.WORKDAY:
            job_postings = data.get("jobPostings", [])
            for job_data in job_postings:
                job = self._parse_workday_job(job_data, company_name, base_url)
                if job:
                    jobs.append(job)
        
        elif provider == ATSProvider.GREENHOUSE:
            job_list = data.get("jobs", [])
            for job_data in job_list:
                job = self._parse_greenhouse_job(job_data, company_name)
                if job:
                    jobs.append(job)
        
        elif provider == ATSProvider.LEVER:
            if isinstance(data, list):
                for job_data in data:
                    job = self._parse_lever_job(job_data, company_name)
                    if job:
                        jobs.append(job)
        
        return jobs
    
    def _parse_workday_job(self, job_data: dict, company_name: str, base_url: str) -> JobPosting | None:
        """Parse Workday job from API response."""
        try:
            title = job_data.get("title", "")
            if not title:
                return None
            
            bullet_fields = job_data.get("bulletFields", [])
            job_id = bullet_fields[0] if bullet_fields else hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
            
            location = job_data.get("locationsText", "") or job_data.get("location", "")
            external_path = job_data.get("externalPath", "")
            
            parsed = urlparse(base_url)
            job_url = f"{parsed.scheme}://{parsed.netloc}{external_path}" if external_path else base_url
            
            return JobPosting(
                job_id=job_id,
                title=title,
                company_name=company_name,
                location=location,
                source=JobSource.ATS,
                source_url=job_url,
                apply_url=job_url,
                ats_provider=ATSProvider.WORKDAY,
                job_origin=JobOrigin.ATS,
                extraction_method="network_interception",
            )
        except Exception:
            return None
    
    def _parse_greenhouse_job(self, job_data: dict, company_name: str) -> JobPosting | None:
        """Parse Greenhouse job from API response."""
        try:
            job_id = str(job_data.get("id", ""))
            title = job_data.get("title", "")
            
            if not job_id or not title:
                return None
            
            location = job_data.get("location", {}).get("name", "")
            job_url = job_data.get("absolute_url", "")
            
            return JobPosting(
                job_id=job_id,
                title=title,
                company_name=company_name,
                location=location,
                source=JobSource.ATS,
                source_url=job_url,
                apply_url=job_url,
                ats_provider=ATSProvider.GREENHOUSE,
                job_origin=JobOrigin.ATS,
                extraction_method="network_interception",
            )
        except Exception:
            return None
    
    def _parse_lever_job(self, job_data: dict, company_name: str) -> JobPosting | None:
        """Parse Lever job from API response."""
        try:
            job_id = job_data.get("id", "")
            title = job_data.get("text", "")
            
            if not job_id or not title:
                return None
            
            location = job_data.get("categories", {}).get("location", "")
            job_url = job_data.get("hostedUrl", "")
            apply_url = job_data.get("applyUrl", job_url)
            
            return JobPosting(
                job_id=job_id,
                title=title,
                company_name=company_name,
                location=location,
                source=JobSource.ATS,
                source_url=job_url,
                apply_url=apply_url,
                ats_provider=ATSProvider.LEVER,
                job_origin=JobOrigin.ATS,
                extraction_method="network_interception",
            )
        except Exception:
            return None
    
    async def _html_fallback(
        self,
        page: Page,
        provider: ATSProvider,
        company_name: str,
        base_url: str,
        max_jobs: int,
    ) -> AsyncGenerator[JobPosting, None]:
        """
        HTML scraping fallback - LAST RESORT ONLY.
        
        WARNING: This method uses brittle DOM selectors that may break.
        """
        console.print("[red bold]⚠️ HTML FALLBACK: Using brittle DOM selectors[/red bold]")
        
        selectors = self._get_provider_selectors(provider)
        if not selectors:
            return
        
        jobs_found = 0
        
        try:
            job_elements = await page.query_selector_all(selectors["container"])
            
            for element in job_elements[:max_jobs]:
                if jobs_found >= max_jobs:
                    break
                
                try:
                    title_el = await element.query_selector(selectors["title"])
                    if not title_el:
                        continue
                    
                    title = (await title_el.inner_text()).strip()
                    if not title or len(title) < 3:
                        continue
                    
                    location = ""
                    if selectors.get("location"):
                        location_el = await element.query_selector(selectors["location"])
                        if location_el:
                            location = (await location_el.inner_text()).strip()
                    
                    href = await title_el.get_attribute("href")
                    job_id = hashlib.md5(f"{title}{company_name}".encode()).hexdigest()[:12]
                    
                    if href:
                        match = re.search(r"/jobs?/(\d+)", href)
                        if match:
                            job_id = match.group(1)
                    
                    job_url = href if href and href.startswith("http") else base_url
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=job_url,
                        ats_provider=provider,
                        job_origin=JobOrigin.ATS,
                        extraction_method="html_fallback",
                    )
                    jobs_found += 1
                
                except Exception as e:
                    console.print(f"[yellow]HTML extraction error: {e}[/yellow]")
                    continue
        
        except Exception as e:
            console.print(f"[red]HTML fallback failed: {e}[/red]")
    
    def _get_provider_selectors(self, provider: ATSProvider) -> dict | None:
        """Get DOM selectors for a provider (fallback only)."""
        selectors = {
            ATSProvider.GREENHOUSE: {
                "container": ".opening, [data-job-id], .job-post",
                "title": "a, .job-title, h3",
                "location": ".location, .job-location",
            },
            ATSProvider.LEVER: {
                "container": ".posting, [data-qa='posting-name']",
                "title": "h5, .posting-title, a",
                "location": ".location, .posting-categories .sort-by-location",
            },
            ATSProvider.WORKDAY: {
                "container": "[data-automation-id='jobTitle'], .css-19uc56f, .job-listing",
                "title": "a, span",
                "location": "[data-automation-id='location'], .css-location",
            },
            ATSProvider.ASHBY: {
                "container": ".ashby-job-posting, [data-job-id]",
                "title": "a, h3, .job-title",
                "location": ".location",
            },
        }
        return selectors.get(provider)
    
    def _update_cache(
        self,
        company_name: str,
        provider: ATSProvider,
        url: str,
        job_count: int,
    ) -> None:
        """Update ATS company cache."""
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        self._ats_cache[company_name.lower()] = ATSCompanyInfo(
            company_name=company_name,
            ats_provider=provider,
            ats_base_url=base_url,
            job_count=job_count,
        )
    
    def get_cached_ats_info(self, company_name: str) -> ATSCompanyInfo | None:
        """Get cached ATS info for a company."""
        return self._ats_cache.get(company_name.lower())
    
    def is_company_cached(self, company_name: str) -> bool:
        """Check if company ATS info is cached."""
        return company_name.lower() in self._ats_cache
    
    def get_all_cached_companies(self) -> dict[str, ATSCompanyInfo]:
        """Get all cached ATS company info."""
        return self._ats_cache.copy()
