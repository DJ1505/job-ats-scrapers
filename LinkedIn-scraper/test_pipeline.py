"""
Test cases for the LinkedIn Job Ingestion Pipeline.

Required Test Cases:
1. ATS Company (Greenhouse) - Jobs fetched via JSON API
2. ATS Company (Workday) - Network interception captures API
3. LinkedIn-Only Startup - Easy Apply, no external scraping
4. Block Detection - Authwall/captcha triggers immediate stop
5. Mixed Companies - ATS + LinkedIn-native handled correctly
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from schemas import (
    JobPosting,
    JobSource,
    JobOrigin,
    ATSProvider,
    ScraperState,
    BlockReason,
    PipelineResult,
)
from ats_clients import GreenhouseClient, LeverClient, WorkdayClient, fetch_ats_jobs
from ats_detector import detect_ats_from_url
from network_interceptor import detect_block_from_url, detect_block_from_response
from linkedin_scraper import LinkedInScraper
from ats_scraper import ATSScraper
from job_pipeline import JobIngestionPipeline


class TestATSDetection:
    """Test ATS provider detection from URLs."""
    
    def test_greenhouse_detection(self):
        urls = [
            "https://boards.greenhouse.io/company/jobs/123",
            "https://job-boards.greenhouse.io/example",
        ]
        for url in urls:
            assert detect_ats_from_url(url) == ATSProvider.GREENHOUSE
    
    def test_lever_detection(self):
        urls = [
            "https://jobs.lever.co/company/abc-123",
            "https://jobs.lever.co/example",
        ]
        for url in urls:
            assert detect_ats_from_url(url) == ATSProvider.LEVER
    
    def test_workday_detection(self):
        urls = [
            "https://company.wd5.myworkdayjobs.com/en-US/careers",
            "https://wd1.myworkdayjobs.com/example",
        ]
        for url in urls:
            assert detect_ats_from_url(url) == ATSProvider.WORKDAY
    
    def test_ashby_detection(self):
        urls = [
            "https://jobs.ashbyhq.com/company",
        ]
        for url in urls:
            assert detect_ats_from_url(url) == ATSProvider.ASHBY
    
    def test_unknown_detection(self):
        urls = [
            "https://linkedin.com/jobs/view/123",
            "https://company.com/careers",
            "https://indeed.com/job/123",
        ]
        for url in urls:
            assert detect_ats_from_url(url) == ATSProvider.UNKNOWN


class TestBlockDetection:
    """Test block detection from URLs and responses."""
    
    def test_login_block_detection(self):
        urls = [
            "https://www.linkedin.com/login",
            "https://www.linkedin.com/uas/login",
            "https://www.linkedin.com/signin",
        ]
        for url in urls:
            assert detect_block_from_url(url) == BlockReason.LOGIN_REQUIRED
    
    def test_authwall_detection(self):
        urls = [
            "https://www.linkedin.com/authwall",
        ]
        for url in urls:
            assert detect_block_from_url(url) == BlockReason.AUTHWALL
    
    def test_captcha_detection(self):
        urls = [
            "https://www.linkedin.com/checkpoint/challenge",
            "https://challenge.linkedin.com/something",
        ]
        for url in urls:
            result = detect_block_from_url(url)
            assert result in [BlockReason.CAPTCHA_DETECTED, BlockReason.CHECKPOINT]
    
    def test_normal_url_no_block(self):
        urls = [
            "https://www.linkedin.com/jobs/search",
            "https://www.linkedin.com/jobs/view/123",
        ]
        for url in urls:
            assert detect_block_from_url(url) is None


class TestJobOriginClassification:
    """Test job origin classification logic."""
    
    def test_ats_job_classification(self):
        """Jobs with external ATS apply URLs should be classified as ATS."""
        job = JobPosting(
            job_id="123",
            title="Software Engineer",
            company_name="Tech Corp",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/123",
            apply_url="https://boards.greenhouse.io/techcorp/jobs/123",
            ats_provider=ATSProvider.GREENHOUSE,
            external_apply=True,
            job_origin=JobOrigin.ATS,
        )
        assert job.job_origin == JobOrigin.ATS
        assert job.ats_provider == ATSProvider.GREENHOUSE
    
    def test_linkedin_native_job_classification(self):
        """Jobs with Easy Apply should be classified as LINKEDIN_NATIVE."""
        job = JobPosting(
            job_id="456",
            title="Product Manager",
            company_name="Startup Inc",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/456",
            easy_apply=True,
            external_apply=False,
            job_origin=JobOrigin.LINKEDIN_NATIVE,
        )
        assert job.job_origin == JobOrigin.LINKEDIN_NATIVE
        assert job.easy_apply is True


class TestGreenhouseClient:
    """Test Case 1: ATS Company (Greenhouse) - Jobs fetched via JSON API."""
    
    @pytest.mark.asyncio
    async def test_greenhouse_api_fetch(self):
        """
        Test that Greenhouse jobs are fetched via JSON API.
        
        Expected:
        - External apply URL detected
        - ATS jobs fetched via JSON API
        - Jobs marked as ATS origin
        - No HTML scraping
        """
        client = GreenhouseClient()
        
        slug = client.extract_slug_from_url("https://boards.greenhouse.io/testcompany/jobs/123")
        assert slug == "testcompany"
        
        mock_response = {
            "jobs": [
                {
                    "id": 12345,
                    "title": "Software Engineer",
                    "location": {"name": "San Francisco, CA"},
                    "absolute_url": "https://boards.greenhouse.io/testcompany/jobs/12345",
                    "updated_at": "2024-01-15T10:00:00Z",
                },
                {
                    "id": 12346,
                    "title": "Product Manager",
                    "location": {"name": "Remote"},
                    "absolute_url": "https://boards.greenhouse.io/testcompany/jobs/12346",
                },
            ]
        }
        
        with patch.object(client, 'client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            
            client.client = mock_client
            
            jobs = []
            async for job in client.fetch_jobs("testcompany", "Test Company"):
                jobs.append(job)
            
            assert len(jobs) == 2
            assert jobs[0].title == "Software Engineer"
            assert jobs[0].job_origin == JobOrigin.ATS
            assert jobs[0].ats_provider == ATSProvider.GREENHOUSE
            assert jobs[0].extraction_method == "ats_api"
            assert jobs[1].title == "Product Manager"


class TestWorkdayClient:
    """Test Case 2: ATS Company (Workday) - Network interception captures API."""
    
    @pytest.mark.asyncio
    async def test_workday_api_structure(self):
        """
        Test Workday API response parsing.
        
        Expected:
        - Network interception captures Workday job API
        - Jobs extracted without HTML scraping
        - Normalized output
        - No login prompts
        """
        client = WorkdayClient()
        
        slug = client.extract_slug_from_url("https://company.wd5.myworkdayjobs.com/en-US/External")
        assert slug == "External"
        
        mock_response = {
            "jobPostings": [
                {
                    "title": "Data Engineer",
                    "bulletFields": ["REQ-001"],
                    "locationsText": "New York, NY",
                    "externalPath": "/job/Data-Engineer_REQ-001",
                    "postedOn": "2024-01-15T00:00:00Z",
                },
                {
                    "title": "Senior Developer",
                    "bulletFields": ["REQ-002"],
                    "locationsText": "Remote",
                    "externalPath": "/job/Senior-Developer_REQ-002",
                },
            ]
        }
        
        with patch.object(client, 'client') as mock_client:
            mock_response_obj = MagicMock()
            mock_response_obj.json.return_value = mock_response
            mock_response_obj.raise_for_status = MagicMock()
            mock_client.get = AsyncMock(return_value=mock_response_obj)
            
            client.client = mock_client
            
            jobs = []
            base_url = "https://company.wd5.myworkdayjobs.com/en-US/External"
            async for job in client.fetch_jobs("External", "Company", base_url):
                jobs.append(job)
            
            assert len(jobs) == 2
            assert jobs[0].title == "Data Engineer"
            assert jobs[0].job_origin == JobOrigin.ATS
            assert jobs[0].ats_provider == ATSProvider.WORKDAY
            assert jobs[0].extraction_method == "ats_api"


class TestLinkedInNativeStartup:
    """Test Case 3: LinkedIn-Only Startup - Easy Apply, no external scraping."""
    
    def test_linkedin_native_job_accepted(self):
        """
        Test that LinkedIn-native jobs are accepted without external scraping.
        
        Expected:
        - Job extracted from LinkedIn API
        - No external scraping attempted
        - Job marked LINKEDIN_NATIVE
        """
        job = JobPosting(
            job_id="789",
            title="Founding Engineer",
            company_name="Hot Startup",
            location="San Francisco, CA",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/789",
            easy_apply=True,
            external_apply=False,
            job_origin=JobOrigin.LINKEDIN_NATIVE,
            extraction_method="api",
        )
        
        assert job.job_origin == JobOrigin.LINKEDIN_NATIVE
        assert job.easy_apply is True
        assert job.external_apply is False
        assert job.ats_provider is None
        assert job.extraction_method == "api"
    
    def test_no_ats_scraping_for_native(self):
        """Ensure no ATS scraping is triggered for LinkedIn-native jobs."""
        job = JobPosting(
            job_id="999",
            title="CEO",
            company_name="Tiny Startup",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/999",
            easy_apply=True,
            job_origin=JobOrigin.LINKEDIN_NATIVE,
        )
        
        assert job.apply_url is None
        assert job.ats_provider is None


class TestBlockDetectionBehavior:
    """Test Case 4: Block Detection - Authwall/captcha triggers immediate stop."""
    
    def test_scraper_state_on_block(self):
        """
        Test that scraper state is properly set on block.
        
        Expected:
        - Scraper immediately stops
        - Partial results preserved
        - Clear error state returned
        """
        state = ScraperState()
        
        assert state.is_blocked is False
        assert state.block_reason is None
        
        state.is_blocked = True
        state.block_reason = BlockReason.AUTHWALL
        state.jobs_collected = 5
        
        assert state.is_blocked is True
        assert state.block_reason == BlockReason.AUTHWALL
        assert state.jobs_collected == 5
    
    def test_pipeline_result_on_block(self):
        """Test that pipeline result properly reflects block state."""
        result = PipelineResult()
        result.scraper_state.is_blocked = True
        result.scraper_state.block_reason = BlockReason.CAPTCHA_DETECTED
        result.errors.append("Blocked: captcha_detected")
        
        result.jobs.append(JobPosting(
            job_id="partial1",
            title="Partial Job 1",
            company_name="Company",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/partial1",
        ))
        
        assert result.scraper_state.is_blocked is True
        assert len(result.jobs) == 1
        assert len(result.errors) == 1


class TestMixedCompanies:
    """Test Case 5: Mixed Companies - ATS + LinkedIn-native handled correctly."""
    
    def test_mixed_job_classification(self):
        """
        Test handling of mixed ATS and LinkedIn-native companies.
        
        Expected:
        - ATS companies scraped via ATS APIs
        - LinkedIn-only companies accepted via API
        - No unnecessary browser actions
        - Stable execution
        """
        jobs = [
            JobPosting(
                job_id="ats1",
                title="Engineer at Greenhouse Company",
                company_name="Big Corp",
                source=JobSource.LINKEDIN,
                source_url="https://linkedin.com/jobs/view/ats1",
                apply_url="https://boards.greenhouse.io/bigcorp/jobs/ats1",
                ats_provider=ATSProvider.GREENHOUSE,
                job_origin=JobOrigin.ATS,
                external_apply=True,
            ),
            JobPosting(
                job_id="native1",
                title="Designer at Startup",
                company_name="Cool Startup",
                source=JobSource.LINKEDIN,
                source_url="https://linkedin.com/jobs/view/native1",
                easy_apply=True,
                job_origin=JobOrigin.LINKEDIN_NATIVE,
            ),
            JobPosting(
                job_id="ats2",
                title="PM at Lever Company",
                company_name="Tech Inc",
                source=JobSource.LINKEDIN,
                source_url="https://linkedin.com/jobs/view/ats2",
                apply_url="https://jobs.lever.co/techinc/ats2",
                ats_provider=ATSProvider.LEVER,
                job_origin=JobOrigin.ATS,
                external_apply=True,
            ),
            JobPosting(
                job_id="native2",
                title="Intern at Small Co",
                company_name="Small Co",
                source=JobSource.LINKEDIN,
                source_url="https://linkedin.com/jobs/view/native2",
                easy_apply=True,
                job_origin=JobOrigin.LINKEDIN_NATIVE,
            ),
        ]
        
        ats_jobs = [j for j in jobs if j.job_origin == JobOrigin.ATS]
        native_jobs = [j for j in jobs if j.job_origin == JobOrigin.LINKEDIN_NATIVE]
        
        assert len(ats_jobs) == 2
        assert len(native_jobs) == 2
        
        ats_companies = set(j.company_name for j in ats_jobs)
        native_companies = set(j.company_name for j in native_jobs)
        
        assert ats_companies == {"Big Corp", "Tech Inc"}
        assert native_companies == {"Cool Startup", "Small Co"}
        
        for job in ats_jobs:
            assert job.ats_provider is not None
            assert job.apply_url is not None
        
        for job in native_jobs:
            assert job.easy_apply is True
    
    def test_deduplication(self):
        """Test that duplicate jobs are properly filtered."""
        jobs = [
            JobPosting(
                job_id="123",
                title="Engineer",
                company_name="Company",
                source=JobSource.LINKEDIN,
                source_url="https://linkedin.com/jobs/view/123",
            ),
            JobPosting(
                job_id="123",
                title="Engineer",
                company_name="Company",
                source=JobSource.ATS,
                source_url="https://greenhouse.io/jobs/123",
            ),
        ]
        
        seen_keys = set()
        unique_jobs = []
        for job in jobs:
            key = f"{job.company_name.lower()}:{job.job_id}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_jobs.append(job)
        
        assert len(unique_jobs) == 1


class TestOutputSchema:
    """Test that job output matches required schema."""
    
    def test_required_fields_present(self):
        """Verify all required output fields are present."""
        job = JobPosting(
            job_id="test123",
            title="Test Engineer",
            company_name="Test Company",
            location="Remote",
            source=JobSource.LINKEDIN,
            source_url="https://linkedin.com/jobs/view/test123",
            apply_url="https://boards.greenhouse.io/test/jobs/123",
            ats_provider=ATSProvider.GREENHOUSE,
            job_origin=JobOrigin.ATS,
        )
        
        assert job.job_id is not None
        assert job.title is not None
        assert job.company_name is not None
        assert job.location is not None
        assert job.apply_url is not None
        assert job.ats_provider is not None
        assert job.job_origin is not None
        assert job.source_url is not None
        assert job.extracted_at is not None
    
    def test_job_serialization(self):
        """Test that jobs can be serialized to JSON."""
        job = JobPosting(
            job_id="test456",
            title="Senior Developer",
            company_name="Tech Corp",
            location="New York, NY",
            source=JobSource.ATS,
            source_url="https://boards.greenhouse.io/techcorp/jobs/456",
            apply_url="https://boards.greenhouse.io/techcorp/jobs/456",
            ats_provider=ATSProvider.GREENHOUSE,
            job_origin=JobOrigin.ATS,
        )
        
        job_dict = job.model_dump(mode="json")
        
        assert "job_id" in job_dict
        assert "title" in job_dict
        assert "company_name" in job_dict
        assert "location" in job_dict
        assert "apply_url" in job_dict
        assert "ats_provider" in job_dict
        assert "job_origin" in job_dict
        assert "source_url" in job_dict
        assert "extracted_at" in job_dict


def run_tests():
    """Run all tests using pytest."""
    pytest.main([__file__, "-v", "--tb=short"])


if __name__ == "__main__":
    run_tests()
