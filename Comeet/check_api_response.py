#!/usr/bin/env python3
"""Check actual API response structure."""

import requests
import json

COMPANY_ID = "72.008"
TOKEN = "2789E01638768C58768ED013C011480"
BASE_DOMAIN = "https://www.comeet.co"

url = f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/positions?token={TOKEN}"
response = requests.get(url)
data = response.json()

if isinstance(data, list) and len(data) > 0:
    first_job = data[0]
    print("First job from API:")
    print(f"Keys: {list(first_job.keys())}")
    print(f"\nHas 'details' key: {'details' in first_job}")
    if 'details' in first_job:
        print(f"Details type: {type(first_job['details'])}")
        print(f"Details length: {len(first_job['details']) if first_job['details'] else 0}")
        if first_job['details']:
            print(f"First detail: {json.dumps(first_job['details'][0], indent=2)}")
    
    # Check a job that should have details (not general application)
    for job in data:
        if job.get('name') and 'General application' not in job.get('name', ''):
            print(f"\n\nJob with details: {job.get('name')}")
            print(f"Has details: {bool(job.get('details'))}")
            if job.get('details'):
                print(f"Details: {json.dumps(job['details'], indent=2)[:500]}")
            break


