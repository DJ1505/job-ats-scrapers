"""
LinkedIn Job Duplication Research Tool

This script researches whether LinkedIn jobs are duplicates of company career page postings
or if they are exclusive to LinkedIn. Uses Playwright for network interception.

Usage:
    python main.py --keywords "software engineer" --location "San Francisco" --max-jobs 20
"""
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
import pandas as pd

from schemas import (
    JobPosting,
    ResearchReport,
    DuplicationResult,
    CompanyInfo,
    ATSProvider,
)
from linkedin_scraper import LinkedInScraper
from career_page_scraper import CareerPageScraper
from job_comparator import JobComparator
from ats_detector import detect_ats_from_url, extract_career_page_base_url

console = Console()


async def run_research(
    keywords: str = "software engineer",
    location: str = "",
    max_jobs: int = 10,
    headless: bool = True,
    output_dir: str = "results",
) -> ResearchReport:
    """
    Run the LinkedIn job duplication research.
    
    Steps:
    1. Search LinkedIn for jobs matching criteria
    2. For each job, extract the apply URL and detect ATS
    3. If external apply URL found, scrape the career page
    4. Compare jobs to detect duplicates
    5. Generate report
    """
    report = ResearchReport()
    linkedin_jobs: list[JobPosting] = []
    career_page_jobs: list[JobPosting] = []
    comparator = JobComparator()
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    console.print(Panel.fit(
        "[bold blue]LinkedIn Job Duplication Research[/bold blue]\n"
        f"Keywords: {keywords or 'Any'}\n"
        f"Location: {location or 'Any'}\n"
        f"Max Jobs: {max_jobs}",
        title="Research Parameters",
    ))
    
    async with LinkedInScraper(headless=headless) as scraper:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Searching LinkedIn jobs...", total=None)
            
            async for job in scraper.search_jobs_guest(
                keywords=keywords,
                location=location,
                max_jobs=max_jobs,
            ):
                linkedin_jobs.append(job)
                progress.update(task, description=f"Found {len(linkedin_jobs)} jobs...")
            
            progress.update(task, description=f"[green]Collected {len(linkedin_jobs)} LinkedIn jobs[/green]")
        
        if not linkedin_jobs:
            console.print("[yellow]No LinkedIn jobs found. The search may have been blocked.[/yellow]")
            console.print("[yellow]Try running with --no-headless to see what's happening.[/yellow]")
            return report
        
        _display_linkedin_jobs_table(linkedin_jobs)
        
        career_urls_to_scrape: dict[str, list[JobPosting]] = {}
        
        for job in linkedin_jobs:
            if job.apply_url and job.external_apply:
                base_url = extract_career_page_base_url(job.apply_url)
                if base_url:
                    if base_url not in career_urls_to_scrape:
                        career_urls_to_scrape[base_url] = []
                    career_urls_to_scrape[base_url].append(job)
        
        console.print(f"\n[blue]Found {len(career_urls_to_scrape)} unique career pages to check[/blue]")
        
        if career_urls_to_scrape:
            career_scraper = CareerPageScraper(scraper.context)
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                for career_url, jobs in career_urls_to_scrape.items():
                    company_name = jobs[0].company_name
                    task = progress.add_task(f"Scraping {company_name}...", total=None)
                    
                    try:
                        async for cp_job in career_scraper.scrape_career_page(
                            career_url,
                            company_name,
                            max_jobs=30,
                        ):
                            career_page_jobs.append(cp_job)
                    except Exception as e:
                        console.print(f"[yellow]Error scraping {career_url}: {e}[/yellow]")
                    
                    progress.update(task, completed=True)
    
    console.print(f"\n[green]Scraped {len(career_page_jobs)} jobs from career pages[/green]")
    
    console.print("\n[blue]Comparing jobs for duplicates...[/blue]")
    results = comparator.batch_compare(linkedin_jobs, career_page_jobs)
    
    duplicates = [r for r in results if r.is_duplicate]
    linkedin_only = [r for r in results if not r.is_duplicate]
    
    report.total_linkedin_jobs_analyzed = len(linkedin_jobs)
    report.total_career_page_jobs_found = len(career_page_jobs)
    report.confirmed_duplicates = len(duplicates)
    report.linkedin_only_jobs = len(linkedin_only)
    report.duplication_rate = (len(duplicates) / len(linkedin_jobs) * 100) if linkedin_jobs else 0
    report.results = results
    
    ats_counts: dict[str, int] = {}
    for job in linkedin_jobs:
        if job.ats_provider:
            ats_name = job.ats_provider.value
            ats_counts[ats_name] = ats_counts.get(ats_name, 0) + 1
    report.ats_distribution = ats_counts
    
    companies_analyzed: dict[str, CompanyInfo] = {}
    for job in linkedin_jobs:
        company = job.company_name
        if company not in companies_analyzed:
            companies_analyzed[company] = CompanyInfo(name=company)
        companies_analyzed[company].jobs_on_linkedin += 1
        if job.ats_provider:
            companies_analyzed[company].detected_ats = job.ats_provider
    
    for job in career_page_jobs:
        company = job.company_name
        if company in companies_analyzed:
            companies_analyzed[company].jobs_on_career_page += 1
    
    for result in duplicates:
        company = result.linkedin_job.company_name
        if company in companies_analyzed:
            companies_analyzed[company].duplicates_found += 1
    
    report.companies_analyzed = list(companies_analyzed.values())
    
    _display_results(report)
    _save_results(report, output_path)
    
    return report


