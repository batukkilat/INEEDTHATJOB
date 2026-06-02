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

# JobStreet Indonesia Chalice search API
_SEARCH_URL = "https://id.jobstreet.com/api/chalice-search/v4/search"
_BASE_URL = "https://id.jobstreet.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    "Referer": "https://id.jobstreet.com/",
}


class JobStreetScraper(BaseScraper):
    platform = "jobstreet"

    def _build_headers(self) -> dict:
        headers = dict(_HEADERS)
        if settings.jobstreet_session_cookie:
            headers["Cookie"] = settings.jobstreet_session_cookie
        return headers

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=self._build_headers(), follow_redirects=True, timeout=20) as client:
            for keyword in keywords:
                log.info("jobstreet_scrape_keyword", keyword=keyword)
                for page in range(1, max_pages + 1):
                    batch = await self._fetch_page(client, keyword, page)
                    if not batch:
                        break
                    for job in batch:
                        if job.external_id and job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            jobs.append(job)
                    await asyncio.sleep(random.uniform(2.0, 4.0))

        log.info("jobstreet_scrape_complete", total=len(jobs))
        return jobs

    async def _fetch_page(self, client: httpx.AsyncClient, keyword: str, page: int) -> list[Job]:
        params = {
            "siteKey": "ID-Main",
            "sourcesystem": "houston",
            "where": "Indonesia",
            "page": page,
            "pageSize": 30,
            "include": "seodata",
            "keywords": keyword,
            "seekSelectAllPages": "true",
        }
        try:
            r = await client.get(_SEARCH_URL, params=params)
            if r.status_code == 429:
                log.warning("jobstreet_rate_limited", page=page)
                await asyncio.sleep(30)
                return []
            if r.status_code != 200:
                log.warning("jobstreet_search_error", status=r.status_code)
                return []
            data = r.json()
            return self._parse_results(data)
        except (httpx.RequestError, ValueError) as e:
            log.error("jobstreet_request_error", error=str(e))
            return []

    def _parse_results(self, data: dict) -> list[Job]:
        jobs = []
        now = datetime.now(timezone.utc).isoformat()
        items = data.get("data", []) or data.get("jobs", []) or []
        for item in items:
            try:
                job = self._parse_item(item, now)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("jobstreet_item_parse_error", error=str(e))
        return jobs

    def _parse_item(self, item: dict, scraped_at: str) -> Job | None:
        external_id = str(item.get("id") or item.get("jobId") or "")
        if not external_id:
            return None

        title = item.get("title") or item.get("jobTitle") or ""
        if not title:
            return None

        advertiser = item.get("advertiser") or {}
        company = advertiser.get("description") or advertiser.get("name") or item.get("companyName") or ""

        location_data = item.get("jobLocation") or item.get("location") or {}
        if isinstance(location_data, dict):
            city = location_data.get("label") or location_data.get("city") or ""
            location = city or "Indonesia"
        else:
            location = str(location_data) or "Indonesia"

        work_types = item.get("workTypes") or []
        remote_type = None
        for wt in (work_types if isinstance(work_types, list) else []):
            wt_lower = str(wt).lower()
            if "remote" in wt_lower:
                remote_type = "remote"
                break
            elif "hybrid" in wt_lower:
                remote_type = "hybrid"

        url = item.get("jobUrl") or f"{_BASE_URL}/job/{external_id}"
        if url and not url.startswith("http"):
            url = _BASE_URL + url

        posted_date = item.get("listingDate") or item.get("postedAt") or None

        salary_data = item.get("salary") or {}
        salary_min = salary_data.get("minimum") if isinstance(salary_data, dict) else None
        salary_max = salary_data.get("maximum") if isinstance(salary_data, dict) else None

        teaser = item.get("teaser") or item.get("abstract") or ""

        return Job(
            platform="jobstreet",
            external_id=external_id,
            url=url,
            title=title,
            company=company,
            location=location,
            remote_type=remote_type,
            posted_date=posted_date,
            scraped_at=scraped_at,
            status="new",
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            description=teaser if teaser else None,
        )

    async def fetch_description(self, external_id: str) -> str | None:
        url = f"{_BASE_URL}/job/{external_id}"
        try:
            async with httpx.AsyncClient(headers=self._build_headers(), timeout=15) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return None
                soup = BeautifulSoup(r.text, "lxml")
                # JobStreet embeds job detail in a <script id="__NEXT_DATA__"> JSON blob
                next_data = soup.find("script", id="__NEXT_DATA__")
                if next_data:
                    import json
                    try:
                        nd = json.loads(next_data.string or "")
                        props = nd.get("props", {}).get("pageProps", {})
                        job_detail = props.get("jobDetail") or props.get("job") or {}
                        desc = job_detail.get("description") or job_detail.get("jobDescription") or ""
                        if desc:
                            # Strip HTML tags from description
                            return BeautifulSoup(desc, "lxml").get_text("\n", strip=True)
                    except (ValueError, KeyError):
                        pass
                # Fallback: look for description element
                desc_el = soup.find(attrs={"data-automation": "jobDescription"})
                return desc_el.get_text("\n", strip=True) if desc_el else None
        except httpx.RequestError:
            return None
