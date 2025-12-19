"""Schema definitions for job data extraction."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class JobSource(str, Enum):
    LINKEDIN = "linkedin"
    CAREER_PAGE = "career_page"
    ATS = "ats"


class ATSProvider(str, Enum):
    WORKDAY = "workday"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ICIMS = "icims"
    TALEO = "taleo"
    BAMBOO_HR = "bamboohr"
    JOBVITE = "jobvite"
    SMART_RECRUITERS = "smartrecruiters"
    ASHBY = "ashby"
    UNKNOWN = "unknown"


class JobPosting(BaseModel):
    """Schema for extracted job posting data."""
    job_id: str = Field(..., description="Unique job identifier")
    title: str = Field(..., description="Job title")
    company_name: str = Field(..., description="Company name")
    location: Optional[str] = Field(None, description="Job location")
    description_hash: Optional[str] = Field(None, description="Hash of job description for comparison")
    description_snippet: Optional[str] = Field(None, description="First 500 chars of description")
    posted_date: Optional[datetime] = Field(None, description="When job was posted")
    source: JobSource = Field(..., description="Where this job was found")
    source_url: str = Field(..., description="URL where job was found")
    apply_url: Optional[str] = Field(None, description="Application URL")
    ats_provider: Optional[ATSProvider] = Field(None, description="Detected ATS provider")
    company_career_url: Optional[str] = Field(None, description="Company career page URL")
    easy_apply: bool = Field(False, description="Whether Easy Apply is available")
    external_apply: bool = Field(False, description="Whether it redirects to external site")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class CompanyInfo(BaseModel):
    """Schema for company information."""
    name: str
    linkedin_url: Optional[str] = None
    career_page_url: Optional[str] = None
    detected_ats: Optional[ATSProvider] = None
    jobs_on_linkedin: int = 0
    jobs_on_career_page: int = 0
    duplicates_found: int = 0


class DuplicationResult(BaseModel):
    """Schema for job duplication analysis result."""
    linkedin_job: JobPosting
    career_page_job: Optional[JobPosting] = None
    is_duplicate: bool = False
    similarity_score: float = 0.0
    match_method: Optional[str] = None


class ResearchReport(BaseModel):
    """Schema for final research report."""
    total_linkedin_jobs_analyzed: int = 0
    total_career_page_jobs_found: int = 0
    confirmed_duplicates: int = 0
    linkedin_only_jobs: int = 0
    duplication_rate: float = 0.0
    companies_analyzed: list[CompanyInfo] = Field(default_factory=list)
    ats_distribution: dict[str, int] = Field(default_factory=dict)
    results: list[DuplicationResult] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
