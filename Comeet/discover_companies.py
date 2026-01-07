#!/usr/bin/env python3
"""
Discover companies using Comeet ATS and extract their company IDs and tokens.
"""

import requests
import re
import json
from typing import List, Dict, Optional
from urllib.parse import urlparse

def find_comeet_careers_pages() -> List[str]:
    """Find Comeet careers pages through web search and known patterns."""
    # Known companies using Comeet (from research)
    known_companies = [
        "fiverr",
        "playtika", 
        "playbuzz",
        "appsflyer",
        "zim"  # The company from the sample data
    ]
    
    base_urls = []
    for company in known_companies:
        # Try common Comeet URL patterns
        patterns = [
            f"https://www.comeet.co/jobs/{company}",
            f"https://www.comeet.com/jobs/{company}",
            f"https://{company}.comeet.co",
            f"https://careers.{company}.com",
        ]
        base_urls.extend(patterns)
    
    return base_urls

def extract_company_info_from_page(url: str) -> Optional[Dict[str, str]]:
    """Extract company_id and token from a Comeet careers page."""
    try:
        response = requests.get(url, timeout=10, allow_redirects=True)
        if response.status_code != 200:
            return None
        
        html = response.text
        
        # Look for API calls in JavaScript
        # Pattern: /careers-api/2.0/company/{company_id}/positions
        api_pattern = r'/careers-api/2.0/company/([\d.]+)/positions'
        company_id_match = re.search(api_pattern, html)
        
        if not company_id_match:
            return None
        
        company_id = company_id_match.group(1)
        
        # Look for token in API URLs or JavaScript variables
        token_patterns = [
            r'token=([A-F0-9]+)',
            r'"token"\s*:\s*"([A-F0-9]+)"',
            r'token["\']?\s*[:=]\s*["\']([A-F0-9]+)["\']',
        ]
        
        token = None
        for pattern in token_patterns:
            token_match = re.search(pattern, html, re.IGNORECASE)
            if token_match:
                token = token_match.group(1)
                break
        
        return {
            "company_id": company_id,
            "token": token,
            "url": url
        }
    except Exception as e:
        print(f"Error processing {url}: {e}")
        return None

def discover_comeet_companies() -> List[Dict[str, str]]:
    """Discover companies using Comeet ATS."""
    print("Discovering Comeet companies...")
    
    companies = []
    urls_to_check = find_comeet_careers_pages()
    
    for url in urls_to_check:
        print(f"Checking: {url}")
        info = extract_company_info_from_page(url)
        if info:
            companies.append(info)
            print(f"  Found: company_id={info['company_id']}, token={'Yes' if info['token'] else 'No'}")
    
    return companies

if __name__ == "__main__":
    companies = discover_comeet_companies()
    print(f"\nFound {len(companies)} companies using Comeet ATS:")
    print(json.dumps(companies, indent=2))



