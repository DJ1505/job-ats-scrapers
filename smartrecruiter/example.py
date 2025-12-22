#!/usr/bin/env python3
"""
SmartRecruiter ATS Scraper - Example Usage

This example demonstrates how to use the SmartRecruiter ATS scraper
with API-first approach and ATS schema compliance.
"""

import asyncio
import json
from scraper import SmartRecruiterScraper

async def basic_example():
    """Basic scraping example"""
    print("🚀 SmartRecruiter ATS - Basic Example")
    print("=" * 50)
    
    # Initialize scraper
    scraper = SmartRecruiterScraper('smartrecruiters')
    
    # Scrape using Workday-style interface
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=1)
    
    if result['success']:
        print(f"✅ Successfully scraped {result['total_jobs']} jobs")
        print(f"🔧 Method used: {result['scraping_method']}")
        print(f"📊 Quality score: {result['extraction_quality']['score']}")
        
        # Display first few jobs
        print(f"\n📋 Sample Jobs:")
        for i, job in enumerate(result['jobs'][:3]):
            print(f"\n{i+1}. {job['job_title']}")
            print(f"   📍 Location: {job['job_location']}")
            print(f"   💼 Type: {job['employment_type']}")
            print(f"   🔗 URL: {job['job_url']}")
            print(f"   📊 Status: {job['processing_status']}")
    else:
        print(f"❌ Scraping failed: {result['error']}")

async def ats_schema_example():
    """ATS schema compliance example"""
    print("\n🎯 ATS Schema Compliance Example")
    print("=" * 50)
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=1)
    
    if result['success'] and result['jobs']:
        job = result['jobs'][0]
        
        print("📋 ATS Schema Fields:")
        print(f"   ✅ ats_source: {job['ats_source']}")
        print(f"   ✅ company_slug: {job['company_slug']}")
        print(f"   ✅ job_id: {job['job_id']}")
        print(f"   ✅ job_title: {job['job_title']}")
        print(f"   ✅ job_location: {job['job_location']}")
        print(f"   ✅ employment_type: {job['employment_type']}")
        print(f"   ✅ processing_status: {job['processing_status']}")
        print(f"   ✅ ai_extraction_confidence: {job['ai_extraction_confidence']}")
        print(f"   ✅ job_status: {job['job_status']}")
        
        # Check compliance
        required_fields = ['ats_source', 'company_slug', 'job_id', 'job_title']
        compliant = all(field in job for field in required_fields)
        print(f"\n🎯 ATS Compliance: {'✅ COMPLIANT' if compliant else '❌ NON-COMPLIANT'}")

async def api_only_example():
    """API-only scraping example"""
    print("\n🔌 API-Only Example")
    print("=" * 50)
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper._scrape_via_api()
    
    if result['success']:
        print(f"✅ API approach successful")
        print(f"📊 Jobs found: {result['total_jobs']}")
        print(f"🔧 Method: {result['scraping_method']}")
        
        # Show pattern usage
        patterns = result['patterns_used']
        print(f"🎯 Patterns used: {list(patterns.keys())}")
    else:
        print(f"❌ API approach failed: {result['error']}")

async def save_to_file_example():
    """Save results to file example"""
    print("\n💾 Save to File Example")
    print("=" * 50)
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=1)
    
    if result['success']:
        # Save to JSON file
        with open('smartrecruiter_jobs.json', 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)
        
        print(f"✅ Results saved to 'smartrecruiter_jobs.json'")
        print(f"📊 Saved {result['total_jobs']} jobs")
        
        # Save just the ATS schema jobs
        ats_jobs = result['jobs']
        with open('smartrecruiter_ats_jobs.json', 'w', encoding='utf-8') as f:
            json.dump(ats_jobs, f, indent=2, default=str, ensure_ascii=False)
        
        print(f"✅ ATS jobs saved to 'smartrecruiter_ats_jobs.json'")
    else:
        print(f"❌ Failed to save: {result['error']}")

async def main():
    """Run all examples"""
    print("🚀 SmartRecruiter ATS Scraper - Complete Example Suite")
    print("=" * 60)
    
    await basic_example()
    await ats_schema_example()
    await api_only_example()
    await save_to_file_example()
    
    print("\n✅ All examples completed!")
    print("\n📚 Next Steps:")
    print("   1. Check the generated JSON files")
    print("   2. Review the ATS schema compliance")
    print("   3. Test with different companies")
    print("   4. Integrate with your database")

if __name__ == "__main__":
    asyncio.run(main())
