"""ATS provider detection from URLs and page content."""
import re
from urllib.parse import urlparse
from schemas import ATSProvider


ATS_URL_PATTERNS: dict[ATSProvider, list[str]] = {
    ATSProvider.WORKDAY: [
        r"myworkdayjobs\.com",
        r"wd\d+\.myworkdaysite\.com",
        r"wd\d+\.myworkdayjobs\.com",
        r"workday\.com/.*careers",
        r"\.wd\d+\.",
    ],
    ATSProvider.GREENHOUSE: [
        r"boards\.greenhouse\.io",
        r"job-boards\.greenhouse\.io",
        r"greenhouse\.io/.*embed",
    ],
    ATSProvider.LEVER: [
        r"jobs\.lever\.co",
        r"lever\.co/.*apply",
    ],
    ATSProvider.ICIMS: [
        r"careers-.*\.icims\.com",
        r"icims\.com",
        r"jobs\..*\.com/.*icims",
    ],
    ATSProvider.TALEO: [
        r"taleo\.net",
        r"oracle\.com/.*taleo",
        r"taleo\.com",
    ],
    ATSProvider.BAMBOO_HR: [
        r".*\.bamboohr\.com/careers",
        r".*\.bamboohr\.com/jobs",
    ],
    ATSProvider.JOBVITE: [
        r"jobs\.jobvite\.com",
        r".*\.jobvite\.com",
    ],
    ATSProvider.SMART_RECRUITERS: [
        r"jobs\.smartrecruiters\.com",
        r"careers\.smartrecruiters\.com",
    ],
    ATSProvider.ASHBY: [
        r"jobs\.ashbyhq\.com",
        r".*\.ashbyhq\.com",
    ],
}


def detect_ats_from_url(url: str) -> ATSProvider:
    """Detect ATS provider from URL patterns."""
    if not url:
        return ATSProvider.UNKNOWN
    
    url_lower = url.lower()
    
    for provider, patterns in ATS_URL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return provider
    
    return ATSProvider.UNKNOWN


def detect_ats_from_redirect_chain(urls: list[str]) -> ATSProvider:
    """Detect ATS from a chain of redirect URLs."""
    for url in urls:
        provider = detect_ats_from_url(url)
        if provider != ATSProvider.UNKNOWN:
            return provider
    return ATSProvider.UNKNOWN


def extract_career_page_base_url(apply_url: str) -> str | None:
    """Extract the base career page URL from an apply URL."""
    if not apply_url:
        return None
    
    parsed = urlparse(apply_url)
    
    for provider, patterns in ATS_URL_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, apply_url.lower()):
                return f"{parsed.scheme}://{parsed.netloc}"
    
    if parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    
    return None


def is_ats_url(url: str) -> bool:
    """Check if URL belongs to a known ATS provider."""
    return detect_ats_from_url(url) != ATSProvider.UNKNOWN
