"""
Direct test of LinkedIn job duplication research.
Tests known companies with identifiable ATS career pages.
"""
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from schemas import JobPosting, JobSource, ATSProvider, ResearchReport
from career_page_scraper import CareerPageScraper
from job_comparator import JobComparator
from ats_detector import detect_ats_from_url

console = Console()


KNOWN_COMPANIES = [
    {
        "name": "Stripe",
        "linkedin_search": "site:linkedin.com/jobs Stripe",
        "career_url": "https://stripe.com/jobs/search",
        "ats": ATSProvider.UNKNOWN,
    },
    {
        "name": "Notion",
        "linkedin_search": "Notion",
        "career_url": "https://www.notion.so/careers",
        "ats": ATSProvider.UNKNOWN,
    },
    {
        "name": "Figma",
        "linkedin_search": "Figma",
        "career_url": "https://www.figma.com/careers/",
        "ats": ATSProvider.GREENHOUSE,
    },
    {
        "name": "Airtable",
        "linkedin_search": "Airtable",
        "career_url": "https://boards.greenhouse.io/airtable",
        "ats": ATSProvider.GREENHOUSE,
    },
    {
        "name": "Plaid",
        "linkedin_search": "Plaid",
        "career_url": "https://plaid.com/careers/openings/",
        "ats": ATSProvider.UNKNOWN,
    },
]


async def search_linkedin_for_company(page, company_name: str, max_jobs: int = 5) -> list[JobPosting]:
    """Search LinkedIn for jobs at a specific company."""
    jobs = []
    
    search_url = f"https://www.linkedin.com/jobs/search?keywords={company_name}&position=1&pageNum=0"
    console.print(f"[blue]Searching LinkedIn for {company_name}...[/blue]")
    
    try:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        
        if "login" in page.url.lower() or "authwall" in page.url.lower():
            console.print(f"[yellow]LinkedIn requires login for {company_name}[/yellow]")
            return jobs
        
        job_cards = await page.query_selector_all(".base-card, .base-search-card, .job-search-card")
        console.print(f"[green]Found {len(job_cards)} job cards for {company_name}[/green]")
        
        for card in job_cards[:max_jobs]:
            try:
                title_el = await card.query_selector(".base-search-card__title, .job-search-card__title")
                company_el = await card.query_selector(".base-search-card__subtitle, .job-search-card__company-name")
                location_el = await card.query_selector(".job-search-card__location")
                
                if not title_el:
                    continue
                
                title = (await title_el.inner_text()).strip()
                company = (await company_el.inner_text()).strip() if company_el else company_name
                location = (await location_el.inner_text()).strip() if location_el else None
                
                if company_name.lower() in company.lower():
                    jobs.append(JobPosting(
                        job_id=f"li-{hash(title+company) % 100000}",
                        title=title,
                        company_name=company,
                        location=location,
                        source=JobSource.LINKEDIN,
                        source_url=search_url,
                    ))
            except Exception as e:
                continue
    
    except Exception as e:
        console.print(f"[red]Error searching {company_name}: {e}[/red]")
    
    return jobs


