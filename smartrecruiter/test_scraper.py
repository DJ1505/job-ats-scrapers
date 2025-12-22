#!/usr/bin/env python3
"""Test script for the updated SmartRecruiter scraper"""

import asyncio
from scraper import SmartRecruiterScraper

async def test_api():
    """Test the API-first approach"""
    print("🧪 Testing SmartRecruiter API approach...")
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper._scrape_via_api()
    
    print(f"✅ Success: {result['success']}")
    if result['success']:
        print(f"📊 Jobs found: {result['total_jobs']}")
        print(f"🔧 Method: {result['scraping_method']}")
        print(f"📈 Quality score: {result['extraction_quality']['score']}")
        
        if result['jobs']:
            sample_job = result['jobs'][0]
            print(f"📋 Sample job title: {sample_job.get('title', 'N/A')}")
            print(f"📍 Sample job location: {sample_job.get('location', 'N/A')}")
            print(f"🏢 Sample job company: {sample_job.get('company', 'N/A')}")
    else:
        print(f"❌ Error: {result.get('error')}")

async def test_workday_interface():
    """Test the Workday-style interface"""
    print("\n🧪 Testing Workday-style interface...")
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=1)
    
    print(f"✅ Success: {result['success']}")
    if result['success']:
        print(f"📊 Jobs found: {result['total_jobs']}")
        print(f"🔧 Method: {result['scraping_method']}")
        print(f"📄 Pages scraped: {result['pages_scraped']}")
        print(f"📈 Quality score: {result['extraction_quality']['score']}")
        
        # Show patterns used
        if 'patterns_used' in result:
            print("🎯 Patterns used:")
            for category, patterns in result['patterns_used'].items():
                print(f"  - {category}: {len(patterns)} patterns")
    else:
        print(f"❌ Error: {result.get('error')}")

async def main():
    """Run all tests"""
    print("🚀 Testing SmartRecruiter ATS Scraper (Workday-style)")
    print("=" * 60)
    
    await test_api()
    await test_workday_interface()
    
    print("\n✅ Testing complete!")

if __name__ == "__main__":
    asyncio.run(main())
