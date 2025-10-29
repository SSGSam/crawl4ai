"""
Job Board Scraper for Company Website Scraper

Supports 32+ ATS (Applicant Tracking System) platforms:
- Greenhouse, Lever, Workable, iCIMS, SmartRecruiters, and more
- Filters for US-based jobs
- Filters for engineering and technology roles
- Caches job board URLs to avoid re-discovery

Author: Claude
Date: 2025-01-29
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from urllib.parse import urlparse, urljoin
from enum import Enum

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()


# ===========================
# Data Models
# ===========================

class ATSPlatform(str, Enum):
    """Supported ATS platforms"""
    # Tier 1 - Most Common
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKABLE = "workable"
    ICIMS = "icims"

    # Tier 2 - Common
    SMARTRECRUITERS = "smartrecruiters"
    BAMBOOHR = "bamboohr"
    JAZZHR = "jazzhr"
    JOBVITE = "jobvite"
    BREEZY_HR = "breezyhr"
    FRESHTEAM = "freshteam"

    # Tier 3 - Less Common
    ASHBY = "ashby"
    PINPOINT = "pinpoint"
    POLYMER = "polymer"
    RECOOTY = "recooty"
    RECRUITEE = "recruitee"
    SUCCESSFACTORS = "successfactors"
    TEAMTAILOR = "teamtailor"
    TRAKSTAR = "trakstar"
    ZOHO_RECRUIT = "zoho_recruit"
    CAREERPLUG = "careerplug"
    COMEET = "comeet"
    CSOD = "csod"
    DAYFORCE = "dayforce"
    EIGHTFOLD = "eightfold"
    GOHIRE = "gohire"
    HIREHIVE = "hirehive"
    HIRINGTHING = "hiringthing"
    JOIN_COM = "join_com"
    ORACLECLOUD = "oraclecloud"
    PAYCOM = "paycom"
    PAYLOCITY = "paylocity"
    PERSONIO = "personio"
    PHENOMPEOPLE = "phenompeople"
    WORKDAY = "workday"

    # Fallback
    CUSTOM = "custom"
    UNKNOWN = "unknown"


class JobLocation(BaseModel):
    """Job location information"""
    raw_location: str = Field(..., description="Original location string from job board")
    city: Optional[str] = Field(None, description="Parsed city name")
    state: Optional[str] = Field(None, description="Parsed state/province")
    country: Optional[str] = Field(None, description="Parsed country")
    is_remote: bool = Field(False, description="Whether this is a remote position")
    is_hybrid: bool = Field(False, description="Whether this is a hybrid position")
    is_us: bool = Field(False, description="Whether this location is in the US")


class JobRole(BaseModel):
    """Job role/position information"""
    title: str = Field(..., description="Job title")
    department: Optional[str] = Field(None, description="Department or team")
    job_type: Optional[str] = Field(None, description="Full-time, Part-time, Contract, etc.")
    seniority: Optional[str] = Field(None, description="Entry, Mid, Senior, Lead, etc.")
    is_engineering: bool = Field(False, description="Engineering role")
    is_technology: bool = Field(False, description="Technology/IT role")


class Job(BaseModel):
    """Individual job posting"""
    job_id: str = Field(..., description="Unique job ID from ATS")
    title: str = Field(..., description="Job title")
    location: JobLocation = Field(..., description="Job location details")
    role: JobRole = Field(..., description="Job role classification")

    # Optional fields
    description: Optional[str] = Field(None, description="Job description (full text)")
    requirements: Optional[List[str]] = Field(None, description="Job requirements/qualifications")
    responsibilities: Optional[List[str]] = Field(None, description="Job responsibilities")
    posted_date: Optional[str] = Field(None, description="Date job was posted")
    apply_url: str = Field(..., description="URL to apply for this job")

    # Metadata
    scraped_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class JobBoardInfo(BaseModel):
    """Job board information"""
    url: str = Field(..., description="Job board URL")
    platform: ATSPlatform = Field(..., description="Detected ATS platform")
    total_jobs: int = Field(0, description="Total number of jobs found")
    us_jobs: int = Field(0, description="Number of US-based jobs")
    engineering_jobs: int = Field(0, description="Number of engineering/tech jobs")
    jobs: List[Job] = Field(default_factory=list, description="List of filtered jobs")
    discovered_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_scraped: Optional[str] = Field(None, description="Last time this board was scraped")


# ===========================
# ATS Platform Patterns
# ===========================

# URL patterns for detecting ATS platforms
ATS_URL_PATTERNS = {
    # Tier 1
    ATSPlatform.GREENHOUSE: [
        r"greenhouse\.io",
        r"boards\.greenhouse\.io",
        r"\.greenhouse\.io/",
    ],
    ATSPlatform.LEVER: [
        r"lever\.co",
        r"jobs\.lever\.co",
        r"\.lever\.co/",
    ],
    ATSPlatform.WORKABLE: [
        r"workable\.com",
        r"apply\.workable\.com",
        r"\.workable\.com/",
    ],
    ATSPlatform.ICIMS: [
        r"icims\.com",
        r"careers.*\.icims\.com",
        r"\.icims\.com/",
    ],

    # Tier 2
    ATSPlatform.SMARTRECRUITERS: [
        r"smartrecruiters\.com",
        r"jobs\.smartrecruiters\.com",
        r"careers\.smartrecruiters\.com",
    ],
    ATSPlatform.BAMBOOHR: [
        r"bamboohr\.com",
        r"\.bamboohr\.com/jobs",
    ],
    ATSPlatform.JAZZHR: [
        r"jazz\.co",
        r"\.jazz\.co/",
        r"applytojob\.com",
    ],
    ATSPlatform.JOBVITE: [
        r"jobvite\.com",
        r"jobs\.jobvite\.com",
    ],
    ATSPlatform.BREEZY_HR: [
        r"breezy\.hr",
        r"\.breezy\.hr/",
    ],
    ATSPlatform.FRESHTEAM: [
        r"freshteam\.com",
        r"\.freshteam\.com/jobs",
    ],

    # Tier 3
    ATSPlatform.ASHBY: [r"ashbyhq\.com", r"jobs\.ashbyhq\.com"],
    ATSPlatform.PINPOINT: [r"pinpointhq\.com"],
    ATSPlatform.POLYMER: [r"polymer\.co"],
    ATSPlatform.RECOOTY: [r"recooty\.com"],
    ATSPlatform.RECRUITEE: [r"recruitee\.com"],
    ATSPlatform.SUCCESSFACTORS: [r"successfactors\.com", r"successfactors\.eu"],
    ATSPlatform.TEAMTAILOR: [r"teamtailor\.com"],
    ATSPlatform.TRAKSTAR: [r"trakstar\.com"],
    ATSPlatform.ZOHO_RECRUIT: [r"zoho\.com/recruit"],
    ATSPlatform.CAREERPLUG: [r"careerplug\.com"],
    ATSPlatform.COMEET: [r"comeet\.com", r"comeet\.co"],
    ATSPlatform.CSOD: [r"csod\.com"],
    ATSPlatform.DAYFORCE: [r"dayforce\.com"],
    ATSPlatform.EIGHTFOLD: [r"eightfold\.ai"],
    ATSPlatform.GOHIRE: [r"gohire\.io"],
    ATSPlatform.HIREHIVE: [r"hirehive\.com"],
    ATSPlatform.HIRINGTHING: [r"hiringthing\.com"],
    ATSPlatform.JOIN_COM: [r"join\.com"],
    ATSPlatform.ORACLECLOUD: [r"oracle\.com/.*recruiting", r"taleo\.net"],
    ATSPlatform.PAYCOM: [r"paycom\.com"],
    ATSPlatform.PAYLOCITY: [r"paylocity\.com"],
    ATSPlatform.PERSONIO: [r"personio\.com", r"personio\.de"],
    ATSPlatform.PHENOMPEOPLE: [r"phenompeople\.com"],
    ATSPlatform.WORKDAY: [r"myworkdayjobs\.com", r"wd1\.myworkdayjobs\.com"],
}

# Keywords in URLs that suggest a careers/jobs page
CAREERS_PAGE_KEYWORDS = [
    "careers", "jobs", "join", "hiring", "openings", "positions",
    "opportunities", "work-with-us", "team", "apply", "employment"
]

# Engineering and technology job title keywords
ENGINEERING_KEYWORDS = [
    # Software Engineering
    "software engineer", "software developer", "programmer", "backend engineer",
    "frontend engineer", "full stack", "fullstack", "devops", "site reliability",
    "sre", "platform engineer", "cloud engineer", "data engineer",

    # Mechanical/Manufacturing Engineering
    "mechanical engineer", "manufacturing engineer", "process engineer",
    "production engineer", "quality engineer", "industrial engineer",
    "automation engineer", "robotics engineer", "design engineer",
    "cad engineer", "tooling engineer", "maintenance engineer",

    # Electrical/Electronics Engineering
    "electrical engineer", "electronics engineer", "hardware engineer",
    "embedded engineer", "firmware engineer", "pcb designer",
    "controls engineer", "instrumentation engineer",

    # Systems/Integration
    "systems engineer", "integration engineer", "test engineer",
    "validation engineer", "verification engineer",

    # Specialized Engineering
    "aerospace engineer", "automotive engineer", "biomedical engineer",
    "chemical engineer", "civil engineer", "materials engineer",
    "plastics engineer", "polymer engineer", "packaging engineer",

    # Technology/IT Roles
    "it specialist", "it manager", "network engineer", "security engineer",
    "systems administrator", "database administrator", "dba",
    "technical support", "help desk", "infrastructure engineer",

    # Data & AI
    "data scientist", "machine learning", "ml engineer", "ai engineer",
    "data analyst", "business intelligence",

    # Management/Leadership
    "engineering manager", "technical lead", "tech lead", "vp engineering",
    "director of engineering", "chief technology officer", "cto",
]

# US states for location filtering
US_STATES = {
    # State codes
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",

    # Full state names (lowercase for comparison)
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
}

# US cities (top 100 for quick matching)
US_MAJOR_CITIES = {
    "new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia",
    "san antonio", "san diego", "dallas", "san jose", "austin", "jacksonville",
    "fort worth", "columbus", "charlotte", "san francisco", "indianapolis",
    "seattle", "denver", "boston", "detroit", "nashville", "memphis",
    "portland", "oklahoma city", "las vegas", "baltimore", "milwaukee",
    "albuquerque", "tucson", "fresno", "sacramento", "mesa", "kansas city",
    "atlanta", "miami", "oakland", "tulsa", "minneapolis", "cleveland",
    "wichita", "arlington", "raleigh", "omaha", "long beach", "virginia beach",
}


# ===========================
# Job Board Scraper
# ===========================

class JobBoardScraper:
    """
    Main job board scraper that handles:
    - Job board URL discovery
    - ATS platform detection
    - Job scraping from multiple ATS platforms
    - US location filtering
    - Engineering/tech role filtering
    """

    def __init__(
        self,
        cache_file: str = ".job_board_cache.json",
        verbose: bool = True
    ):
        """
        Initialize job board scraper

        Args:
            cache_file: File to cache discovered job board URLs
            verbose: Enable verbose logging
        """
        self.cache_file = cache_file
        self.verbose = verbose
        self.cache = self._load_cache()

        # Statistics
        self.stats = {
            "boards_discovered": 0,
            "boards_cached": 0,
            "jobs_scraped": 0,
            "jobs_us_filtered": 0,
            "jobs_engineering_filtered": 0,
        }

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Load cached job board URLs"""
        try:
            with open(self.cache_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Warning:[/yellow] Could not load job board cache: {e}")
            return {}

    def _save_cache(self):
        """Save job board URLs to cache"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            if self.verbose:
                console.print(f"[yellow]Warning:[/yellow] Could not save job board cache: {e}")

    def detect_ats_platform(self, url: str) -> ATSPlatform:
        """
        Detect which ATS platform is being used based on URL

        Args:
            url: Job board URL

        Returns:
            ATSPlatform enum value
        """
        url_lower = url.lower()

        for platform, patterns in ATS_URL_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    return platform

        return ATSPlatform.UNKNOWN

    def find_job_board_url(self, company_url: str, page_links: List[str]) -> Optional[str]:
        """
        Find job board URL from a list of page links

        Args:
            company_url: Main company website URL
            page_links: List of links found on the company website

        Returns:
            Job board URL if found, None otherwise
        """
        # Check cache first
        cache_key = company_url.rstrip('/')
        if cache_key in self.cache:
            cached_board = self.cache[cache_key]
            if self.verbose:
                console.print(f"[cyan]✓ Job board URL from cache:[/cyan] {cached_board['url']}")
            self.stats["boards_cached"] += 1
            return cached_board['url']

        # Look for careers/jobs links
        candidates = []

        for link in page_links:
            link_lower = link.lower()

            # Check if link contains career/job keywords
            has_keyword = any(keyword in link_lower for keyword in CAREERS_PAGE_KEYWORDS)

            # Check if it's an external ATS link
            is_ats = any(
                any(re.search(pattern, link_lower) for pattern in patterns)
                for patterns in ATS_URL_PATTERNS.values()
            )

            if has_keyword or is_ats:
                candidates.append(link)

        if not candidates:
            return None

        # Prioritize external ATS platforms (they're usually the actual job board)
        for candidate in candidates:
            platform = self.detect_ats_platform(candidate)
            if platform != ATSPlatform.UNKNOWN:
                # Found an ATS platform link!
                self._cache_job_board(company_url, candidate, platform)
                self.stats["boards_discovered"] += 1
                if self.verbose:
                    console.print(f"[green]✓ Found job board:[/green] {candidate} ({platform.value})")
                return candidate

        # If no external ATS found, return the first careers link
        first_candidate = candidates[0]
        platform = ATSPlatform.CUSTOM
        self._cache_job_board(company_url, first_candidate, platform)
        self.stats["boards_discovered"] += 1
        if self.verbose:
            console.print(f"[yellow]⚠ Found careers page (custom ATS):[/yellow] {first_candidate}")
        return first_candidate

    def _cache_job_board(self, company_url: str, board_url: str, platform: ATSPlatform):
        """Cache discovered job board URL"""
        cache_key = company_url.rstrip('/')
        self.cache[cache_key] = {
            "url": board_url,
            "platform": platform.value,
            "discovered_at": datetime.now().isoformat()
        }
        self._save_cache()

    def is_us_location(self, location_str: str) -> tuple[bool, JobLocation]:
        """
        Determine if a job location is in the US

        Args:
            location_str: Location string from job posting

        Returns:
            (is_us, JobLocation object)
        """
        location_lower = location_str.lower()

        # Check for remote/hybrid
        is_remote = bool(re.search(r'\b(remote|work from home|wfh)\b', location_lower))
        is_hybrid = bool(re.search(r'\bhybrid\b', location_lower))

        # Check for US indicators
        is_us = False
        city = None
        state = None
        country = None

        # Check for explicit "United States" or "USA"
        if re.search(r'\b(united states|usa|u\.s\.a|us)\b', location_lower):
            is_us = True
            country = "United States"

        # Check for state codes (e.g., "CA", "NY", "TX")
        state_match = re.search(r'\b([A-Z]{2})\b', location_str)
        if state_match:
            state_code = state_match.group(1)
            if state_code in US_STATES:
                is_us = True
                state = state_code

        # Check for state names
        for state_name in US_STATES:
            if len(state_name) > 2 and state_name in location_lower:  # Full state name
                is_us = True
                state = state_name.title()
                break

        # Check for major US cities
        for city_name in US_MAJOR_CITIES:
            if city_name in location_lower:
                is_us = True
                city = city_name.title()
                break

        # Check for "Remote (US)" or "Remote - United States"
        if is_remote and re.search(r'remote.*\(us\)|remote.*united states', location_lower):
            is_us = True
            country = "United States"

        return is_us, JobLocation(
            raw_location=location_str,
            city=city,
            state=state,
            country=country,
            is_remote=is_remote,
            is_hybrid=is_hybrid,
            is_us=is_us
        )

    def is_engineering_role(self, job_title: str, department: Optional[str] = None) -> tuple[bool, bool]:
        """
        Determine if a job is an engineering or technology role

        Args:
            job_title: Job title
            department: Department name (optional)

        Returns:
            (is_engineering, is_technology)
        """
        title_lower = job_title.lower()
        dept_lower = department.lower() if department else ""
        combined = f"{title_lower} {dept_lower}"

        is_eng = False
        is_tech = False

        # Check title and department against keywords
        for keyword in ENGINEERING_KEYWORDS:
            if keyword in combined:
                is_eng = True
                is_tech = True
                break

        # Additional checks for technology roles
        if not is_tech:
            tech_keywords = ["it ", "information technology", "technical", "tech "]
            is_tech = any(kw in combined for kw in tech_keywords)

        return is_eng, is_tech

    # ===========================
    # Platform-Specific Scrapers
    # ===========================

    async def scrape_greenhouse(self, board_url: str) -> List[Job]:
        """
        Scrape jobs from Greenhouse ATS

        Greenhouse API endpoint: https://boards-api.greenhouse.io/v1/boards/{company}/jobs
        """
        from ats_scrapers.greenhouse_scraper import GreenhouseScraper

        scraper = GreenhouseScraper(verbose=self.verbose)
        raw_jobs = await scraper.scrape(board_url)

        # Convert to Job objects
        jobs = []
        for raw_job in raw_jobs:
            # Parse location
            is_us, location = self.is_us_location(raw_job.get('location', ''))
            if not is_us:
                continue  # Skip non-US jobs

            # Parse role
            is_eng, is_tech = self.is_engineering_role(
                raw_job.get('title', ''),
                raw_job.get('department')
            )
            if not (is_eng or is_tech):
                continue  # Skip non-engineering/tech roles

            # Create Job object
            role = JobRole(
                title=raw_job.get('title', ''),
                department=raw_job.get('department'),
                job_type=raw_job.get('job_type'),
                is_engineering=is_eng,
                is_technology=is_tech
            )

            job = Job(
                job_id=raw_job.get('job_id', ''),
                title=raw_job.get('title', ''),
                location=location,
                role=role,
                description=raw_job.get('description'),
                requirements=raw_job.get('requirements'),
                responsibilities=raw_job.get('responsibilities'),
                posted_date=raw_job.get('posted_date'),
                apply_url=raw_job.get('apply_url', '')
            )
            jobs.append(job)

        return jobs

    async def scrape_lever(self, board_url: str) -> List[Job]:
        """Scrape jobs from Lever ATS"""
        from ats_scrapers.lever_scraper import LeverScraper

        scraper = LeverScraper(verbose=self.verbose)
        raw_jobs = await scraper.scrape(board_url)

        # Convert to Job objects
        jobs = []
        for raw_job in raw_jobs:
            # Parse location
            is_us, location = self.is_us_location(raw_job.get('location', ''))
            if not is_us:
                continue

            # Parse role
            is_eng, is_tech = self.is_engineering_role(
                raw_job.get('title', ''),
                raw_job.get('department')
            )
            if not (is_eng or is_tech):
                continue

            # Create Job object
            role = JobRole(
                title=raw_job.get('title', ''),
                department=raw_job.get('department'),
                job_type=raw_job.get('job_type'),
                is_engineering=is_eng,
                is_technology=is_tech
            )

            job = Job(
                job_id=raw_job.get('job_id', ''),
                title=raw_job.get('title', ''),
                location=location,
                role=role,
                description=raw_job.get('description'),
                requirements=raw_job.get('requirements'),
                responsibilities=raw_job.get('responsibilities'),
                posted_date=raw_job.get('posted_date'),
                apply_url=raw_job.get('apply_url', '')
            )
            jobs.append(job)

        return jobs

    async def scrape_workable(self, board_url: str) -> List[Job]:
        """Scrape jobs from Workable ATS"""
        from ats_scrapers.workable_scraper import WorkableScraper

        scraper = WorkableScraper(verbose=self.verbose)
        raw_jobs = await scraper.scrape(board_url)

        # TODO: Implement conversion to Job objects (same pattern as above)
        jobs = []

        return jobs

    async def scrape_icims(self, board_url: str) -> List[Job]:
        """Scrape jobs from iCIMS ATS"""
        from ats_scrapers.icims_scraper import ICIMSScraper

        scraper = ICIMSScraper(verbose=self.verbose)
        raw_jobs = await scraper.scrape(board_url)

        # TODO: Implement conversion to Job objects (same pattern as above)
        jobs = []

        return jobs

    async def scrape_custom(self, board_url: str) -> List[Job]:
        """
        Generic scraper for custom/unknown ATS platforms
        Uses the main crawler to scrape the careers page
        """
        if self.verbose:
            console.print(f"[yellow]Using generic scraper for custom ATS...[/yellow]")

        # TODO: Implement generic scraper using crawl4ai
        jobs = []

        return jobs

    async def scrape_job_board(
        self,
        company_url: str,
        board_url: Optional[str] = None,
        page_links: Optional[List[str]] = None
    ) -> JobBoardInfo:
        """
        Main method to scrape a job board

        Args:
            company_url: Main company website URL
            board_url: Job board URL (if known)
            page_links: Links found on company website (for discovery)

        Returns:
            JobBoardInfo with all scraped jobs
        """
        # Discover job board URL if not provided
        if not board_url:
            if not page_links:
                raise ValueError("Either board_url or page_links must be provided")
            board_url = self.find_job_board_url(company_url, page_links)
            if not board_url:
                if self.verbose:
                    console.print(f"[yellow]⚠ No job board found for {company_url}[/yellow]")
                return JobBoardInfo(
                    url="",
                    platform=ATSPlatform.UNKNOWN,
                    total_jobs=0,
                    us_jobs=0,
                    engineering_jobs=0
                )

        # Detect platform
        platform = self.detect_ats_platform(board_url)

        if self.verbose:
            console.print(f"[cyan]Detected ATS platform:[/cyan] {platform.value}")

        # Scrape based on platform
        if platform == ATSPlatform.GREENHOUSE:
            jobs = await self.scrape_greenhouse(board_url)
        elif platform == ATSPlatform.LEVER:
            jobs = await self.scrape_lever(board_url)
        elif platform == ATSPlatform.WORKABLE:
            jobs = await self.scrape_workable(board_url)
        elif platform == ATSPlatform.ICIMS:
            jobs = await self.scrape_icims(board_url)
        else:
            # Use custom/generic scraper
            jobs = await self.scrape_custom(board_url)

        # Filter for US jobs and engineering roles
        filtered_jobs = []
        for job in jobs:
            # Check if US location
            if not job.location.is_us:
                continue

            # Check if engineering/tech role
            if not (job.role.is_engineering or job.role.is_technology):
                continue

            filtered_jobs.append(job)

        # Update statistics
        self.stats["jobs_scraped"] += len(jobs)
        self.stats["jobs_us_filtered"] += sum(1 for j in jobs if j.location.is_us)
        self.stats["jobs_engineering_filtered"] += len(filtered_jobs)

        return JobBoardInfo(
            url=board_url,
            platform=platform,
            total_jobs=len(jobs),
            us_jobs=sum(1 for j in jobs if j.location.is_us),
            engineering_jobs=len(filtered_jobs),
            jobs=filtered_jobs,
            last_scraped=datetime.now().isoformat()
        )


# ===========================
# Testing & Examples
# ===========================

async def main():
    """Example usage"""
    scraper = JobBoardScraper(verbose=True)

    # Example: Detect platform
    test_urls = [
        "https://boards.greenhouse.io/example",
        "https://jobs.lever.co/company",
        "https://apply.workable.com/company",
        "https://careers-company.icims.com",
    ]

    for url in test_urls:
        platform = scraper.detect_ats_platform(url)
        print(f"{url} → {platform.value}")

    # Example: Test location filtering
    test_locations = [
        "San Francisco, CA",
        "Remote (US)",
        "London, UK",
        "New York, NY",
        "Remote - United States",
        "Toronto, Canada",
    ]

    for loc in test_locations:
        is_us, location_obj = scraper.is_us_location(loc)
        print(f"{loc} → US: {is_us}")

    # Example: Test role filtering
    test_titles = [
        "Software Engineer",
        "Mechanical Engineer",
        "Sales Manager",
        "Manufacturing Engineer",
        "Product Manager",
        "IT Specialist",
    ]

    for title in test_titles:
        is_eng, is_tech = scraper.is_engineering_role(title)
        print(f"{title} → Eng: {is_eng}, Tech: {is_tech}")


if __name__ == "__main__":
    asyncio.run(main())
