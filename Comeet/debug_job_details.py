#!/usr/bin/env python3
"""Debug script to check what individual job detail endpoint returns."""

import requests
import json

COMPANY_ID = "72.008"
TOKEN = "2789E01638768C58768ED013C011480"
BASE_DOMAIN = "https://www.comeet.co"

# First get the list
list_url = f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/positions?token={TOKEN}"
response = requests.get(list_url)
positions = response.json()

if positions and len(positions) > 0:
    # Check first position from list
    first_from_list = positions[0]
    print("First position from LIST endpoint:")
    print(f"UID: {first_from_list.get('uid')}")
    print(f"Has details: {bool(first_from_list.get('details'))}")
    if first_from_list.get('details'):
        print(f"Details structure: {json.dumps(first_from_list['details'][:2], indent=2)}")
    
    # Now fetch individual details
    uid = first_from_list.get('uid')
    detail_url = f"{BASE_DOMAIN}/careers-api/2.0/company/{COMPANY_ID}/positions/{uid}?token={TOKEN}"
    detail_response = requests.get(detail_url)
    detail_data = detail_response.json()
    
    print(f"\n\nIndividual DETAIL endpoint for {uid}:")
    print(f"Response type: {type(detail_data)}")
    if isinstance(detail_data, dict):
        print(f"Keys: {list(detail_data.keys())}")
        print(f"Has details: {bool(detail_data.get('details'))}")
        if detail_data.get('details'):
            print(f"Details structure: {json.dumps(detail_data['details'][:2], indent=2)}")
        else:
            print(f"Full response: {json.dumps(detail_data, indent=2)[:1000]}")


