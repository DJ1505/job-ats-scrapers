#!/usr/bin/env python3
"""Test script to explore Comeet API structure."""

import requests
import json

COMPANY_ID = "72.008"
BASE_DOMAIN = "https://www.comeet.co"

# Try different endpoint variations
endpoints = [
    f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/positions",
    f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/positions/",
    f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}",
    f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/",
]

for url in endpoints:
    print(f"\nTrying: {url}")
    try:
        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
            print(f"Sample: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"Error: {response.text[:200]}")
    except Exception as e:
        print(f"Exception: {e}")



