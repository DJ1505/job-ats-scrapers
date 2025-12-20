"""Job ingestion pipeline orchestrator.

ARCHITECTURE: LinkedIn Discovery → ATS Ingestion → Job Normalization

Flow:
1. Discover jobs via LinkedIn Guest API (network interception)
2. Classify jobs by origin (ATS vs LINKEDIN_NATIVE)
3. For ATS jobs: fetch directly from ATS JSON APIs
4. For LinkedIn-native jobs: accept as final (no further scraping)
5. Deduplicate and normalize all jobs
"""
import asyncio
from datetime import datetime
from typing import Callable
from urllib.parse import urlparse

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from schemas import (
    JobPosting,
    JobOrigin,
    ATSProvider,
    ATSCompanyInfo,
    PipelineResult,
    ScraperState,
    BlockReason,
)
from linkedin_scraper import LinkedInScraper
from ats_scraper import ATSScraper
from ats_detector import detect_ats_from_url, extract_career_page_base_url

console = Console()


class JobIngestionPipeline:
    """
    Production-grade job ingestion pipeline.
    
    Key behaviors:
    - LinkedIn is DISCOVERY layer only
    - ATS APIs are source of truth for ATS companies
    - LinkedIn-native jobs are accepted without further scraping
    - Immediate abort on block detection
    - Duplicate detection across sources
    """
    
    def __init__(
        self,
        headless: bool = True,
        rate_limit_ms: int = 2000,
        fetch_ats_jobs: bool = True,
    ):
        self.headless = headless
        self.rate_limit_ms = rate_limit_ms
        self.fetch_ats_jobs = fetch_ats_jobs
        
        self._linkedin_scraper: LinkedInScraper | None = None
        self._ats_scraper: ATSScraper | None = None
        
        self._result = PipelineResult()
        self._seen_job_ids: set[str] = set()
        self._companies_processed: set[str] = set()
        self._on_block: Callable[[BlockReason], None] | None = None
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def start(self) -> None:
        """Initialize pipeline components."""
        self._linkedin_scraper = LinkedInScraper(
            headless=self.headless,
            rate_limit_ms=self.rate_limit_ms,
        )
        await self._linkedin_scraper.start()
        
        self._ats_scraper = ATSScraper(context=self._linkedin_scraper.context)
        
        self._result = PipelineResult()
        self._seen_job_ids.clear()
        self._companies_processed.clear()
    
    async def close(self) -> None:
        """Clean up pipeline resources."""
        if self._linkedin_scraper:
            await self._linkedin_scraper.close()
    
    def set_block_callback(self, callback: Callable[[BlockReason], None]) -> None:
        """Set callback for block detection."""
        self._on_block = callback
        if self._linkedin_scraper:
            self._linkedin_scraper.set_block_callback(callback)
    
    def _handle_block(self, reason: BlockReason) -> None:
        """Handle block detection."""
        self._result.scraper_state.is_blocked = True
        self._result.scraper_state.block_reason = reason
        self._result.errors.append(f"Blocked: {reason.value}")
        console.print(f"[red bold]Pipeline blocked: {reason.value}[/red bold]")
        if self._on_block:
            self._on_block(reason)
    
    async def run(
        self,
        keywords: str = "",
        location: str = "",
        max_jobs: int = 25,
        max_ats_jobs_per_company: int = 50,
    ) -> PipelineResult:
        """
        Run the complete job ingestion pipeline.
        
        Steps:
        1. Search LinkedIn for jobs
        2. Classify each job by origin
        3. For ATS companies: fetch jobs via ATS API
        4. For LinkedIn-native: accept job as-is
        5. Deduplicate and return results
        """
        if not self._linkedin_scraper:
            raise RuntimeError("Pipeline not initialized. Use 'async with' or call start()")
        
        self._linkedin_scraper.set_block_callback(self._handle_block)
        
        console.print("[blue bold]═══ Job Ingestion Pipeline ═══[/blue bold]")
        console.print(f"Keywords: {keywords or 'Any'} | Location: {location or 'Any'} | Max: {max_jobs}")
        
        linkedin_jobs: list[JobPosting] = []
        ats_companies: dict[str, list[JobPosting]] = {}
        linkedin_native_companies: set[str] = set()
        
        console.print("\n[cyan]Phase 1: LinkedIn Discovery[/cyan]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Searching LinkedIn...", total=None)
            
            async for job in self._linkedin_scraper.search_jobs(
                keywords=keywords,
                location=location,
                max_jobs=max_jobs,
            ):
                linkedin_jobs.append(job)
                progress.update(task, description=f"Found {len(linkedin_jobs)} jobs...")
                
                if self._result.scraper_state.is_blocked:
                    break
            
            progress.update(task, description=f"[green]Discovered {len(linkedin_jobs)} jobs[/green]")
        
        if not linkedin_jobs:
            if self._result.scraper_state.is_blocked:
                console.print("[red]Pipeline blocked during LinkedIn discovery[/red]")
            else:
                console.print("[yellow]No jobs found on LinkedIn[/yellow]")
            return self._finalize_result()
        
        console.print("\n[cyan]Phase 2: Job Classification[/cyan]")
        
        for job in linkedin_jobs:
            company_key = job.company_name.lower()
            
            if job.job_origin == JobOrigin.ATS and job.apply_url:
                if company_key not in ats_companies:
                    ats_companies[company_key] = []
                ats_companies[company_key].append(job)
            else:
                linkedin_native_companies.add(company_key)
                self._add_job(job)
        
        console.print(f"  ATS companies: {len(ats_companies)}")
        console.print(f"  LinkedIn-native companies: {len(linkedin_native_companies)}")
        
        if self.fetch_ats_jobs and ats_companies and not self._result.scraper_state.is_blocked:
            console.print("\n[cyan]Phase 3: ATS Job Ingestion[/cyan]")
            
            for company_key, company_jobs in ats_companies.items():
                if self._result.scraper_state.is_blocked:
                    break
                
                if company_key in self._companies_processed:
                    continue
                
                representative_job = company_jobs[0]
                company_name = representative_job.company_name
                apply_url = representative_job.apply_url
                ats_provider = representative_job.ats_provider
                
                if not apply_url or not ats_provider:
                    for job in company_jobs:
                        self._add_job(job)
                    continue
                
                console.print(f"  Fetching from {ats_provider.value}: {company_name}")
                
                ats_job_count = 0
                try:
                    async for ats_job in self._ats_scraper.scrape_company(
                        apply_url=apply_url,
                        company_name=company_name,
                        max_jobs=max_ats_jobs_per_company,
                    ):
                        self._add_job(ats_job)
                        ats_job_count += 1
                except Exception as e:
                    console.print(f"[yellow]ATS fetch error for {company_name}: {e}[/yellow]")
                    self._result.errors.append(f"ATS error ({company_name}): {str(e)}")
                
                if ats_job_count > 0:
                    self._result.ats_companies[company_key] = ATSCompanyInfo(
                        company_name=company_name,
                        ats_provider=ats_provider,
                        ats_base_url=extract_career_page_base_url(apply_url) or "",
                        job_count=ats_job_count,
                    )
                    self._companies_processed.add(company_key)
                else:
                    for job in company_jobs:
                        self._add_job(job)
        else:
            for company_key, company_jobs in ats_companies.items():
                for job in company_jobs:
                    self._add_job(job)
        
        self._result.linkedin_native_companies = list(linkedin_native_companies)
        
        return self._finalize_result()
    
    def _add_job(self, job: JobPosting) -> bool:
        """Add job to results if not duplicate."""
        job_key = self._get_job_key(job)
        
        if job_key in self._seen_job_ids:
            return False
        
        self._seen_job_ids.add(job_key)
        self._result.jobs.append(job)
        self._result.scraper_state.jobs_collected += 1
        return True
    
    def _get_job_key(self, job: JobPosting) -> str:
        """Generate unique key for job deduplication."""
        return f"{job.company_name.lower()}:{job.job_id}"
    
    def _finalize_result(self) -> PipelineResult:
        """Finalize and return pipeline result."""
        self._result.completed_at = datetime.utcnow()
        
        if self._linkedin_scraper:
            self._result.scraper_state = self._linkedin_scraper.get_state()
        
        ats_count = sum(1 for j in self._result.jobs if j.job_origin == JobOrigin.ATS)
        native_count = sum(1 for j in self._result.jobs if j.job_origin == JobOrigin.LINKEDIN_NATIVE)
        
        console.print("\n[green bold]═══ Pipeline Complete ═══[/green bold]")
        console.print(f"Total jobs: {len(self._result.jobs)}")
        console.print(f"  ATS jobs: {ats_count}")
        console.print(f"  LinkedIn-native jobs: {native_count}")
        console.print(f"ATS companies detected: {len(self._result.ats_companies)}")
        
        if self._result.scraper_state.is_blocked:
            console.print(f"[red]Blocked: {self._result.scraper_state.block_reason}[/red]")
        
        if self._result.errors:
            console.print(f"[yellow]Errors: {len(self._result.errors)}[/yellow]")
        
        return self._result
    
    def get_result(self) -> PipelineResult:
        """Get current pipeline result."""
        return self._result


async def run_pipeline(
    keywords: str = "",
    location: str = "",
    max_jobs: int = 25,
    headless: bool = True,
    fetch_ats_jobs: bool = True,
) -> PipelineResult:
    """Convenience function to run the pipeline."""
    async with JobIngestionPipeline(
        headless=headless,
        fetch_ats_jobs=fetch_ats_jobs,
    ) as pipeline:
        return await pipeline.run(
            keywords=keywords,
            location=location,
            max_jobs=max_jobs,
        )
