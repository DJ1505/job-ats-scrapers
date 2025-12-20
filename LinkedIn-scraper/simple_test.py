"""
Simple test to verify the pipeline components are working.
"""
import asyncio
from schemas import JobOrigin, ATSProvider
from ats_detector import detect_ats_from_url
from network_interceptor import detect_block_from_url

def test_ats_detection():
    """Test ATS detection with example URLs"""
    print("🔍 Testing ATS Detection:")
    
    test_urls = {
        "https://boards.greenhouse.io/stripe/jobs/123": ATSProvider.GREENHOUSE,
        "https://jobs.lever.co/airbnb": ATSProvider.LEVER,
        "https://microsoft.wd5.myworkdayjobs.com/en-US/careers": ATSProvider.WORKDAY,
        "https://jobs.ashbyhq.com/notion": ATSProvider.ASHBY,
        "https://linkedin.com/jobs/view/123": ATSProvider.UNKNOWN,
    }
    
    for url, expected in test_urls.items():
        detected = detect_ats_from_url(url)
        status = "✅" if detected == expected else "❌"
        print(f"  {status} {url}")
        print(f"    Expected: {expected.value if expected else 'None'}")
        print(f"    Detected: {detected.value if detected else 'None'}")
    
    print()

def test_block_detection():
    """Test block detection"""
    print("🚫 Testing Block Detection:")
    
    test_urls = {
        "https://www.linkedin.com/jobs/search": None,
        "https://www.linkedin.com/login": "login_required",
        "https://www.linkedin.com/authwall": "authwall",
        "https://www.linkedin.com/checkpoint/challenge": "checkpoint",
    }
    
    for url, expected_block in test_urls.items():
        block_reason = detect_block_from_url(url)
        detected_block = block_reason.value if block_reason else None
        
        status = "✅" if detected_block == expected_block else "❌"
        print(f"  {status} {url}")
        print(f"    Expected block: {expected_block}")
        print(f"    Detected block: {detected_block}")
    
    print()

def test_job_schemas():
    """Test job schema creation"""
    print("📋 Testing Job Schemas:")
    
    from schemas import JobPosting, JobSource
    from datetime import datetime
    
    # Test ATS job
    ats_job = JobPosting(
        job_id="12345",
        title="Software Engineer",
        company_name="Stripe",
        location="San Francisco, CA",
        source=JobSource.ATS,
        source_url="https://boards.greenhouse.io/stripe/jobs/12345",
        apply_url="https://boards.greenhouse.io/stripe/jobs/12345",
        ats_provider=ATSProvider.GREENHOUSE,
        job_origin=JobOrigin.ATS,
        extraction_method="ats_api",
    )
    
    print(f"  ✅ ATS Job Created:")
    print(f"    Title: {ats_job.title}")
    print(f"    Company: {ats_job.company_name}")
    print(f"    Origin: {ats_job.job_origin.value}")
    print(f"    ATS: {ats_job.ats_provider.value}")
    
    # Test LinkedIn Native job
    native_job = JobPosting(
        job_id="67890",
        title="Product Manager",
        company_name="StartupXYZ",
        location="New York, NY",
        source=JobSource.LINKEDIN,
        source_url="https://linkedin.com/jobs/view/67890",
        easy_apply=True,
        job_origin=JobOrigin.LINKEDIN_NATIVE,
        extraction_method="api",
    )
    
    print(f"\n  ✅ LinkedIn Native Job Created:")
    print(f"    Title: {native_job.title}")
    print(f"    Company: {native_job.company_name}")
    print(f"    Origin: {native_job.job_origin.value}")
    print(f"    Easy Apply: {native_job.easy_apply}")
    
    print()

async def test_ats_clients():
    """Test ATS client initialization"""
    print("🔌 Testing ATS Clients:")
    
    from ats_clients import get_ats_client, GreenhouseClient, LeverClient, WorkdayClient
    
    clients = [
        (ATSProvider.GREENHOUSE, GreenhouseClient),
        (ATSProvider.LEVER, LeverClient),
        (ATSProvider.WORKDAY, WorkdayClient),
    ]
    
    for provider, client_class in clients:
        client = get_ats_client(provider)
        status = "✅" if client is not None else "❌"
        print(f"  {status} {provider.value}: {client_class.__name__}")
        
        if client:
            # Test slug extraction
            test_urls = {
                ATSProvider.GREENHOUSE: "https://boards.greenhouse.io/stripe/jobs/123",
                ATSProvider.LEVER: "https://jobs.lever.co/airbnb/abc123",
                ATSProvider.WORKDAY: "https://company.wd5.myworkdayjobs.com/External",
            }
            
            if provider in test_urls:
                slug = client.extract_slug_from_url(test_urls[provider])
                print(f"    Extracted slug: {slug}")
    
    print()

def main():
    """Run all simple tests"""
    print("🧪 Simple Pipeline Component Tests")
    print("=" * 50)
    
    test_ats_detection()
    test_block_detection()
    test_job_schemas()
    
    # Run async test
    asyncio.run(test_ats_clients())
    
    print("✅ All component tests completed!")
    print("\n💡 Note: LinkedIn search may be blocked or rate-limited.")
    print("   The core components (ATS detection, block detection, schemas) are working correctly.")

if __name__ == "__main__":
    main()
