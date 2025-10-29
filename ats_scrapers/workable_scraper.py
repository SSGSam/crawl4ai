"""
Workable ATS Scraper

Workable is a popular ATS platform for small to medium businesses.
Unlike Greenhouse and Lever, Workable doesn't have a documented public API.

URL Patterns:
- https://apply.workable.com/{company}
- https://{company}.workable.com/
- Embedded: https://www.company.com/careers (uses Workable widget)

Note: This scraper uses HTML parsing via crawl4ai since there's no API.
"""

import asyncio
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

from rich.console import Console

console = Console()


class WorkableScraper:
    """
    Scraper for Workable ATS platform

    Uses HTML scraping with crawl4ai since Workable has no public API.
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def extract_company_id(self, board_url: str) -> Optional[str]:
        """
        Extract Workable company ID from URL

        Examples:
            https://apply.workable.com/anthropic/ → "anthropic"
            https://anthropic.workable.com/ → "anthropic"
        """
        # Pattern 1: apply.workable.com/{company}
        match = re.search(r'apply\.workable\.com/([^/\?]+)', board_url)
        if match:
            return match.group(1)

        # Pattern 2: {company}.workable.com
        match = re.search(r'([^.]+)\.workable\.com', board_url)
        if match:
            company = match.group(1)
            # Exclude 'apply' and 'www'
            if company not in ['apply', 'www']:
                return company

        return None

    async def scrape(
        self,
        board_url: str,
        crawler=None  # AsyncWebCrawler instance (will be passed from main scraper)
    ) -> List[Dict[str, Any]]:
        """
        Main scraping method for Workable boards

        Args:
            board_url: Workable board URL
            crawler: AsyncWebCrawler instance to use for scraping

        Returns:
            List of parsed job dictionaries
        """
        company_id = self.extract_company_id(board_url)
        if not company_id:
            if self.verbose:
                console.print(f"[red]✗ Could not extract company ID from URL:[/red] {board_url}")
            return []

        if self.verbose:
            console.print(f"[cyan]Scraping Workable board for:[/cyan] {company_id}")
            console.print(f"[yellow]⚠ Workable scraper not yet implemented - using placeholder[/yellow]")

        # TODO: Implement Workable HTML scraping using crawl4ai
        # Steps:
        # 1. Navigate to board_url
        # 2. Extract job listings (usually in <li class="job"> elements)
        # 3. For each job:
        #    - Extract title, location, department
        #    - Extract job URL
        #    - Optionally visit job URL for full description
        # 4. Parse and return standardized job dicts

        # Placeholder return
        return []


# ===========================
# Testing
# ===========================

async def test_workable():
    """Test Workable scraper"""
    scraper = WorkableScraper(verbose=True)

    # Test company ID extraction
    test_urls = [
        "https://apply.workable.com/anthropic/",
        "https://anthropic.workable.com/",
    ]

    print("\n=== Testing Company ID Extraction ===")
    for url in test_urls:
        company_id = scraper.extract_company_id(url)
        print(f"{url} → {company_id}")


if __name__ == "__main__":
    asyncio.run(test_workable())