def _display_linkedin_jobs_table(jobs: list[JobPosting]) -> None:
    """Display LinkedIn jobs in a table."""
    table = Table(title="LinkedIn Jobs Found", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Company", style="green")
    table.add_column("Location", style="yellow")
    table.add_column("Apply Type", style="magenta")
    table.add_column("ATS", style="blue")
    
    for job in jobs[:20]:
        apply_type = "Easy Apply" if job.easy_apply else "External"
        ats = job.ats_provider.value if job.ats_provider else "-"
        table.add_row(
            job.title[:40],
            job.company_name[:25],
            (job.location or "-")[:20],
            apply_type,
            ats,
        )
    
    if len(jobs) > 20:
        table.add_row("...", f"({len(jobs) - 20} more)", "...", "...", "...")
    
    console.print(table)


def _display_results(report: ResearchReport) -> None:
    """Display research results."""
    console.print("\n")
    console.print(Panel.fit(
        f"[bold]Total LinkedIn Jobs Analyzed:[/bold] {report.total_linkedin_jobs_analyzed}\n"
        f"[bold]Career Page Jobs Found:[/bold] {report.total_career_page_jobs_found}\n"
        f"[bold]Confirmed Duplicates:[/bold] {report.confirmed_duplicates}\n"
        f"[bold]LinkedIn-Only Jobs:[/bold] {report.linkedin_only_jobs}\n"
        f"[bold green]Duplication Rate:[/bold green] {report.duplication_rate:.1f}%",
        title="Research Results",
        border_style="green",
    ))
    
    if report.ats_distribution:
        table = Table(title="ATS Distribution")
        table.add_column("ATS Provider", style="cyan")
        table.add_column("Job Count", style="green")
        table.add_column("Percentage", style="yellow")
        
        total = sum(report.ats_distribution.values())
        for ats, count in sorted(report.ats_distribution.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total else 0
            table.add_row(ats, str(count), f"{pct:.1f}%")
        
        console.print(table)
    
    if report.results:
        table = Table(title="Duplicate Detection Results (Sample)")
        table.add_column("LinkedIn Job", style="cyan", max_width=35)
        table.add_column("Company", style="green")
        table.add_column("Is Duplicate?", style="magenta")
        table.add_column("Similarity", style="yellow")
        table.add_column("Match Method", style="blue")
        
        for result in report.results[:15]:
            is_dup = "[green]✓ Yes[/green]" if result.is_duplicate else "[red]✗ No[/red]"
            table.add_row(
                result.linkedin_job.title[:35],
                result.linkedin_job.company_name[:20],
                is_dup,
                f"{result.similarity_score:.0f}%",
                result.match_method or "-",
            )
        
        console.print(table)


def _save_results(report: ResearchReport, output_path: Path) -> None:
    """Save results to files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_path = output_path / f"research_report_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)
    console.print(f"[green]Saved JSON report to:[/green] {json_path}")
    
    if report.results:
        rows = []
        for result in report.results:
            job = result.linkedin_job
            rows.append({
                "job_id": job.job_id,
                "title": job.title,
                "company": job.company_name,
                "location": job.location,
                "easy_apply": job.easy_apply,
                "external_apply": job.external_apply,
                "ats_provider": job.ats_provider.value if job.ats_provider else None,
                "apply_url": job.apply_url,
                "is_duplicate": result.is_duplicate,
                "similarity_score": result.similarity_score,
                "match_method": result.match_method,
            })
        
        df = pd.DataFrame(rows)
        csv_path = output_path / f"jobs_analysis_{timestamp}.csv"
        df.to_csv(csv_path, index=False)
        console.print(f"[green]Saved CSV analysis to:[/green] {csv_path}")
    
    summary_path = output_path / f"summary_{timestamp}.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("LinkedIn Job Duplication Research Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Generated: {report.generated_at}\n\n")
        f.write(f"Total LinkedIn Jobs Analyzed: {report.total_linkedin_jobs_analyzed}\n")
        f.write(f"Career Page Jobs Found: {report.total_career_page_jobs_found}\n")
        f.write(f"Confirmed Duplicates: {report.confirmed_duplicates}\n")
        f.write(f"LinkedIn-Only Jobs: {report.linkedin_only_jobs}\n")
        f.write(f"Duplication Rate: {report.duplication_rate:.1f}%\n\n")
        
        f.write("Key Finding:\n")
        if report.duplication_rate > 70:
            f.write("Most LinkedIn jobs ARE duplicates from company career pages/ATS.\n")
        elif report.duplication_rate > 40:
            f.write("A significant portion of LinkedIn jobs are duplicates from career pages.\n")
        else:
            f.write("Many LinkedIn jobs appear to be unique or couldn't be matched to career pages.\n")
        
        f.write("\nATS Distribution:\n")
        for ats, count in report.ats_distribution.items():
            f.write(f"  - {ats}: {count} jobs\n")
    
    console.print(f"[green]Saved summary to:[/green] {summary_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Research LinkedIn job duplication from ATS/career pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py --keywords "data scientist" --location "New York"
    python main.py --keywords "product manager" --max-jobs 30
    python main.py --no-headless  # Run with visible browser
        """,
    )
    
    parser.add_argument(
        "--keywords",
        type=str,
        default="software engineer",
        help="Job search keywords (default: 'software engineer')",
    )
    parser.add_argument(
        "--location",
        type=str,
        default="",
        help="Job location filter",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=10,
        help="Maximum number of jobs to analyze (default: 10)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode for debugging",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory for output files (default: 'results')",
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_research(
            keywords=args.keywords,
            location=args.location,
            max_jobs=args.max_jobs,
            headless=not args.no_headless,
            output_dir=args.output_dir,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Research interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    main()
