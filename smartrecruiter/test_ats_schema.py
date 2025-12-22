#!/usr/bin/env python3
"""Test script for ATS schema mapping"""

import asyncio
import json
from scraper import SmartRecruiterScraper

async def test_ats_schema_mapping():
    """Test the ATS schema mapping functionality"""
    print("🧪 Testing ATS Schema Mapping...")
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    
    # Test API approach with ATS schema
    result = await scraper._scrape_via_api()
    
    print(f"✅ Success: {result['success']}")
    if result['success'] and result['jobs']:
        print(f"📊 Jobs found: {result['total_jobs']}")
        
        # Check first job for ATS schema compliance
        sample_job = result['jobs'][0]
        print(f"📋 Sample job title: {sample_job.get('job_title', 'N/A')}")
        
        # Verify required ATS schema fields
        required_fields = [
            'ats_source', 'company_slug', 'job_id', 'job_title',
            'job_url', 'job_description_raw', 'processing_status',
            'job_status', 'created_at'
        ]
        
        print("\n🔍 Checking ATS Schema Compliance:")
        missing_fields = []
        for field in required_fields:
            if field in sample_job:
                print(f"  ✅ {field}: {sample_job[field] if field not in ['job_description_raw'] else '...'}")
            else:
                print(f"  ❌ {field}: MISSING")
                missing_fields.append(field)
        
        # Check location mapping
        print(f"\n📍 Location mapping:")
        print(f"  - job_location: {sample_job.get('job_location')}")
        print(f"  - city: {sample_job.get('city')}")
        print(f"  - country: {sample_job.get('country')}")
        print(f"  - work_location_type: {sample_job.get('work_location_type')}")
        print(f"  - remote_scope: {sample_job.get('remote_scope')}")
        
        # Check employment mapping
        print(f"\n💼 Employment mapping:")
        print(f"  - employment_type: {sample_job.get('employment_type')}")
        print(f"  - experience_level: {sample_job.get('experience_level')}")
        print(f"  - management_level: {sample_job.get('management_level')}")
        
        # Check AI processing metadata
        print(f"\n🤖 AI Processing metadata:")
        ai_metadata = sample_job.get('ai_processing_metadata', {})
        for key, value in ai_metadata.items():
            print(f"  - {key}: {value}")
        
        if not missing_fields:
            print(f"\n✅ All required ATS schema fields present!")
        else:
            print(f"\n❌ Missing {len(missing_fields)} required fields: {missing_fields}")
            
        # Save sample to file for inspection
        with open('sample_ats_job.json', 'w', encoding='utf-8') as f:
            json.dump(sample_job, f, indent=2, default=str, ensure_ascii=False)
        print(f"\n💾 Sample job saved to 'sample_ats_job.json'")
        
    else:
        print(f"❌ Error: {result.get('error')}")

async def test_workday_interface_ats():
    """Test the Workday-style interface with ATS schema"""
    print("\n🧪 Testing Workday-style Interface with ATS Schema...")
    
    scraper = SmartRecruiterScraper('smartrecruiters')
    result = await scraper.scrape_jobs("", scraper.base_url, max_pages=1)
    
    print(f"✅ Success: {result['success']}")
    if result['success']:
        print(f"📊 Jobs found: {result['total_jobs']}")
        print(f"🔧 Method: {result['scraping_method']}")
        
        # Verify all jobs have ATS schema
        ats_compliant = all(
            'ats_source' in job and 'job_id' in job and 'job_title' in job 
            for job in result['jobs']
        )
        
        print(f"📋 ATS Schema Compliance: {'✅ All jobs compliant' if ats_compliant else '❌ Some jobs non-compliant'}")
        
    else:
        print(f"❌ Error: {result.get('error')}")

async def main():
    """Run all ATS schema tests"""
    print("🚀 Testing SmartRecruiter ATS Schema Mapping")
    print("=" * 60)
    
    await test_ats_schema_mapping()
    await test_workday_interface_ats()
    
    print("\n✅ ATS Schema testing complete!")

if __name__ == "__main__":
    asyncio.run(main())
