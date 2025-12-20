"""Pydantic schemas for normalized Recruitee job data."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Location(BaseModel):
    """Normalized location data."""
    city: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    region: Optional[str] = None
    remote: bool = False


class Department(BaseModel):
    """Department/team information."""
    id: Optional[int] = None
    name: Optional[str] = None


class NormalizedJob(BaseModel):
    """Normalized job listing schema."""
    id: int
    slug: str
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    department: Optional[Department] = None
    locations: list[Location] = Field(default_factory=list)
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    education_level: Optional[str] = None
    remote_option: Optional[str | bool] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    careers_url: Optional[str] = None
    apply_url: Optional[str] = None
    company_slug: str
    raw_data: Optional[dict] = Field(default=None, exclude=True)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
