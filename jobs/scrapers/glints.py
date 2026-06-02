import asyncio
import random
from datetime import datetime, timezone

import httpx

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from utils.logging import get_logger

log = get_logger(__name__)

_SEARCH_URL = "https://glints.com/api/opportunities/jobs"
_DETAIL_URL = "https://glints.com/api/opportunities/jobs/{job_id}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8",
    "Referer": "https://glints.com/id/opportunities/jobs/explore",
}


class GlintsScraper(BaseScraper):
    platform = "glints"

    def _build_headers(self) -> dict:
        headers = dict(_HEADERS)
        if settings.glints_session_cookie:
            headers["Cookie"] = settings.glints_session_cookie
        return headers

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with httpx.AsyncClient(headers=self._build_headers(), follow_redirects=True, timeout=20) as client:
            for keyword in keywords:
                log.info("glints_scrape_keyword", keyword=keyword)
                for page in range(max_pages):
                    batch = await self._fetch_page(client, keyword, page)
                    if not batch:
                        break
                    for job in batch:
                        if job.external_id and job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            jobs.append(job)
                    await asyncio.sleep(random.uniform(1.5, 3.0))

        log.info("glints_scrape_complete", total=len(jobs))
        return jobs

    async def _fetch_page(self, client: httpx.AsyncClient, keyword: str, page: int) -> list[Job]:
        params = {
            "keyword": keyword,
            "countryCode": "ID",
            "page": page,
            "size": 30,
            "sort": "LATEST",
        }
        try:
            r = await client.get(_SEARCH_URL, params=params)
            if r.status_code == 429:
                log.warning("glints_rate_limited", page=page)
                await asyncio.sleep(30)
                return []
            if r.status_code != 200:
                log.warning("glints_search_error", status=r.status_code)
                return []
            data = r.json()
            return self._parse_results(data)
        except (httpx.RequestError, ValueError) as e:
            log.error("glints_request_error", error=str(e))
            return []

    def _parse_results(self, data: dict) -> list[Job]:
        jobs = []
        now = datetime.now(timezone.utc).isoformat()
        items = (
            data.get("data", {}).get("jobs", {}).get("data", [])
            or data.get("data", [])
            or []
        )
        for item in items:
            try:
                job = self._parse_item(item, now)
                if job:
                    jobs.append(job)
            except Exception as e:
                log.debug("glints_item_parse_error", error=str(e))
        return jobs

    def _parse_item(self, item: dict, scraped_at: str) -> Job | None:
        external_id = str(item.get("id") or item.get("externalId") or "")
        if not external_id:
            return None

        title = item.get("title") or item.get("name") or ""
        if not title:
            return None

        company = (
            (item.get("company") or {}).get("name")
            or item.get("companyName")
            or ""
        )
        city = (item.get("citySubDivision") or {}).get("name") or ""
        country = (item.get("country") or {}).get("name") or "Indonesia"
        location = f"{city}, {country}".strip(", ") if city else country

        work_arrangement = (item.get("workArrangement") or "").lower()
        remote_type = None
        if "remote" in work_arrangement:
            remote_type = "remote"
        elif "hybrid" in work_arrangement:
            remote_type = "hybrid"

        url = f"https://glints.com/id/opportunities/jobs/{external_id}"
        posted_date = item.get("createdAt") or item.get("updatedAt") or None

        salary_min = item.get("salaryRangeFrom") or item.get("minSalary")
        salary_max = item.get("salaryRangeTo") or item.get("maxSalary")

        description = item.get("description") or ""

        return Job(
            platform="glints",
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
            description=description if description else None,
        )

    async def fetch_description(self, external_id: str) -> str | None:
        url = _DETAIL_URL.format(job_id=external_id)
        try:
            async with httpx.AsyncClient(headers=self._build_headers(), timeout=15) as client:
                r = await client.get(url)
                if r.status_code != 200:
                    return None
                data = r.json()
                job_data = data.get("data", {})
                return job_data.get("description") or None
        except (httpx.RequestError, ValueError):
            return None
