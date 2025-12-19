"""Job comparison and duplication detection logic."""
from fuzzywuzzy import fuzz
from rich.console import Console

from schemas import JobPosting, DuplicationResult, CompanyInfo, ATSProvider

console = Console()


class JobComparator:
    """Compare jobs between LinkedIn and career pages to detect duplicates."""
    
    TITLE_SIMILARITY_THRESHOLD = 85
    LOCATION_SIMILARITY_THRESHOLD = 70
    DESCRIPTION_MATCH_BOOST = 20
    
    def __init__(self):
        self.company_stats: dict[str, CompanyInfo] = {}
    
    def compare_jobs(
        self,
        linkedin_job: JobPosting,
        career_page_jobs: list[JobPosting],
    ) -> DuplicationResult:
        """Compare a LinkedIn job against career page jobs to find duplicates."""
        best_match: JobPosting | None = None
        best_score = 0.0
        match_method = None
        
        for cp_job in career_page_jobs:
            if linkedin_job.company_name.lower() != cp_job.company_name.lower():
                continue
            
            score, method = self._calculate_similarity(linkedin_job, cp_job)
            
            if score > best_score:
                best_score = score
                best_match = cp_job
                match_method = method
        
        is_duplicate = best_score >= self.TITLE_SIMILARITY_THRESHOLD
        
        return DuplicationResult(
            linkedin_job=linkedin_job,
            career_page_job=best_match,
            is_duplicate=is_duplicate,
            similarity_score=best_score,
            match_method=match_method,
        )
    
    def _calculate_similarity(
        self,
        job1: JobPosting,
        job2: JobPosting,
    ) -> tuple[float, str]:
        """Calculate similarity score between two jobs."""
        title_score = fuzz.ratio(
            self._normalize_title(job1.title),
            self._normalize_title(job2.title),
        )
        
        method = "title_match"
        
        if job1.description_hash and job2.description_hash:
            if job1.description_hash == job2.description_hash:
                return 100.0, "exact_description_match"
            
            if job1.description_snippet and job2.description_snippet:
                desc_score = fuzz.partial_ratio(
                    job1.description_snippet[:200],
                    job2.description_snippet[:200],
                )
                if desc_score > 80:
                    title_score = min(100, title_score + self.DESCRIPTION_MATCH_BOOST)
                    method = "title_and_description_match"
        
        if job1.location and job2.location:
            loc_score = fuzz.ratio(
                self._normalize_location(job1.location),
                self._normalize_location(job2.location),
            )
            if loc_score >= self.LOCATION_SIMILARITY_THRESHOLD:
                title_score = min(100, title_score + 5)
                method = f"{method}_with_location"
        
        if job1.job_id == job2.job_id:
            return 100.0, "exact_id_match"
        
        return float(title_score), method
    
    def _normalize_title(self, title: str) -> str:
        """Normalize job title for comparison."""
        title = title.lower().strip()
        
        remove_patterns = [
            r"\s*-\s*remote",
            r"\s*\(remote\)",
            r"\s*\(hybrid\)",
            r"\s*-\s*hybrid",
            r"\s*\(.*location.*\)",
            r"\s*#\d+",
            r"\s*req\s*#?\d+",
            r"\s*job\s*id:?\s*\d+",
        ]
        
        import re
        for pattern in remove_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)
        
        return title.strip()
    
    def _normalize_location(self, location: str) -> str:
        """Normalize location for comparison."""
        location = location.lower().strip()
        
        location = location.replace("remote", "").strip()
        location = location.replace("hybrid", "").strip()
        
        parts = location.split(",")
        if parts:
            location = parts[0].strip()
        
        return location
    
    def update_company_stats(
        self,
        company_name: str,
        linkedin_jobs: list[JobPosting],
        career_page_jobs: list[JobPosting],
        duplicates: int,
        ats_provider: ATSProvider | None = None,
    ) -> CompanyInfo:
        """Update statistics for a company."""
        if company_name not in self.company_stats:
            self.company_stats[company_name] = CompanyInfo(name=company_name)
        
        info = self.company_stats[company_name]
        info.jobs_on_linkedin = len(linkedin_jobs)
        info.jobs_on_career_page = len(career_page_jobs)
        info.duplicates_found = duplicates
        info.detected_ats = ats_provider
        
        return info
    
    def batch_compare(
        self,
        linkedin_jobs: list[JobPosting],
        career_page_jobs: list[JobPosting],
    ) -> list[DuplicationResult]:
        """Compare multiple LinkedIn jobs against career page jobs."""
        results: list[DuplicationResult] = []
        
        jobs_by_company: dict[str, list[JobPosting]] = {}
        for job in career_page_jobs:
            company = job.company_name.lower()
            if company not in jobs_by_company:
                jobs_by_company[company] = []
            jobs_by_company[company].append(job)
        
        for linkedin_job in linkedin_jobs:
            company = linkedin_job.company_name.lower()
            company_jobs = jobs_by_company.get(company, [])
            
            result = self.compare_jobs(linkedin_job, company_jobs)
            results.append(result)
        
        return results
