"""Network interception utilities for capturing API responses."""
import json
import re
from dataclasses import dataclass, field
from typing import Callable, Any
from playwright.async_api import Page, Response, Route


@dataclass
class InterceptedData:
    """Container for intercepted network data."""
    jobs_api_responses: list[dict] = field(default_factory=list)
    company_data: list[dict] = field(default_factory=list)
    apply_urls: list[str] = field(default_factory=list)
    redirect_chains: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


LINKEDIN_API_PATTERNS = [
    r"/voyager/api/jobs/jobPostings",
    r"/voyager/api/jobs/jobDetails",
    r"/voyager/api/graphql.*jobPosting",
    r"/voyager/api/entities/companies",
    r"/jobs-guest/jobs/api/",
    r"/jobs/api/",
]


def matches_linkedin_api(url: str) -> bool:
    """Check if URL matches LinkedIn jobs API patterns."""
    for pattern in LINKEDIN_API_PATTERNS:
        if re.search(pattern, url):
            return True
    return False


async def setup_network_interception(
    page: Page,
    intercepted: InterceptedData,
    on_job_data: Callable[[dict], None] | None = None,
) -> None:
    """Set up network interception for LinkedIn API calls."""
    
    async def handle_response(response: Response) -> None:
        url = response.url
        
        if not matches_linkedin_api(url):
            return
        
        try:
            if response.status == 200:
                content_type = response.headers.get("content-type", "")
                
                if "application/json" in content_type:
                    body = await response.json()
                    intercepted.jobs_api_responses.append({
                        "url": url,
                        "data": body,
                    })
                    
                    if on_job_data:
                        on_job_data(body)
                        
        except Exception as e:
            intercepted.errors.append(f"Error processing {url}: {str(e)}")
    
    page.on("response", handle_response)


async def capture_redirect_chain(
    page: Page,
    start_url: str,
    intercepted: InterceptedData,
    max_redirects: int = 10,
) -> list[str]:
    """Capture the redirect chain when navigating to a URL."""
    chain: list[str] = [start_url]
    redirect_count = 0
    
    async def handle_response(response: Response) -> None:
        nonlocal redirect_count
        if response.request.redirected_from and redirect_count < max_redirects:
            chain.append(response.url)
            redirect_count += 1
    
    page.on("response", handle_response)
    
    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
        chain.append(page.url)
    except Exception as e:
        intercepted.errors.append(f"Redirect capture error: {str(e)}")
    
    intercepted.redirect_chains[start_url] = list(set(chain))
    return chain


def extract_jobs_from_api_response(response_data: dict) -> list[dict]:
    """Extract job postings from LinkedIn API response structure."""
    jobs = []
    
    if not isinstance(response_data, dict):
        return jobs
    
    if "included" in response_data:
        for item in response_data.get("included", []):
            if isinstance(item, dict):
                entity_urn = item.get("entityUrn", "") or item.get("$recipeType", "")
                if "jobPosting" in entity_urn.lower() or "fsd_jobPosting" in str(item):
                    jobs.append(item)
    
    if "elements" in response_data:
        for element in response_data.get("elements", []):
            if isinstance(element, dict):
                jobs.append(element)
    
    if "data" in response_data:
        data = response_data["data"]
        if isinstance(data, dict):
            for key, value in data.items():
                if "job" in key.lower() and isinstance(value, (list, dict)):
                    if isinstance(value, list):
                        jobs.extend([v for v in value if isinstance(v, dict)])
                    else:
                        jobs.append(value)
    
    return jobs


def extract_apply_url_from_job(job_data: dict) -> str | None:
    """Extract apply URL from job data."""
    apply_url_keys = [
        "applyUrl",
        "applyMethod",
        "externalApplyUrl",
        "companyApplyUrl",
        "offSiteApplyUrl",
    ]
    
    for key in apply_url_keys:
        if key in job_data:
            value = job_data[key]
            if isinstance(value, str) and value.startswith("http"):
                return value
            if isinstance(value, dict):
                url = value.get("url") or value.get("companyApplyUrl")
                if url:
                    return url
    
    if "applyMethod" in job_data:
        method = job_data["applyMethod"]
        if isinstance(method, dict):
            if "com.linkedin.voyager.jobs.OffsiteApply" in str(method.get("$type", "")):
                return method.get("companyApplyUrl")
    
    return None
