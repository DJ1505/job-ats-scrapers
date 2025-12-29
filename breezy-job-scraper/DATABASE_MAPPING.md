# Database Mapping Documentation

## Overview

This document describes how the Breezy Job Scraper output maps to the PostgreSQL `ats_jobs` table schema. The mapping ensures seamless integration of scraped job data into your database.

## Schema Mapping

### Core Field Mapping

| Breezy Scraper Field | Database Field | Data Type | Notes |
|---------------------|----------------|-----------|-------|
| `position.id` | `job_id` | VARCHAR(255) | Unique job identifier from Breezy |
| `position.title` | `job_title` | TEXT | Job title |
| `position.company.name` | `company_name` | VARCHAR(255) | Company name |
| `position.description` | `job_description_raw` | TEXT | Raw job description |
| `position.description` | `job_description_cleaned` | TEXT | Cleaned description (same as raw for now) |
| `position.published_at` | `published_date` | TIMESTAMPTZ | Publication date |
| `position.expires_at` | `updated_date` | TIMESTAMPTZ | Last updated date |
| `position.application_url` | `job_url` / `apply_url` | TEXT | Application URL |
| `position.is_active` | `job_status` | VARCHAR(20) | Maps to 'active'/'expired' |

### Location Mapping

| Breezy Scraper Field | Database Field | Data Type | Mapping Logic |
|---------------------|----------------|-----------|--------------|
| `position.location.remote` | `work_location_type` | VARCHAR(50) | true → 'remote', false → 'on-site' |
| `position.location.remote` | `remote_scope` | VARCHAR(50) | true → 'anywhere', false → NULL |
| `position.location.city` | `city` | VARCHAR(255) | Direct mapping |
| `position.location.state` | `state` | VARCHAR(100) | Direct mapping |
| `position.location.country` | `country` | VARCHAR(100) | Direct mapping |
| Combined location fields | `job_location` | TEXT | "city, state, country" format |

### Compensation Mapping

| Breezy Scraper Field | Database Field | Data Type | Conversion |
|---------------------|----------------|-----------|------------|
| `position.salary_min` | `salary_min` | INTEGER | Float → Integer conversion |
| `position.salary_max` | `salary_max` | INTEGER | Float → Integer conversion |
| `position.currency` | `salary_currency` | VARCHAR(10) | Direct mapping |

### Skills and Requirements

| Breezy Scraper Field | Database Field | Data Type | Notes |
|---------------------|----------------|-----------|-------|
| `position.skills_required` | `required_skills` | TEXT[] | Array conversion |
| `position.benefits` | `preferred_skills` | TEXT[] | Stored as preferred skills |
| `position.responsibilities` | `key_responsibilities` | TEXT[] | Array conversion |
| `position.qualifications` | `certifications_required` | TEXT[] | Array conversion |

### Job Details

| Breezy Scraper Field | Database Field | Data Type | Mapping |
|---------------------|----------------|-----------|---------|
| `position.job_type` | `employment_type` | VARCHAR(50) | Enum mapping |
| `position.department` | `job_function` | VARCHAR(100) | Direct mapping |
| `position.experience_level` | `experience_level` | VARCHAR(50) | Direct mapping |
| `position.education_level` | `education_required` | VARCHAR(50) | Direct mapping |

### Metadata Fields

| Database Field | Value | Description |
|----------------|-------|-------------|
| `ats_source` | 'breezy' | Fixed ATS source identifier |
| `company_slug` | URL-derived | Extracted from company URL |
| `processing_status` | 'scraped' | Initial processing status |
| `sync_status` | 'pending' | Initial sync status |
| `job_status` | 'active'/'expired' | Based on position.is_active |
| `created_at` | Current timestamp | Record creation time |
| `updated_at` | Current timestamp | Record update time |
| `raw_data` | JSON object | Complete scraped data |

## Enum Mappings

### Employment Type Mapping

