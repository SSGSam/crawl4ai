"""
Greenhouse ATS Scraper

Greenhouse is one of the most popular ATS platforms, especially for tech companies.
They provide a public API: https://boards-api.greenhouse.io/v1/boards/{company}/jobs

URL Patterns:
- https://boards.greenhouse.io/{company}
- https://{company}.greenhouse.io/
- Embedded: https://www.company.com/careers (uses Greenhouse widget)
"""

import asyncio
import httpx
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from rich.console import Console

console = Console()


class GreenhouseScraper:
    """
    Scraper for Greenhouse ATS platform

    Uses the official Greenhouse Board API:
    https://developers.greenhouse.io/job-board.html
    """

    API_BASE = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def extract_company_id(self, board_url: str) -> Optional[str]:
        """
        Extract Greenhouse company ID from URL

        Examples:
            https://boards.greenhouse.io/anthropic → "anthropic"
            https://anthropic.greenhouse.io/ → "anthropic"
            https://www.greenhouse.io/anthropic → "anthropic"
        """
        # Pattern 1: boards.greenhouse.io/{company}
        match = re.search(r'boards\.greenhouse\.io/([^/\?]+)', board_url)
        if match:
            return match.group(1)

        # Pattern 2: {company}.greenhouse.io
        match = re.search(r'([^.]+)\.greenhouse\.io', board_url)
        if match:
            company = match.group(1)
            # Exclude 'boards' and 'www'
            if company not in ['boards', 'www']:
                return company

        # Pattern 3: greenhouse.io/{company}
        match = re.search(r'greenhouse\.io/([^/\?]+)', board_url)
        if match:
            return match.group(1)

        return None

    async def fetch_jobs(self, company_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all jobs from Greenhouse API

        API Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs

        Returns list of job objects with structure:
        {
            "id": 123456,
            "title": "Software Engineer",
            "location": {"name": "San Francisco, CA"},
            "departments": [{"name": "Engineering"}],
            "offices": [{"name": "San Francisco"}],
            "absolute_url": "https://boards.greenhouse.io/company/jobs/123456",
            ...
        }
        """
        url = f"{self.API_BASE}/{company_id}/jobs"

        if self.verbose:
            console.print(f"[cyan]Fetching jobs from Greenhouse API:[/cyan] {url}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                # API returns {"jobs": [...]}
                jobs = data.get('jobs', [])

                if self.verbose:
                    console.print(f"[green]✓ Found {len(jobs)} jobs on Greenhouse[/green]")

                return jobs

        except httpx.HTTPError as e:
            if self.verbose:
                console.print(f"[red]✗ Error fetching Greenhouse jobs:[/red] {e}")
            return []
        except Exception as e:
            if self.verbose:
                console.print(f"[red]✗ Unexpected error:[/red] {e}")
            return []

    async def fetch_job_details(self, company_id: str, job_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch detailed information for a specific job

        API Endpoint: GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs/{job_id}

        Returns job details including:
        - Full description (HTML)
        - Requirements
        - Responsibilities
        - Benefits
        - More metadata
        """
        url = f"{self.API_BASE}/{company_id}/jobs/{job_id}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.json()

        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Warning:[/yellow] Could not fetch details for job {job_id}: {e}")
            return None

    def parse_job(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse Greenhouse job data into our standard format

        Args:
            job_data: Raw job object from Greenhouse API

        Returns:
            Standardized job dict compatible with our Job model
        """
        # Extract basic info
        job_id = str(job_data.get('id', ''))
        title = job_data.get('title', '')

        # Location info
        location_obj = job_data.get('location', {})
        location_str = location_obj.get('name', '') if location_obj else ''

        # Department info
        departments = job_data.get('departments', [])
        department = departments[0].get('name', '') if departments else None

        # Job metadata
        metadata = job_data.get('metadata', [])
        job_type = None
        for meta in metadata:
            if meta.get('name', '').lower() == 'employment type':
                job_type = meta.get('value', '')
                break

        # Apply URL
        apply_url = job_data.get('absolute_url', '')

        # Updated/Posted date
        posted_date = job_data.get('updated_at', '')

        return {
            'job_id': job_id,
            'title': title,
            'location': location_str,
            'department': department,
            'job_type': job_type,
            'apply_url': apply_url,
            'posted_date': posted_date,
            'raw_data': job_data  # Keep raw data for reference
        }

    async def scrape(
        self,
        board_url: str,
        fetch_details: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method for Greenhouse boards

        Args:
            board_url: Greenhouse board URL
            fetch_details: If True, fetches full job details (slower, more API calls)

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
            # Optionally fetch detailed info
            if fetch_details:
                job_id = job_data.get('id')
                details = await self.fetch_job_details(company_id, job_id)
                if details:
                    # Merge details into job data
                    job_data.update(details)

                # Add small delay to respect API rate limits
                await asyncio.sleep(0.1)

            parsed_job = self.parse_job(job_data)
            parsed_jobs.append(parsed_job)

        return parsed_jobs


# ===========================
# Testing
# ===========================

async def test_greenhouse():
    """Test Greenhouse scraper"""
    scraper = GreenhouseScraper(verbose=True)

    # Test company ID extraction
    test_urls = [
        "https://boards.greenhouse.io/anthropic",
        "https://anthropic.greenhouse.io/",
        "https://boards.greenhouse.io/openai",
    ]

    print("\n=== Testing Company ID Extraction ===")
    for url in test_urls:
        company_id = scraper.extract_company_id(url)
        print(f"{url} → {company_id}")

    # Test actual scraping (using a real company)
    print("\n=== Testing Job Scraping ===")
    test_board = "https://boards.greenhouse.io/anthropic"
    jobs = await scraper.scrape(test_board)

    print(f"\nFound {len(jobs)} jobs")
    if jobs:
        print("\nSample job:")
        print(f"  ID: {jobs[0]['job_id']}")
        print(f"  Title: {jobs[0]['title']}")
        print(f"  Location: {jobs[0]['location']}")
        print(f"  Department: {jobs[0]['department']}")
        print(f"  URL: {jobs[0]['apply_url']}")


if __name__ == "__main__":
    asyncio.run(test_greenhouse())
