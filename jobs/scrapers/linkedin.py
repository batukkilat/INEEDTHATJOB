import asyncio
import random
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from utils.logging import get_logger

log = get_logger(__name__)

# Indonesia LinkedIn geoId
_INDONESIA_GEO_ID = "102478259"

_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class LinkedInScraper(BaseScraper):
    platform = "linkedin"

    def _build_headers(self) -> dict:
        headers = dict(_HEADERS)
        if settings.linkedin_session_cookie:
            headers["Cookie"] = f"li_at={settings.linkedin_session_cookie}"
        return headers

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Full Stack Developer", "Python Developer"]

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=self._build_headers(), follow_redirects=True, timeout=20) as client:
            for keyword in keywords:
                log.info("linkedin_scrape_keyword", keyword=keyword)
                for page in range(max_pages):
                    start = page * 25
                    batch = await self._fetch_search_page(client, keyword, start)
                    if not batch:
                        break
                    for job in batch:
                        if job.external_id and job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            jobs.append(job)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

        log.info("linkedin_scrape_complete", total=len(jobs))
        return jobs

    async def _fetch_search_page(
        self, client: httpx.AsyncClient, keywords: str, start: int
    ) -> list[Job]:
        params = {
            "keywords": keywords,
            "location": "Indonesia",
            "geoId": _INDONESIA_GEO_ID,
            "start": start,
            "count": 25,
            "f_JT": "F",   # full-time
        }
        try:
            r = await client.get(_SEARCH_URL, params=params)
            if r.status_code == 429:
                log.warning("linkedin_rate_limited", start=start)
                await asyncio.sleep(30)
                return []
            if r.status_code != 200:
                log.warning("linkedin_search_error", status=r.status_code)
                return []
            return self._parse_search_html(r.text)
        except httpx.RequestError as e:
            log.error("linkedin_request_error", error=str(e))
            return []

    def _parse_search_html(self, html: str) -> list[Job]:
        soup = BeautifulSoup(html, "lxml")
        jobs = []
        now = datetime.now(timezone.utc).isoformat()

        for card in soup.find_all("div", class_=re.compile(r"base-card")):
            try:
                job = self._parse_card(card, now)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("linkedin_card_parse_error", error=str(e))

        return jobs

    def _parse_card(self, card, scraped_at: str) -> Job | None:
        # Extract job ID from data-entity-urn or href
        external_id = None
        urn = card.get("data-entity-urn", "")
        if urn:
            m = re.search(r"jobPosting:(\d+)", urn)
            if m:
                external_id = m.group(1)

        if not external_id:
            link = card.find("a", href=re.compile(r"/jobs/view/"))
            if link:
                m = re.search(r"/jobs/view/(\d+)", link.get("href", ""))
                if m:
                    external_id = m.group(1)

        if not external_id:
            return None

        # Title
        title_el = card.find(["h3", "h2"], class_=re.compile(r"title|job-title"))
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            return None

        # Company
        company_el = card.find(["h4", "a"], class_=re.compile(r"subtitle|company"))
        company = company_el.get_text(strip=True) if company_el else ""

        # Location
        location_el = card.find(class_=re.compile(r"location"))
        location = location_el.get_text(strip=True) if location_el else "Indonesia"

        # URL
        url = f"https://www.linkedin.com/jobs/view/{external_id}/"

        # Remote type from location text
        remote_type = None
        loc_lower = location.lower()
        if "remote" in loc_lower:
            remote_type = "remote"
        elif "hybrid" in loc_lower:
            remote_type = "hybrid"

        # Posted date
        time_el = card.find("time")
        posted_date = time_el.get("datetime", "") if time_el else ""

        return Job(
            platform="linkedin",
            external_id=external_id,
            url=url,
            title=title,
            company=company,
            location=location,
            remote_type=remote_type,
            posted_date=posted_date or None,
            scraped_at=scraped_at,
            status="new",
        )

    async def fetch_description(self, external_id: str) -> str | None:
        """Fetch the full job description for a single job ID."""
        url = _DETAIL_URL.format(job_id=external_id)
        try:
            async with httpx.AsyncClient(headers=self._build_headers(), timeout=15) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return None
                soup = BeautifulSoup(r.text, "lxml")
                desc_el = soup.find(class_=re.compile(r"description|show-more-less-html"))
                return desc_el.get_text("\n", strip=True) if desc_el else None
        except httpx.RequestError:
            return None