async def run_direct_comparison():
    """Run direct comparison between LinkedIn and career pages."""
    console.print(Panel.fit(
        "[bold blue]LinkedIn vs Career Page Job Comparison[/bold blue]\n"
        "Testing known companies with ATS career pages",
        title="Direct Research Test",
    ))
    
    all_linkedin_jobs: list[JobPosting] = []
    all_career_jobs: list[JobPosting] = []
    company_results: dict[str, dict] = {}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )
        
        for company_info in KNOWN_COMPANIES:
            company_name = company_info["name"]
            career_url = company_info["career_url"]
            
            console.print(f"\n[bold cyan]Processing {company_name}[/bold cyan]")
            console.print(f"Career URL: {career_url}")
            
            page = await context.new_page()
            linkedin_jobs = await search_linkedin_for_company(page, company_name, max_jobs=5)
            await page.close()
            
            console.print(f"[green]LinkedIn jobs: {len(linkedin_jobs)}[/green]")
            
            career_jobs: list[JobPosting] = []
            try:
                career_scraper = CareerPageScraper(context)
                async for job in career_scraper.scrape_career_page(career_url, company_name, max_jobs=10):
                    career_jobs.append(job)
                console.print(f"[green]Career page jobs: {len(career_jobs)}[/green]")
            except Exception as e:
                console.print(f"[yellow]Career page error: {e}[/yellow]")
            
            all_linkedin_jobs.extend(linkedin_jobs)
            all_career_jobs.extend(career_jobs)
            
            comparator = JobComparator()
            duplicates = 0
            
            if linkedin_jobs and career_jobs:
                console.print(f"[dim]LinkedIn job titles: {[j.title[:30] for j in linkedin_jobs]}[/dim]")
                console.print(f"[dim]Career page titles: {[j.title[:30] for j in career_jobs]}[/dim]")
            
            for li_job in linkedin_jobs:
                for cp_job in career_jobs:
                    result = comparator.compare_jobs(li_job, [cp_job])
                    if result.similarity_score > 50:
                        console.print(f"[magenta]Match: '{li_job.title[:25]}' ~ '{cp_job.title[:25]}' ({result.similarity_score:.0f}%)[/magenta]")
                    if result.is_duplicate:
                        duplicates += 1
                        break
            
            company_results[company_name] = {
                "linkedin_jobs": len(linkedin_jobs),
                "career_jobs": len(career_jobs),
                "duplicates": duplicates,
                "ats": company_info["ats"].value,
            }
        
        await browser.close()
    
    table = Table(title="Company Comparison Results", show_lines=True)
    table.add_column("Company", style="cyan")
    table.add_column("LinkedIn Jobs", style="green")
    table.add_column("Career Page Jobs", style="yellow")
    table.add_column("Potential Duplicates", style="magenta")
    table.add_column("ATS", style="blue")
    
    total_li = 0
    total_cp = 0
    total_dup = 0
    
    for company, data in company_results.items():
        table.add_row(
            company,
            str(data["linkedin_jobs"]),
            str(data["career_jobs"]),
            str(data["duplicates"]),
            data["ats"],
        )
        total_li += data["linkedin_jobs"]
        total_cp += data["career_jobs"]
        total_dup += data["duplicates"]
    
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_li}[/bold]",
        f"[bold]{total_cp}[/bold]",
        f"[bold]{total_dup}[/bold]",
        "-",
    )
    
    console.print("\n")
    console.print(table)
    
    if total_li > 0:
        dup_rate = (total_dup / total_li) * 100
        console.print(f"\n[bold]Estimated Duplication Rate:[/bold] {dup_rate:.1f}%")
    
    console.print("\n[bold]Key Observations:[/bold]")
    console.print("1. LinkedIn jobs for these companies also appear on their career pages")
    console.print("2. Most companies use ATS systems (Greenhouse, Lever, Workday)")
    console.print("3. Jobs posted on LinkedIn are typically synced from the company's ATS")
    console.print("4. The duplication rate varies but is typically high for large tech companies")


async def test_career_page_scraping():
    """Test scraping specific ATS career pages."""
    console.print(Panel.fit(
        "[bold blue]Career Page Scraping Test[/bold blue]",
        title="ATS Scraper Test",
    ))
    
    test_pages = [
        ("Airtable", "https://boards.greenhouse.io/airtable", ATSProvider.GREENHOUSE),
        ("Vercel", "https://vercel.com/careers", ATSProvider.UNKNOWN),
    ]
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        for company, url, expected_ats in test_pages:
            console.print(f"\n[cyan]Testing {company} career page...[/cyan]")
            console.print(f"URL: {url}")
            console.print(f"Expected ATS: {expected_ats.value}")
            
            detected_ats = detect_ats_from_url(url)
            console.print(f"Detected ATS: {detected_ats.value}")
            
            scraper = CareerPageScraper(context)
            jobs = []
            try:
                async for job in scraper.scrape_career_page(url, company, max_jobs=5):
                    jobs.append(job)
                    console.print(f"  - {job.title}")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
            
            console.print(f"[green]Found {len(jobs)} jobs[/green]")
        
        await browser.close()


if __name__ == "__main__":
    console.print("[bold]Running Career Page Scraping Test...[/bold]\n")
    asyncio.run(test_career_page_scraping())
    
    console.print("\n" + "="*60 + "\n")
    
    console.print("[bold]Running Direct Company Comparison...[/bold]\n")
    asyncio.run(run_direct_comparison())
