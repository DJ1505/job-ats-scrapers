"""
LinkedIn Job Ingestion Pipeline

Production-grade, API-first job ingestion system for LinkedIn jobs.
Uses network interception (no login), ATS JSON APIs, and safe scraping practices.

ARCHITECTURE:
- LinkedIn Guest APIs are the PRIMARY data source
- ATS JSON APIs (Greenhouse, Lever, Workday, etc.) for external jobs
- No DOM scraping for job data
- Immediate abort on login/captcha detection

Usage:
    python main.py --keywords "software engineer" --location "San Francisco" --max-jobs 20
    python main.py --keywords "data scientist" --no-ats  # Skip ATS fetching
"""
import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import pandas as pd

from schemas import (
    JobPosting,
    JobOrigin,
    PipelineResult,
    ATSProvider,
    BlockReason,
)
from job_pipeline import JobIngestionPipeline, run_pipeline

console = Console()


async def run_ingestion(
    keywords: str = "software engineer",
    location: str = "",
    max_jobs: int = 10,
    headless: bool = True,
    output_dir: str = "results",
    fetch_ats: bool = True,
) -> PipelineResult:
    """
    Run the job ingestion pipeline.
    
    Pipeline steps:
    1. Discover jobs via LinkedIn Guest API (network interception)
    2. Classify jobs by origin (ATS vs LINKEDIN_NATIVE)
    3. For ATS jobs: fetch directly from ATS JSON APIs
    4. Deduplicate and normalize all jobs
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    console.print(Panel.fit(
        "[bold blue]LinkedIn Job Ingestion Pipeline[/bold blue]\n"
        f"Keywords: {keywords or 'Any'}\n"
        f"Location: {location or 'Any'}\n"
        f"Max Jobs: {max_jobs}\n"
        f"Fetch ATS: {fetch_ats}",
        title="Pipeline Configuration",
    ))
    
    result: PipelineResult
    
    async with JobIngestionPipeline(
        headless=headless,
        fetch_ats_jobs=fetch_ats,
    ) as pipeline:
        result = await pipeline.run(
            keywords=keywords,
            location=location,
            max_jobs=max_jobs,
        )
    
    if not result.jobs:
        if result.scraper_state.is_blocked:
            console.print("[red]Pipeline was blocked. Partial results may be available.[/red]")
            console.print(f"[red]Block reason: {result.scraper_state.block_reason}[/red]")
        else:
            console.print("[yellow]No jobs found. Try different search terms.[/yellow]")
        return result
    
    _display_jobs_table(result.jobs)
    _display_pipeline_results(result)
    _save_pipeline_results(result, output_path)
    
    return result


def _display_jobs_table(jobs: list[JobPosting]) -> None:
    """Display jobs in a table."""
    table = Table(title="Jobs Extracted", show_lines=True)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Company", style="green")
    table.add_column("Location", style="yellow")
    table.add_column("Origin", style="magenta")
    table.add_column("ATS", style="blue")
    table.add_column("Method", style="dim")
    
    for job in jobs[:25]:
        origin = "[green]ATS[/green]" if job.job_origin == JobOrigin.ATS else "[blue]Native[/blue]"
        ats = job.ats_provider.value if job.ats_provider else "-"
        table.add_row(
            job.title[:40],
            job.company_name[:25],
            (job.location or "-")[:20],
            origin,
            ats,
            job.extraction_method,
        )
    
    if len(jobs) > 25:
        table.add_row("...", f"({len(jobs) - 25} more)", "...", "...", "...", "...")
    
    console.print(table)


def _display_pipeline_results(result: PipelineResult) -> None:
    """Display pipeline results."""
    ats_count = sum(1 for j in result.jobs if j.job_origin == JobOrigin.ATS)
    native_count = sum(1 for j in result.jobs if j.job_origin == JobOrigin.LINKEDIN_NATIVE)
    
    console.print("\n")
    console.print(Panel.fit(
        f"[bold]Total Jobs Extracted:[/bold] {len(result.jobs)}\n"
        f"[bold]ATS Jobs:[/bold] {ats_count}\n"
        f"[bold]LinkedIn-Native Jobs:[/bold] {native_count}\n"
        f"[bold]ATS Companies Detected:[/bold] {len(result.ats_companies)}\n"
        f"[bold]LinkedIn-Native Companies:[/bold] {len(result.linkedin_native_companies)}",
        title="Pipeline Results",
        border_style="green",
    ))
    
    ats_distribution: dict[str, int] = {}
    for job in result.jobs:
        if job.ats_provider and job.ats_provider != ATSProvider.UNKNOWN:
            ats_name = job.ats_provider.value
            ats_distribution[ats_name] = ats_distribution.get(ats_name, 0) + 1
    
    if ats_distribution:
        table = Table(title="ATS Distribution")
        table.add_column("ATS Provider", style="cyan")
        table.add_column("Job Count", style="green")
        table.add_column("Percentage", style="yellow")
        
        total = sum(ats_distribution.values())
        for ats, count in sorted(ats_distribution.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total else 0
            table.add_row(ats, str(count), f"{pct:.1f}%")
        
        console.print(table)
    
    origin_distribution: dict[str, int] = {}
    for job in result.jobs:
        origin = job.job_origin.value
        origin_distribution[origin] = origin_distribution.get(origin, 0) + 1
    
    if origin_distribution:
        table = Table(title="Job Origin Distribution")
        table.add_column("Origin", style="cyan")
        table.add_column("Count", style="green")
        table.add_column("Percentage", style="yellow")
        
        total = len(result.jobs)
        for origin, count in sorted(origin_distribution.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total else 0
            table.add_row(origin, str(count), f"{pct:.1f}%")
        
        console.print(table)
    
    if result.scraper_state.is_blocked:
        console.print(Panel.fit(
            f"[red bold]Scraper was blocked![/red bold]\n"
            f"Reason: {result.scraper_state.block_reason.value if result.scraper_state.block_reason else 'Unknown'}",
            title="⚠️ Block Detected",
            border_style="red",
        ))
    
    if result.errors:
        console.print(f"\n[yellow]Errors encountered: {len(result.errors)}[/yellow]")
        for error in result.errors[:5]:
            console.print(f"  - {error}")


def _save_pipeline_results(result: PipelineResult, output_path: Path) -> None:
    """Save pipeline results to files."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_path = output_path / f"pipeline_result_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result.model_dump(mode="json"), f, indent=2, default=str)
    console.print(f"[green]Saved JSON report to:[/green] {json_path}")
    
    if result.jobs:
        rows = []
        for job in result.jobs:
            rows.append({
                "job_id": job.job_id,
                "title": job.title,
                "company_name": job.company_name,
                "location": job.location,
                "apply_url": job.apply_url,
                "ats_provider": job.ats_provider.value if job.ats_provider else None,
                "job_origin": job.job_origin.value,
                "source_url": job.source_url,
                "extracted_at": job.extracted_at.isoformat() if job.extracted_at else None,
                "extraction_method": job.extraction_method,
                "easy_apply": job.easy_apply,
                "external_apply": job.external_apply,
            })
        
        df = pd.DataFrame(rows)
        csv_path = output_path / f"jobs_{timestamp}.csv"
        df.to_csv(csv_path, index=False)
        console.print(f"[green]Saved jobs CSV to:[/green] {csv_path}")
    
    ats_count = sum(1 for j in result.jobs if j.job_origin == JobOrigin.ATS)
    native_count = sum(1 for j in result.jobs if j.job_origin == JobOrigin.LINKEDIN_NATIVE)
    
    summary_path = output_path / f"summary_{timestamp}.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("LinkedIn Job Ingestion Pipeline Summary\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Generated: {result.completed_at}\n\n")
        f.write(f"Total Jobs Extracted: {len(result.jobs)}\n")
        f.write(f"ATS Jobs: {ats_count}\n")
        f.write(f"LinkedIn-Native Jobs: {native_count}\n")
        f.write(f"ATS Companies Detected: {len(result.ats_companies)}\n\n")
        
        if result.ats_companies:
            f.write("ATS Companies:\n")
            for company_key, info in result.ats_companies.items():
                f.write(f"  - {info.company_name}: {info.ats_provider.value} ({info.job_count} jobs)\n")
        
        if result.linkedin_native_companies:
            f.write(f"\nLinkedIn-Native Companies ({len(result.linkedin_native_companies)}):\n")
            for company in result.linkedin_native_companies[:10]:
                f.write(f"  - {company}\n")
            if len(result.linkedin_native_companies) > 10:
                f.write(f"  ... and {len(result.linkedin_native_companies) - 10} more\n")
        
        if result.scraper_state.is_blocked:
            f.write(f"\n⚠️ BLOCKED: {result.scraper_state.block_reason}\n")
        
        if result.errors:
            f.write(f"\nErrors ({len(result.errors)}):\n")
            for error in result.errors:
                f.write(f"  - {error}\n")
    
    console.print(f"[green]Saved summary to:[/green] {summary_path}")


def main():
    parser = argparse.ArgumentParser(
        description="LinkedIn Job Ingestion Pipeline - API-first job extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py --keywords "data scientist" --location "New York"
    python main.py --keywords "product manager" --max-jobs 30
    python main.py --no-headless  # Run with visible browser
    python main.py --no-ats  # Skip ATS job fetching
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
        help="Maximum number of jobs to extract (default: 10)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible mode for debugging",
    )
    parser.add_argument(
        "--no-ats",
        action="store_true",
        help="Skip fetching jobs from ATS APIs",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results",
        help="Directory for output files (default: 'results')",
    )
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_ingestion(
            keywords=args.keywords,
            location=args.location,
            max_jobs=args.max_jobs,
            headless=not args.no_headless,
            output_dir=args.output_dir,
            fetch_ats=not args.no_ats,
        ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    main()
