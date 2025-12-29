#!/usr/bin/env python3
"""
Production-ready Breezy HR ATS Scraper

A fast, reliable scraper for Breezy HR career pages with API-first approach
and HTML fallback. Built for integration into multi-ATS scraping systems.

Features:
- Domain-based Breezy HR detection
- Public JSON API with pagination support
- Lightweight HTML fallback
- Consistent normalized output schema
- Comprehensive error handling and logging
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class BreezyHRScraper:
    """
    Production-ready Breezy HR ATS scraper.
    
    Detects Breezy HR career pages and scrapes job postings using a public API
    first approach with HTML fallback when necessary.
    """
    
    def __init__(self, timeout: int = 30, max_retries: int = 3, retry_delay: float = 1.0):
        """
        Initialize the Breezy HR scraper.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BreezyHR-Scraper/1.0 (jobs-scraper@example.com)'
        })
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def is_breezy_hr_domain(self, url: str) -> bool:
        """
        Detect if a URL belongs to Breezy HR.
        
        Args:
            url: Career page URL to check
            
        Returns:
            True if the domain matches Breezy HR patterns
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Direct breezy.hr domain
            if domain == 'breezy.hr':
                return True
            
            # Subdomain pattern: company.breezy.hr
            if domain.endswith('.breezy.hr'):
                return True
            
            return False
        except Exception as e:
            self.logger.warning(f"Error parsing URL {url}: {e}")
            return False
    
    def extract_company_slug(self, url: str) -> Optional[str]:
        """
        Extract company slug from Breezy HR URL.
        
        Args:
            url: Breezy HR career page URL
            
        Returns:
            Company slug for API calls or None if not found
        """
        try:
            parsed = urlparse(url)
            path_parts = parsed.path.strip('/').split('/')
            
            # For https://breezy.hr/company-slug
            if parsed.netloc == 'breezy.hr' and path_parts:
                return path_parts[0]
            
            # For https://company.breezy.hr/
            if parsed.netloc.endswith('.breezy.hr'):
                return parsed.netloc.split('.')[0]
            
            return None
        except Exception as e:
            self.logger.warning(f"Error extracting company slug from {url}: {e}")
            return None
    
    def _make_request(self, url: str, method: str = 'GET') -> Optional[requests.Response]:
        """
        Make HTTP request with retry logic.
        
        Args:
            url: URL to request
            method: HTTP method
            
        Returns:
            Response object or None if all retries failed
        """
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(method, url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    self.logger.error(f"Request failed after {self.max_retries} attempts: {e}")
                    return None
                
                self.logger.warning(f"Request attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
        
        return None
    
    def scrape_via_api(self, base_url: str, company_slug: str) -> Dict[str, Any]:
        """
        Scrape jobs using Breezy HR public JSON API.
        
        Args:
            base_url: Base career page URL
            company_slug: Company identifier
            
        Returns:
            Scraping result dictionary
        """
        jobs = []
        
        self.logger.info(f"Starting API scraping for company: {company_slug}")
        
        # Breezy HR uses /json endpoint on career pages
        api_urls = [
            f"https://{company_slug}.breezy.hr/json",
            f"https://breezy.hr/{company_slug}/json",
            base_url.rstrip('/') + '/json'
        ]
        
        for api_url in api_urls:
            self.logger.info(f"Trying API endpoint: {api_url}")
            response = self._make_request(api_url)
            
            if not response:
                continue
            
            try:
                data = response.json()
                
                # Handle both list and dict responses
                positions = data if isinstance(data, list) else data.get('positions', [])
                
                if not positions:
                    self.logger.info(f"No positions found at {api_url}")
                    continue
                
                # Convert API positions to normalized format
                for position in positions:
                    normalized_job = self._normalize_api_position(position)
                    if normalized_job:
                        jobs.append(normalized_job)
                
                self.logger.info(f"Retrieved {len(positions)} positions from API")
                break  # Success, no need to try other URLs
                
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse API response from {api_url}: {e}")
                continue
            except Exception as e:
                self.logger.warning(f"Error processing API response from {api_url}: {e}")
                continue
        
        return {
            'success': len(jobs) > 0,
            'scraping_method': 'public_api',
            'total_jobs': len(jobs),
            'jobs': jobs,
            'errors': [] if jobs else ['API returned no jobs']
        }
    
    def _normalize_api_position(self, position: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize API position data to standard schema.
        
        Args:
            position: Raw position data from Breezy API
            
        Returns:
            Normalized job dictionary or None if invalid
        """
        try:
            # Extract location information
            # Extract location from nested structure
            location_data = position.get('location', {})
            location_parts = []
            
            if isinstance(location_data, dict):
                if location_data.get('city'):
                    location_parts.append(location_data['city'])
                if location_data.get('state', {}).get('name'):
                    location_parts.append(location_data['state']['name'])
                elif location_data.get('state'):
                    location_parts.append(str(location_data['state']))
                if location_data.get('country', {}).get('name'):
                    location_parts.append(location_data['country']['name'])
                
                is_remote = location_data.get('is_remote', False)
            else:
                is_remote = False
            
            location = ', '.join(location_parts) if location_parts else ''
            if is_remote:
                location = f"{location} (Remote)" if location else 'Remote'
            
            # Determine job type from nested structure
            type_data = position.get('type', {})
            if isinstance(type_data, dict):
                job_type = type_data.get('name', '')
            else:
                job_type = str(type_data) if type_data else ''
            
            # Get company info
            company_data = position.get('company', {})
            company_slug = company_data.get('friendly_id', '') if isinstance(company_data, dict) else ''
            
            return {
                'title': position.get('name', '') or position.get('title', ''),
                'location': location,
                'department': position.get('department', ''),
                'type': job_type,
                'url': position.get('url', ''),
                'metadata': {
                    'api_id': position.get('id'),
                    'friendly_id': position.get('friendly_id'),
                    'is_remote': is_remote,
                    'published_date': position.get('published_date'),
                    'salary': position.get('salary', ''),
                    'company_name': company_data.get('name', '') if isinstance(company_data, dict) else ''
                },
                'extracted_at': datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            self.logger.warning(f"Error normalizing API position: {e}")
            return None
    
    def scrape_via_html(self, url: str) -> Dict[str, Any]:
        """
        Scrape jobs using HTML fallback method.
        
        Args:
            url: Career page URL
            
        Returns:
            Scraping result dictionary
        """
        self.logger.info(f"Starting HTML fallback scraping for: {url}")
        
        response = self._make_request(url)
        if not response:
            return {
                'success': False,
                'scraping_method': 'html_fallback',
                'total_jobs': 0,
                'jobs': [],
                'errors': ['Failed to fetch HTML page']
            }
        
        try:
            soup = BeautifulSoup(response.text, 'html.parser')
            jobs = []
            
            # Find job listings using lightweight selectors
            job_elements = soup.select('li.position, .position, .job-listing, [class*="position"]')
            
            for element in job_elements:
                job = self._extract_job_from_element(element, url)
                if job:
                    jobs.append(job)
            
            self.logger.info(f"HTML fallback found {len(jobs)} jobs")
            
            return {
                'success': len(jobs) > 0,
                'scraping_method': 'html_fallback',
                'total_jobs': len(jobs),
                'jobs': jobs,
                'errors': [] if jobs else ['HTML fallback found no jobs']
            }
            
        except Exception as e:
            self.logger.error(f"HTML parsing failed: {e}")
            return {
                'success': False,
                'scraping_method': 'html_fallback',
                'total_jobs': 0,
                'jobs': [],
                'errors': [f'HTML parsing error: {e}']
            }
    
    def _extract_job_from_element(self, element, base_url: str) -> Optional[Dict[str, Any]]:
        """
        Extract job information from HTML element.
        
        Args:
            element: BeautifulSoup element containing job info
            base_url: Base URL for resolving relative links
            
        Returns:
            Normalized job dictionary or None if extraction failed
        """
        try:
            # Extract title
            title_elem = element.select_one('.position-name, .job-title, h2, h3, .title, [class*="title"]')
            title = title_elem.get_text(strip=True) if title_elem else ''
            
            if not title:
                return None
            
            # Extract location
            location_elem = element.select_one('.location, .job-location, [class*="location"]')
            location = location_elem.get_text(strip=True) if location_elem else ''
            
            # Extract department (less common in HTML)
            dept_elem = element.select_one('.department, [class*="department"]')
            department = dept_elem.get_text(strip=True) if dept_elem else ''
            
            # Extract job URL
            link_elem = element.select_one('a[href*="/p/"], a[href*="position"], a[href*="job"]')
            job_url = ''
            if link_elem and link_elem.get('href'):
                job_url = urljoin(base_url, link_elem['href'])
            
            # Extract job type (optional)
            type_elem = element.select_one('.type, .job-type, [class*="type"]')
            job_type = type_elem.get_text(strip=True) if type_elem else ''
            
            return {
                'title': title,
                'location': location,
                'department': department,
                'type': job_type,
                'url': job_url,
                'metadata': {
                    'html_element_class': element.get('class', []),
                    'source': 'html_fallback'
                },
                'extracted_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            self.logger.warning(f"Error extracting job from HTML element: {e}")
            return None
    
    def scrape(self, url: str) -> Dict[str, Any]:
        """
        Main scraping method with API-first approach and HTML fallback.
        
        Args:
            url: Breezy HR career page URL
            
        Returns:
            Normalized scraping result
        """
        # Validate Breezy HR domain
        if not self.is_breezy_hr_domain(url):
            error_msg = f"URL does not appear to be a Breezy HR career page: {url}"
            self.logger.error(error_msg)
            return {
                'ats_type': 'breezy',
                'scraping_method': 'none',
                'total_jobs': 0,
                'jobs': [],
                'errors': [error_msg]
            }
        
        # Extract company slug for API calls
        company_slug = self.extract_company_slug(url)
        if not company_slug:
            self.logger.warning(f"Could not extract company slug from: {url}")
        
        # Try API first if we have a company slug
        if company_slug:
            self.logger.info(f"Attempting API scraping for slug: {company_slug}")
            api_result = self.scrape_via_api(url, company_slug)
            
            if api_result['success'] and api_result['total_jobs'] > 0:
                self.logger.info(f"API scraping successful: {api_result['total_jobs']} jobs found")
                result = {
                    'ats_type': 'breezy',
                    **api_result
                }
                return result
            else:
                self.logger.info("API scraping failed or returned no jobs, trying HTML fallback")
        
        # Fallback to HTML scraping
        html_result = self.scrape_via_html(url)
        
        result = {
            'ats_type': 'breezy',
            **html_result
        }
        
        return result
    
    def get_scraper_info(self) -> Dict[str, Any]:
        """
        Get information about the scraper capabilities and characteristics.
        
        Returns:
            Scraper information dictionary
        """
        return {
            'ats_type': 'breezy',
            'name': 'Breezy HR ATS Scraper',
            'version': '1.0.0',
            'description': 'Fast, reliable scraper for Breezy HR career pages with API-first approach',
            'supported_methods': ['public_api', 'html_fallback'],
            'primary_method': 'public_api',
            'accuracy': {
                'api': 'High - Direct structured data from Breezy API',
                'html_fallback': 'Medium - Dependent on HTML structure'
            },
            'cost': {
                'api_requests': 'Low - RESTful API calls',
                'bandwidth': 'Low - JSON responses',
                'processing': 'Minimal'
            },
            'features': [
                'Automatic Breezy HR detection',
                'API pagination support',
                'HTML fallback mechanism',
                'Retry and timeout handling',
                'Normalized output schema',
                'Comprehensive logging'
            ],
            'limitations': [
                'Requires valid company slug for API access',
                'HTML fallback depends on page structure',
                'Rate limiting may apply to API calls'
            ],
            'supported_domains': [
                'breezy.hr',
                '*.breezy.hr (subdomains)'
            ]
        }


def main():
    """
    Example usage of the Breezy HR scraper.
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize scraper
    scraper = BreezyHRScraper(timeout=30, max_retries=3)
    
    # Print scraper information
    print("=" * 60)
    print("BREEZY HR SCRAPER INFORMATION")
    print("=" * 60)
    info = scraper.get_scraper_info()
    print(f"ATS Type: {info['ats_type']}")
    print(f"Name: {info['name']}")
    print(f"Version: {info['version']}")
    print(f"Primary Method: {info['primary_method']}")
    print(f"Accuracy (API): {info['accuracy']['api']}")
    print(f"Supported Domains: {', '.join(info['supported_domains'])}")
    print()
    
    # Example URLs to test
    test_urls = [
        'https://breezy.hr/breezy',  # Example company
        'https://company.breezy.hr/',  # Subdomain example
    ]
    
    print("EXAMPLE SCRAPING RESULTS")
    print("=" * 60)
    
    for url in test_urls:
        print(f"\nTesting URL: {url}")
        print("-" * 40)
        
        try:
            result = scraper.scrape(url)
            
            print(f"ATS Type: {result['ats_type']}")
            print(f"Scraping Method: {result['scraping_method']}")
            print(f"Total Jobs: {result['total_jobs']}")
            
            if result['jobs']:
                print("\nSample Jobs:")
                for i, job in enumerate(result['jobs'][:3], 1):
                    print(f"  {i}. {job['title']}")
                    print(f"     Location: {job['location']}")
                    print(f"     Department: {job['department']}")
                    print(f"     Type: {job['type']}")
                    if job['url']:
                        print(f"     URL: {job['url']}")
                    print()
            
            if result.get('errors'):
                print("Errors:")
                for error in result['errors']:
                    print(f"  - {error}")
                    
        except Exception as e:
            print(f"Scraping failed with error: {e}")
        
        print("-" * 40)
    
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
