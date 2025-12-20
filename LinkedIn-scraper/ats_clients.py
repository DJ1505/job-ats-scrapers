"""ATS JSON API clients for direct job extraction without HTML scraping."""
import hashlib
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import AsyncGenerator
from urllib.parse import urlparse, urljoin

import httpx
from rich.console import Console

from schemas import JobPosting, JobSource, JobOrigin, ATSProvider

console = Console()


class ATSClientBase(ABC):
    """Base class for ATS API clients."""
    
    TIMEOUT = 30.0
    
    def __init__(self):
        self.client: httpx.AsyncClient | None = None
    
    async def __aenter__(self):
        self.client = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
            },
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.client:
            await self.client.aclose()
    
    @abstractmethod
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs from the ATS API."""
        pass
    
    @abstractmethod
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from ATS URL."""
        pass
    
    def _generate_job_id(self, *parts: str) -> str:
        """Generate a consistent job ID from parts."""
        return hashlib.md5("".join(parts).encode()).hexdigest()[:12]


class GreenhouseClient(ATSClientBase):
    """Greenhouse JSON API client - uses public embed API."""
    
    API_BASE = "https://boards-api.greenhouse.io/v1/boards"
    
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs from Greenhouse API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        api_url = f"{self.API_BASE}/{company_slug}/jobs"
        console.print(f"[cyan]Fetching Greenhouse jobs: {api_url}[/cyan]")
        
        try:
            response = await self.client.get(api_url)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("jobs", [])
            console.print(f"[green]Greenhouse API returned {len(jobs)} jobs[/green]")
            
            for job in jobs:
                try:
                    job_id = str(job.get("id", ""))
                    title = job.get("title", "")
                    
                    if not job_id or not title:
                        continue
                    
                    location = job.get("location", {}).get("name", "")
                    job_url = job.get("absolute_url", f"https://boards.greenhouse.io/{company_slug}/jobs/{job_id}")
                    
                    updated_at = job.get("updated_at")
                    posted_date = None
                    if updated_at:
                        try:
                            posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=job_url,
                        ats_provider=ATSProvider.GREENHOUSE,
                        job_origin=JobOrigin.ATS,
                        posted_date=posted_date,
                        extraction_method="ats_api",
                    )
                except Exception as e:
                    console.print(f"[yellow]Greenhouse job parse error: {e}[/yellow]")
                    continue
                    
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]Greenhouse API error: {e.response.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]Greenhouse fetch error: {e}[/red]")
    
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from Greenhouse URL."""
        patterns = [
            r"boards\.greenhouse\.io/([^/]+)",
            r"job-boards\.greenhouse\.io/([^/]+)",
            r"greenhouse\.io/.*embed/job_board/js\?for=([^&]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


class LeverClient(ATSClientBase):
    """Lever JSON API client - uses public postings API."""
    
    API_BASE = "https://api.lever.co/v0/postings"
    
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs from Lever API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        api_url = f"{self.API_BASE}/{company_slug}"
        console.print(f"[cyan]Fetching Lever jobs: {api_url}[/cyan]")
        
        try:
            response = await self.client.get(api_url)
            response.raise_for_status()
            jobs = response.json()
            
            if not isinstance(jobs, list):
                jobs = []
            
            console.print(f"[green]Lever API returned {len(jobs)} jobs[/green]")
            
            for job in jobs:
                try:
                    job_id = job.get("id", "")
                    title = job.get("text", "")
                    
                    if not job_id or not title:
                        continue
                    
                    location = job.get("categories", {}).get("location", "")
                    job_url = job.get("hostedUrl", f"https://jobs.lever.co/{company_slug}/{job_id}")
                    apply_url = job.get("applyUrl", job_url)
                    
                    created_at = job.get("createdAt")
                    posted_date = None
                    if created_at:
                        try:
                            posted_date = datetime.fromtimestamp(created_at / 1000)
                        except Exception:
                            pass
                    
                    description_text = job.get("descriptionPlain", "")
                    description_hash = None
                    if description_text:
                        description_hash = hashlib.md5(description_text.encode()).hexdigest()
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        description_hash=description_hash,
                        description_snippet=description_text[:500] if description_text else None,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=apply_url,
                        ats_provider=ATSProvider.LEVER,
                        job_origin=JobOrigin.ATS,
                        posted_date=posted_date,
                        extraction_method="ats_api",
                    )
                except Exception as e:
                    console.print(f"[yellow]Lever job parse error: {e}[/yellow]")
                    continue
                    
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]Lever API error: {e.response.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]Lever fetch error: {e}[/red]")
    
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from Lever URL."""
        patterns = [
            r"jobs\.lever\.co/([^/]+)",
            r"lever\.co/([^/]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


class AshbyClient(ATSClientBase):
    """Ashby JSON API client - uses public job board API."""
    
    API_BASE = "https://api.ashbyhq.com/posting-api/job-board"
    
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs from Ashby API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        api_url = f"{self.API_BASE}/{company_slug}"
        console.print(f"[cyan]Fetching Ashby jobs: {api_url}[/cyan]")
        
        try:
            response = await self.client.get(api_url)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("jobs", [])
            console.print(f"[green]Ashby API returned {len(jobs)} jobs[/green]")
            
            for job in jobs:
                try:
                    job_id = job.get("id", "")
                    title = job.get("title", "")
                    
                    if not job_id or not title:
                        continue
                    
                    location = job.get("location", "")
                    job_url = job.get("jobUrl", f"https://jobs.ashbyhq.com/{company_slug}/{job_id}")
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=job_url,
                        ats_provider=ATSProvider.ASHBY,
                        job_origin=JobOrigin.ATS,
                        extraction_method="ats_api",
                    )
                except Exception as e:
                    console.print(f"[yellow]Ashby job parse error: {e}[/yellow]")
                    continue
                    
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]Ashby API error: {e.response.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]Ashby fetch error: {e}[/red]")
    
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from Ashby URL."""
        patterns = [
            r"jobs\.ashbyhq\.com/([^/]+)",
            r"ashbyhq\.com/([^/]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


class WorkdayClient(ATSClientBase):
    """Workday API client - requires tenant-specific URLs."""
    
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """
        Fetch jobs from Workday API.
        
        Note: Workday requires tenant-specific API endpoints.
        The base_url must be provided from the original apply URL.
        """
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        if not base_url:
            console.print("[yellow]Workday requires base_url from apply URL[/yellow]")
            return
        
        api_url = self._build_api_url(base_url, company_slug)
        if not api_url:
            console.print("[yellow]Could not build Workday API URL[/yellow]")
            return
        
        console.print(f"[cyan]Fetching Workday jobs: {api_url}[/cyan]")
        
        try:
            response = await self.client.get(api_url)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("jobPostings", [])
            console.print(f"[green]Workday API returned {len(jobs)} jobs[/green]")
            
            for job in jobs:
                try:
                    title = job.get("title", "")
                    if not title:
                        continue
                    
                    bullet_fields = job.get("bulletFields", [])
                    job_id = bullet_fields[0] if bullet_fields else self._generate_job_id(title, company_name)
                    
                    location = job.get("locationsText", "") or job.get("location", "")
                    external_path = job.get("externalPath", "")
                    
                    parsed = urlparse(base_url)
                    base = f"{parsed.scheme}://{parsed.netloc}"
                    job_url = urljoin(base, external_path) if external_path else base_url
                    
                    posted_on = job.get("postedOn")
                    posted_date = None
                    if posted_on:
                        try:
                            posted_date = datetime.fromisoformat(posted_on.replace("Z", "+00:00"))
                        except Exception:
                            pass
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=job_url,
                        ats_provider=ATSProvider.WORKDAY,
                        job_origin=JobOrigin.ATS,
                        posted_date=posted_date,
                        extraction_method="ats_api",
                    )
                except Exception as e:
                    console.print(f"[yellow]Workday job parse error: {e}[/yellow]")
                    continue
                    
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]Workday API error: {e.response.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]Workday fetch error: {e}[/red]")
    
    def _build_api_url(self, base_url: str, company_slug: str) -> str | None:
        """Build Workday API URL from base URL."""
        parsed = urlparse(base_url)
        
        match = re.search(r"/d/([^/]+)/", base_url)
        if match:
            tenant = match.group(1)
            return f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{tenant}/{company_slug}/jobs"
        
        match = re.search(r"myworkdayjobs\.com/([^/]+)", base_url)
        if match:
            site = match.group(1)
            return f"{parsed.scheme}://{parsed.netloc}/wday/cxs/{parsed.netloc.split('.')[0]}/{site}/jobs"
        
        return None
    
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from Workday URL."""
        patterns = [
            r"myworkdayjobs\.com/([^/]+)",
            r"wd\d+\.myworkdaysite\.com/.*?/([^/]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


class SmartRecruitersClient(ATSClientBase):
    """SmartRecruiters JSON API client."""
    
    API_BASE = "https://api.smartrecruiters.com/v1/companies"
    
    async def fetch_jobs(
        self,
        company_slug: str,
        company_name: str,
        base_url: str | None = None,
    ) -> AsyncGenerator[JobPosting, None]:
        """Fetch jobs from SmartRecruiters API."""
        if not self.client:
            raise RuntimeError("Client not initialized")
        
        api_url = f"{self.API_BASE}/{company_slug}/postings"
        console.print(f"[cyan]Fetching SmartRecruiters jobs: {api_url}[/cyan]")
        
        try:
            response = await self.client.get(api_url)
            response.raise_for_status()
            data = response.json()
            
            jobs = data.get("content", [])
            console.print(f"[green]SmartRecruiters API returned {len(jobs)} jobs[/green]")
            
            for job in jobs:
                try:
                    job_id = job.get("id", "") or job.get("uuid", "")
                    title = job.get("name", "")
                    
                    if not job_id or not title:
                        continue
                    
                    location = job.get("location", {})
                    location_str = location.get("city", "")
                    if location.get("region"):
                        location_str = f"{location_str}, {location.get('region')}"
                    
                    job_url = f"https://jobs.smartrecruiters.com/{company_slug}/{job_id}"
                    
                    yield JobPosting(
                        job_id=job_id,
                        title=title,
                        company_name=company_name,
                        location=location_str,
                        source=JobSource.ATS,
                        source_url=job_url,
                        apply_url=job_url,
                        ats_provider=ATSProvider.SMART_RECRUITERS,
                        job_origin=JobOrigin.ATS,
                        extraction_method="ats_api",
                    )
                except Exception as e:
                    console.print(f"[yellow]SmartRecruiters job parse error: {e}[/yellow]")
                    continue
                    
        except httpx.HTTPStatusError as e:
            console.print(f"[yellow]SmartRecruiters API error: {e.response.status_code}[/yellow]")
        except Exception as e:
            console.print(f"[red]SmartRecruiters fetch error: {e}[/red]")
    
    def extract_slug_from_url(self, url: str) -> str | None:
        """Extract company slug from SmartRecruiters URL."""
        patterns = [
            r"jobs\.smartrecruiters\.com/([^/]+)",
            r"careers\.smartrecruiters\.com/([^/]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None


def get_ats_client(provider: ATSProvider) -> ATSClientBase | None:
    """Get the appropriate ATS client for a provider."""
    clients = {
        ATSProvider.GREENHOUSE: GreenhouseClient,
        ATSProvider.LEVER: LeverClient,
        ATSProvider.ASHBY: AshbyClient,
        ATSProvider.WORKDAY: WorkdayClient,
        ATSProvider.SMART_RECRUITERS: SmartRecruitersClient,
    }
    client_class = clients.get(provider)
    return client_class() if client_class else None


async def fetch_ats_jobs(
    provider: ATSProvider,
    apply_url: str,
    company_name: str,
) -> list[JobPosting]:
    """Convenience function to fetch jobs from an ATS."""
    client = get_ats_client(provider)
    if not client:
        console.print(f"[yellow]No API client for {provider.value}[/yellow]")
        return []
    
    slug = client.extract_slug_from_url(apply_url)
    if not slug:
        console.print(f"[yellow]Could not extract slug from {apply_url}[/yellow]")
        return []
    
    jobs = []
    async with client:
        async for job in client.fetch_jobs(slug, company_name, apply_url):
            jobs.append(job)
    
    return jobs
