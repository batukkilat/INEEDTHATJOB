import asyncio
import random
from datetime import datetime, timezone

from curl_cffi import requests as cffi_requests

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from utils.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://id.jobstreet.com"
_SEARCH_URL = f"{_BASE_URL}/api/jobsearch/v5/search"

_HEADERS = {
    "accept": "application/json",
    "origin": _BASE_URL,
    "referer": f"{_BASE_URL}/Software-Engineer-jobs/in-Indonesia",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    ),
    "x-seek-site": "chalice",
}

_REMOTE_LABELS = {"jarak jauh", "remote", "work from home", "wfh"}
_HYBRID_LABELS = {"hibrida", "hybrid"}


def _parse_job_item(item: dict, scraped_at: str) -> Job | None:
    external_id = str(item.get("id") or "")
    if not external_id:
        return None

    title = item.get("title") or ""
    if not title:
        return None

    company = item.get("companyName") or (item.get("advertiser") or {}).get("description") or ""

    locations = item.get("locations") or []
    location = locations[0].get("label") if locations else "Indonesia"
    if not location:
        location = "Indonesia"

    remote_type = None
    arrangements = (item.get("workArrangements") or {}).get("data") or []
    for arr in arrangements:
        label = (arr.get("label") or {}).get("text", "").lower()
        if label in _REMOTE_LABELS:
            remote_type = "remote"
            break
        if label in _HYBRID_LABELS:
            remote_type = "hybrid"
            break
    if remote_type is None:
        for wt in item.get("workTypes") or []:
            wt_lower = str(wt).lower()
            if "remote" in wt_lower:
                remote_type = "remote"
                break
            if "hybrid" in wt_lower or "hibrida" in wt_lower:
                remote_type = "hybrid"
                break

    url = f"{_BASE_URL}/job/{external_id}"
    posted_date = item.get("listingDate") or None
    description = item.get("teaser") or None

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
        salary_min=None,
        salary_max=None,
        description=description,
    )


class JobStreetScraper(BaseScraper):
    platform = "jobstreet"

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        scraped_at = datetime.now(timezone.utc).isoformat()

        for keyword in keywords:
            log.info("jobstreet_scrape_keyword", keyword=keyword)
            for page_num in range(1, max_pages + 1):
                params = {
                    "siteKey": "ID-Main",
                    "where": "Indonesia",
                    "keywords": keyword,
                    "page": page_num,
                    "pageSize": 30,
                    "locale": "id-ID",
                }
                try:
                    resp = await asyncio.to_thread(
                        cffi_requests.get,
                        _SEARCH_URL,
                        params=params,
                        headers=_HEADERS,
                        impersonate="chrome",
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as e:
                    log.warning("jobstreet_request_failed", keyword=keyword, page=page_num, error=str(e))
                    break

                items = data.get("data") or []
                total = data.get("totalCount", 0)

                if not items:
                    log.warning("jobstreet_no_jobs", keyword=keyword, page=page_num)
                    break

                before = len(jobs)
                for item in items:
                    job = _parse_job_item(item, scraped_at)
                    if job and job.external_id not in seen_ids:
                        seen_ids.add(job.external_id)
                        jobs.append(job)

                log.debug("jobstreet_page_done", keyword=keyword, page=page_num,
                          new=len(jobs) - before, total=len(jobs))

                fetched_so_far = (page_num - 1) * 30 + len(items)
                if fetched_so_far >= total or len(jobs) == before:
                    break

                await asyncio.sleep(random.uniform(1.0, 2.0))

        log.info("jobstreet_scrape_complete", total=len(jobs))
        return jobs

    async def fetch_description(self, external_id: str) -> str | None:
        # GraphQL detail endpoint (from HAR)
        query = """
        query jobDetails($jobId: ID!, $zone: Zone!, $locale: Locale!, $languageCode: LanguageCodeIso!, $countryCode: CountryCodeIso2!, $timezone: Timezone!) {
          jobDetails(id: $jobId, tracking: {channel: "WEB", jobDetailsViewedCorrelationId: "", sessionId: ""}) {
            job {
              content(platform: WEB)
              title
              __typename
            }
            __typename
          }
        }
        """
        payload = {
            "operationName": "jobDetails",
            "variables": {
                "jobId": external_id,
                "zone": "asia-4",
                "locale": "id-ID",
                "languageCode": "id",
                "countryCode": "ID",
                "timezone": "Asia/Jakarta",
            },
            "query": query,
        }
        gql_headers = {
            "content-type": "application/json",
            "origin": _BASE_URL,
            "referer": f"{_BASE_URL}/job/{external_id}",
            "x-seek-site": "chalice",
            "user-agent": _HEADERS["user-agent"],
        }
        try:
            resp = await asyncio.to_thread(
                cffi_requests.post,
                f"{_BASE_URL}/graphql",
                json=payload,
                headers=gql_headers,
                impersonate="chrome",
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            return (data.get("data") or {}).get("jobDetails", {}).get("job", {}).get("content")
        except Exception as e:
            log.warning("jobstreet_fetch_description_failed", external_id=external_id, error=str(e))
            return None
