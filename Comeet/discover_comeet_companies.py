#!/usr/bin/env python3
"""
Discover companies using Comeet ATS by finding their careers pages
and extracting company IDs and tokens.
"""

import requests
import re
import json
from typing import List, Dict, Optional
from urllib.parse import urlparse, urljoin

def search_web_for_comeet_companies() -> List[str]:
    """Search for companies using Comeet ATS."""
    # Known companies using Comeet
    known_companies = [
        "zim",  # From sample data
        "fiverr",
        "playtika",
        "appsflyer",
    ]
    
    base_patterns = []
    for company in known_companies:
        base_patterns.extend([
            f"https://www.comeet.co/jobs/{company}",
            f"https://{company}.comeet.co",
            f"https://careers.{company}.com",
        ])
    
    return base_patterns

def extract_company_info(url: str) -> Optional[Dict[str, str]]:
    """Extract company_id and token from a Comeet careers page."""
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        if response.status_code != 200:
            return None
        
        html = response.text
        final_url = response.url
        
        # Extract company_id from API calls in the page
        # Pattern: /careers-api/2.0/company/{company_id}/
        company_id_pattern = r'/careers-api/2\.0/company/([\d.]+)'
        company_id_matches = re.findall(company_id_pattern, html)
        
        if not company_id_matches:
            return None
        
        company_id = company_id_matches[0]  # Use first match
        
        # Extract token from API URLs
        token_patterns = [
            r'token=([A-F0-9]{32})',
            r'"token"\s*:\s*"([A-F0-9]{32})"',
            r'token["\']?\s*[:=]\s*["\']([A-F0-9]{32})["\']',
        ]
        
        token = None
        for pattern in token_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            if matches:
                token = matches[0]  # Use first match
                break
        
        return {
            "company_id": company_id,
            "token": token,
            "careers_url": final_url,
            "source_url": url
        }
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return None

def test_company_api(company_id: str, token: Optional[str] = None) -> bool:
    """Test if company API is accessible with token."""
    url = f"https://www.comeet.co/careers-api/2.0/company/{company_id}/positions"
    if token:
        url += f"?token={token}"
    
    try:
        response = requests.get(url, timeout=10)
        return response.status_code == 200
    except:
        return False

def discover_companies() -> List[Dict[str, str]]:
    """Discover all Comeet companies."""
    print("Discovering Comeet companies...\n")
    
    companies = []
    urls_to_check = search_web_for_comeet_companies()
    
    for url in urls_to_check:
        print(f"Checking: {url}")
        info = extract_company_info(url)
        if info:
            # Test if API works
            is_accessible = test_company_api(info["company_id"], info.get("token"))
            info["api_accessible"] = is_accessible
            
            companies.append(info)
            print(f"  ✓ Found: company_id={info['company_id']}, "
                  f"token={'Yes' if info['token'] else 'No'}, "
                  f"API={'Working' if is_accessible else 'Needs token'}\n")
        else:
            print(f"  ✗ No Comeet data found\n")
    
    return companies

if __name__ == "__main__":
    companies = discover_companies()
    
    print(f"\n{'='*60}")
    print(f"Found {len(companies)} companies using Comeet ATS")
    print(f"{'='*60}\n")
    
    if companies:
        print(json.dumps(companies, indent=2))
        
        # Save to file
        with open("comeet_companies.json", "w") as f:
            json.dump(companies, f, indent=2)
        print(f"\nSaved to comeet_companies.json")