| Breezy Value | Database Value |
|--------------|----------------|
| 'full_time' | 'full-time' |
| 'part_time' | 'part-time' |
| 'contract' | 'contract' |
| 'internship' | 'internship' |
| 'temporary' | 'temporary' |

### Work Location Type Mapping

| Condition | Database Value |
|-----------|----------------|
| `location.remote = true` | 'remote' |
| `location.city AND location.state` | 'on-site' |
| Neither | 'not_specified' |

### Job Status Mapping

| Breezy Value | Database Value |
|--------------|----------------|
| `is_active = true` | 'active' |
| `is_active = false` | 'expired' |

## Data Transformation

### Enhanced Data Extraction

The scraper performs additional text analysis to extract:

1. **Experience Level**: Keywords in description (entry level, senior, etc.)
2. **Education Requirements**: Degree mentions (bachelor, master, PhD)
3. **Years of Experience**: Numeric patterns in description
4. **Benefits**: Mention of 401k, health insurance, etc.
5. **Visa Sponsorship**: Sponsorship mentions in description

### Data Validation

All database records are validated against:

- **AI Confidence**: Must be between 0.0 and 1.0
- **Experience Years**: Cannot be negative
- **Work Hours**: Must be between 0 and 168
- **Required Enums**: Must match database constraints
- **Unique Constraints**: `(ats_source, company_slug, job_id)`

## Usage Examples

### Basic Storage

```python
from src import DatabaseManager, BreezyEnhancedScraper

async def scrape_and_store():
    async with DatabaseManager(db_config) as db:
        async with BreezyEnhancedScraper() as scraper:
            result = await scraper.scrape_company_jobs("company-name")
            stored_ids = await db.store_scraping_result(result, "company-name")
            print(f"Stored {len(stored_ids)} jobs")
```

### Custom Mapping

```python
from src.database_models import DatabaseMapping, ATSJobRecord

# Map scraped position to database record
record = DatabaseMapping.map_position_to_ats_record(
    position, 
    company_slug="company-name",
    scraping_source="breezy"
)

# Store individual record
record_id = await db.store_job_record(record)
```

### Data Retrieval

```python
# Get all jobs for a company
jobs = await db.get_jobs_by_company("company-name")

# Search with filters
remote_jobs = await db.search_jobs(
    work_location_type="remote",
    experience_level="senior",
    limit=50
)
```

## Database Indexes

The schema includes optimized indexes for:

- **Primary Keys**: `id` (serial)
- **Unique Constraints**: `(ats_source, company_slug, job_id)`
- **Search Indexes**: `job_status`, `company_slug`, `work_location_type`
- **Array Indexes**: `required_skills`, `preferred_skills` (GIN)
- **Vector Indexes**: For embedding-based search (pgvector)
- **Composite Indexes**: For common query patterns

## Performance Considerations

### Bulk Operations

- Use `bulk_store_jobs()` for multiple records
- Transactions ensure atomicity
- Connection pooling manages resources

### Query Optimization

- Indexes support common filter combinations
- Partitioned indexes for active jobs
- Vector indexes for semantic search

### Data Quality

- Validation prevents invalid data
- Processing status tracks data lifecycle
- Error logging for debugging

## Integration Steps

1. **Set up Database**: Create PostgreSQL database with provided schema
2. **Configure Connection**: Update database credentials in config
3. **Run Scraper**: Scrape jobs using existing functionality
4. **Store Results**: Use database manager to persist data
5. **Query Data**: Use built-in search and retrieval methods

## Troubleshooting

### Common Issues

1. **Connection Errors**: Check database credentials and network
2. **Validation Errors**: Ensure data meets schema constraints
3. **Duplicate Records**: Handled by unique constraints automatically
4. **Performance**: Use appropriate indexes and bulk operations

### Debugging

- Enable debug logging for detailed operation logs
- Check `processing_status` for job lifecycle tracking
- Use `error_message` field for failure details
- Monitor `sync_status` for integration issues

This mapping ensures that all scraped Breezy job data is properly structured, validated, and stored in your PostgreSQL database with full search and analytics capabilities.
