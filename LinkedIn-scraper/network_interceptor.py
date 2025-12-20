"""Network interception utilities for capturing API responses."""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Any
from playwright.async_api import Page, Response, Route

from schemas import BlockReason, ScraperState


@dataclass
class InterceptedData:
    """Container for intercepted network data."""
    jobs_api_responses: list[dict] = field(default_factory=list)
    job_details: list[dict] = field(default_factory=list)
    company_data: list[dict] = field(default_factory=list)
    apply_urls: dict[str, str] = field(default_factory=dict)  # job_id -> apply_url
    redirect_chains: dict[str, list[str]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    
    def clear(self):
        """Clear all intercepted data."""
        self.jobs_api_responses.clear()
        self.job_details.clear()
        self.company_data.clear()
        self.apply_urls.clear()
        self.redirect_chains.clear()
        self.errors.clear()


LINKEDIN_API_PATTERNS = [
    r"/voyager/api/jobs/jobPostings",
    r"/voyager/api/jobs/jobDetails",
    r"/voyager/api/graphql.*job",
    r"/voyager/api/entities/companies",
    r"/jobs-guest/jobs/api/",
    r"/jobs/api/",
    r"/voyager/api/search/dash",
    r"/voyager/api/jobs/search",
]

BLOCK_URL_PATTERNS = {
    BlockReason.LOGIN_REQUIRED: [
        r"/login",
        r"/signin",
        r"/sign-in",
        r"/uas/login",
    ],
    BlockReason.AUTHWALL: [
        r"/authwall",
        r"/auth-wall",
    ],
    BlockReason.CHECKPOINT: [
        r"/checkpoint",
        r"/security-check",
    ],
    BlockReason.CAPTCHA_DETECTED: [
        r"/captcha",
        r"/challenge",
        r"/security-verification",
        r"challenge\.linkedin\.com",
    ],
}


def matches_linkedin_api(url: str) -> bool:
    """Check if URL matches LinkedIn jobs API patterns."""
    for pattern in LINKEDIN_API_PATTERNS:
        if re.search(pattern, url):
            return True
    return False


def detect_block_from_url(url: str) -> BlockReason | None:
    """Detect if URL indicates a block condition."""
    url_lower = url.lower()
    for reason, patterns in BLOCK_URL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return reason
    return None


def detect_block_from_response(response: Response) -> BlockReason | None:
    """Detect block conditions from response status/headers."""
    if response.status == 429:
        return BlockReason.RATE_LIMITED
    if response.status == 401 or response.status == 403:
        return BlockReason.LOGIN_REQUIRED
    
    block_in_url = detect_block_from_url(response.url)
    if block_in_url:
        return block_in_url
    
    return None


async def setup_network_interception(
    page: Page,
    intercepted: InterceptedData,
    scraper_state: ScraperState | None = None,
    on_job_data: Callable[[dict], None] | None = None,
    on_block_detected: Callable[[BlockReason], None] | None = None,
) -> None:
    """Set up network interception for LinkedIn API calls with block detection."""
    
    async def handle_response(response: Response) -> None:
        url = response.url
        
        if scraper_state:
            scraper_state.requests_made += 1
            scraper_state.last_request_time = datetime.utcnow()
        
        block_reason = detect_block_from_response(response)
        if block_reason:
            if scraper_state:
                scraper_state.is_blocked = True
                scraper_state.block_reason = block_reason
            if on_block_detected:
                on_block_detected(block_reason)
            return
        
        if not matches_linkedin_api(url):
            return
        
        try:
            if response.status == 200:
                content_type = response.headers.get("content-type", "")
                
                if "application/json" in content_type:
                    body = await response.json()
                    
                    if scraper_state:
                        scraper_state.api_responses_captured += 1
                    
                    if "/jobDetails" in url or "jobPosting" in url:
                        intercepted.job_details.append({
                            "url": url,
                            "data": body,
                        })
                        _extract_apply_urls(body, intercepted)
                    else:
                        intercepted.jobs_api_responses.append({
                            "url": url,
                            "data": body,
                        })
                    
                    if on_job_data:
                        on_job_data(body)
                        
        except Exception as e:
            error_msg = f"Error processing {url}: {str(e)}"
            intercepted.errors.append(error_msg)
            if scraper_state:
                scraper_state.errors.append(error_msg)
    
    page.on("response", handle_response)


def _extract_apply_urls(data: dict, intercepted: InterceptedData) -> None:
    """Extract apply URLs from job detail response."""
    if not isinstance(data, dict):
        return
    
    for item in data.get("included", []):
        if not isinstance(item, dict):
            continue
        
        entity_urn = item.get("entityUrn", "")
        job_id = entity_urn.split(":")[-1] if entity_urn else None
        
        apply_url = extract_apply_url_from_job(item)
        if job_id and apply_url:
            intercepted.apply_urls[job_id] = apply_url


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
