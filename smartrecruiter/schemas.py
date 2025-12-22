"""Pydantic schemas for normalized SmartRecruiter job data."""
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
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class Department(BaseModel):
    """Department/team information."""
    id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None


class Company(BaseModel):
    """Company information."""
    identifier: str
    name: str


class Function(BaseModel):
    """Job function/category."""
    id: Optional[str] = None
    label: Optional[str] = None


class EmploymentType(BaseModel):
    """Employment type information."""
    id: Optional[str] = None
    label: Optional[str] = None


class ExperienceLevel(BaseModel):
    """Experience level information."""
    id: Optional[str] = None
    label: Optional[str] = None


class Industry(BaseModel):
    """Industry information."""
    id: Optional[str] = None
    label: Optional[str] = None


class CustomField(BaseModel):
    """Custom field data."""
    field_id: Optional[str] = None
    field_label: Optional[str] = None
    value_id: Optional[str] = None
    value_label: Optional[str] = None


class JobAdSection(BaseModel):
    """Job ad section content."""
    title: Optional[str] = None
    text: Optional[str] = None


class JobAd(BaseModel):
    """Job advertisement details."""
    sections: dict[str, JobAdSection] = Field(default_factory=dict)


class NormalizedJob(BaseModel):
    """Normalized job listing schema."""
    id: str
    uuid: Optional[str] = None
    slug: str
    title: str
    description: Optional[str] = None
    requirements: Optional[str] = None
    company: Company
    department: Optional[Department] = None
    function: Optional[Function] = None
    locations: list[Location] = Field(default_factory=list)
    employment_type: Optional[EmploymentType] = None
    experience_level: Optional[ExperienceLevel] = None
    industry: Optional[Industry] = None
    remote_option: Optional[bool] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    created_at: Optional[datetime] = None
    released_date: Optional[datetime] = None
    active: bool = True
    careers_url: Optional[str] = None
    apply_url: Optional[str] = None
    job_ad: Optional[JobAd] = None
    custom_fields: list[CustomField] = Field(default_factory=list)
    creator_name: Optional[str] = None
    creator_avatar: Optional[str] = None
    raw_data: Optional[dict] = Field(default=None, exclude=True)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }
