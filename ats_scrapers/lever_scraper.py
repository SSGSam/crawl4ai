"""
Lever ATS Scraper

Lever is a popular ATS platform, especially for startups and tech companies.
They provide an undocumented but accessible API: https://api.lever.co/v0/postings/{company}

URL Patterns:
- https://jobs.lever.co/{company}
- https://{company}.lever.co/
- API: https://api.lever.co/v0/postings/{company}
"""

import asyncio
import httpx
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, urljoin

from rich.console import Console

console = Console()


class LeverScraper:
    """
    Scraper for Lever ATS platform

    Uses Lever's (undocumented) public API:
    https://api.lever.co/v0/postings/{company}
    """

    API_BASE = "https://api.lever.co/v0/postings"

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def extract_company_id(self, board_url: str) -> Optional[str]:
        """
        Extract Lever company ID from URL

        Examples:
            https://jobs.lever.co/anthropic → "anthropic"
            https://anthropic.lever.co/ → "anthropic"
        """
        # Pattern 1: jobs.lever.co/{company}
        match = re.search(r'jobs\.lever\.co/([^/\?]+)', board_url)
        if match:
            return match.group(1)

        # Pattern 2: {company}.lever.co
        match = re.search(r'([^.]+)\.lever\.co', board_url)
        if match:
            company = match.group(1)
            # Exclude 'jobs' and 'www'
            if company not in ['jobs', 'www', 'api']:
                return company

        return None

    async def fetch_jobs(self, company_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all jobs from Lever API

        API Endpoint: GET https://api.lever.co/v0/postings/{company}

        Query parameters:
        - mode=json (returns JSON instead of HTML)
        - skip=0 (pagination)
        - limit=100 (max jobs per request)

        Returns list of job objects with structure:
        {
            "id": "abc123-def456-ghi789",
            "text": "Software Engineer",
            "categories": {
                "team": "Engineering",
                "location": "San Francisco, CA",
                "commitment": "Full-time"
            },
            "description": "...",
            "lists": [...],
            "hostedUrl": "https://jobs.lever.co/company/abc123",
            "applyUrl": "https://jobs.lever.co/company/abc123/apply",
            "createdAt": 1640000000000,
            ...
        }
        """
        url = f"{self.API_BASE}/{company_id}"

        if self.verbose:
            console.print(f"[cyan]Fetching jobs from Lever API:[/cyan] {url}")

        all_jobs = []
        skip = 0
        limit = 100

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                while True:
                    params = {
                        'mode': 'json',
                        'skip': skip,
                        'limit': limit
                    }

                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    jobs = response.json()

                    if not jobs or len(jobs) == 0:
                        break

                    all_jobs.extend(jobs)

                    # If we got fewer jobs than the limit, we've reached the end
                    if len(jobs) < limit:
                        break

                    skip += limit

                    # Add small delay for pagination
                    await asyncio.sleep(0.2)

                if self.verbose:
                    console.print(f"[green]✓ Found {len(all_jobs)} jobs on Lever[/green]")

                return all_jobs

        except httpx.HTTPError as e:
            if self.verbose:
                console.print(f"[red]✗ Error fetching Lever jobs:[/red] {e}")
            return []
        except Exception as e:
            if self.verbose:
                console.print(f"[red]✗ Unexpected error:[/red] {e}")
            return []

    def parse_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Lever job data into our standard format

        Args:
            job_data: Raw job object from Lever API

        Returns:
            Standardized job dict compatible with our Job model
        """
        # Extract basic info
        job_id = job_data.get('id', '')
        title = job_data.get('text', '')

        # Categories contain location, department, commitment
        categories = job_data.get('categories', {})
        location_str = categories.get('location', '')
        department = categories.get('team', None)
        job_type = categories.get('commitment', None)  # Full-time, Part-time, etc.

        # URLs
        apply_url = job_data.get('applyUrl', job_data.get('hostedUrl', ''))

        # Posted date (Unix timestamp in milliseconds)
        created_at = job_data.get('createdAt')
        posted_date = None
        if created_at:
            # Convert from milliseconds to ISO format
            from datetime import datetime
            posted_date = datetime.fromtimestamp(created_at / 1000).isoformat()

        # Description
        description = job_data.get('description', '')

        # Requirements and responsibilities
        # Lever stores these in "lists" array
        requirements = []
        responsibilities = []
        lists = job_data.get('lists', [])
        for list_item in lists:
            list_title = list_item.get('text', '').lower()
            list_content = list_item.get('content', '')

            if 'requirement' in list_title or 'qualification' in list_title:
                # Parse HTML list to extract items
                requirements.append(list_content)
            elif 'responsibilit' in list_title or 'what you' in list_title:
                responsibilities.append(list_content)

        return {
            'job_id': job_id,
            'title': title,
            'location': location_str,
            'department': department,
            'job_type': job_type,
            'description': description,
            'requirements': requirements if requirements else None,
            'responsibilities': responsibilities if responsibilities else None,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'raw_data': job_data  # Keep raw data for reference
        }

    async def scrape(
        self,
        board_url: str
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method for Lever boards

        Args:
            board_url: Lever board URL

        Returns:
            List of parsed job dictionaries
        """
        # Extract company ID
        company_id = self.extract_company_id(board_url)
        if not company_id:
            if self.verbose:
                console.print(f"[red]✗ Could not extract company ID from URL:[/red] {board_url}")
            return []

        # Fetch all jobs
        jobs_data = await self.fetch_jobs(company_id)
        if not jobs_data:
            return []

        # Parse jobs
        parsed_jobs = []
        for job_data in jobs_data:
            parsed_job = self.parse_job(job_data)
            parsed_jobs.append(parsed_job)

        return parsed_jobs


# ===========================
# Testing
# ===========================

async def test_lever():
    """Test Lever scraper"""
    scraper = LeverScraper(verbose=True)

    # Test company ID extraction
    test_urls = [
        "https://jobs.lever.co/anthropic",
        "https://anthropic.lever.co/",
        "https://jobs.lever.co/openai",
    ]

    print("\n=== Testing Company ID Extraction ===")
    for url in test_urls:
        company_id = scraper.extract_company_id(url)
        print(f"{url} → {company_id}")

    # Test actual scraping (using a real company if available)
    print("\n=== Testing Job Scraping ===")
    test_board = "https://jobs.lever.co/anthropic"
    jobs = await scraper.scrape(test_board)

    print(f"\nFound {len(jobs)} jobs")
    if jobs:
        print("\nSample job:")
        print(f"  ID: {jobs[0]['job_id']}")
        print(f"  Title: {jobs[0]['title']}")
        print(f"  Location: {jobs[0]['location']}")
        print(f"  Department: {jobs[0]['department']}")
        print(f"  Type: {jobs[0]['job_type']}")
        print(f"  URL: {jobs[0]['apply_url']}")


if __name__ == "__main__":
    asyncio.run(test_lever())
