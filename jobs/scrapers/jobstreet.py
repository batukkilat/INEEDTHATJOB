import asyncio
import json
import random
from datetime import datetime, timezone
from typing import Any

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from utils.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://id.jobstreet.com"


def _parse_job_item(item: dict, scraped_at: str) -> Job | None:
    external_id = str(item.get("id") or item.get("jobId") or item.get("listingId") or "")
    if not external_id:
        return None

    title = item.get("title") or item.get("jobTitle") or item.get("positionTitle") or ""
    if not title:
        return None

    advertiser = item.get("advertiser") or item.get("employer") or {}
    company = (
        advertiser.get("description") or advertiser.get("name")
        or item.get("companyName") or ""
    )

    location_data = item.get("jobLocation") or item.get("location") or {}
    if isinstance(location_data, dict):
        city = (
            location_data.get("label") or location_data.get("city")
            or location_data.get("area") or ""
        )
        location = city or "Indonesia"
    elif isinstance(location_data, list) and location_data:
        location = location_data[0] if isinstance(location_data[0], str) else "Indonesia"
    else:
        location = str(location_data) if location_data else "Indonesia"

    work_types = item.get("workTypes") or item.get("jobType") or []
    remote_type = None
    if isinstance(work_types, list):
        for wt in work_types:
            wt_lower = str(wt).lower()
            if "remote" in wt_lower:
                remote_type = "remote"
                break
            elif "hybrid" in wt_lower:
                remote_type = "hybrid"
    elif isinstance(work_types, str):
        if "remote" in work_types.lower():
            remote_type = "remote"
        elif "hybrid" in work_types.lower():
            remote_type = "hybrid"

    job_url = item.get("jobUrl") or item.get("url") or f"{_BASE_URL}/job/{external_id}"
    if job_url and not job_url.startswith("http"):
        job_url = _BASE_URL + job_url

    posted_date = item.get("listingDate") or item.get("postedAt") or item.get("createdAt") or None

    salary_data = item.get("salary") or {}
    salary_min = salary_data.get("minimum") if isinstance(salary_data, dict) else None
    salary_max = salary_data.get("maximum") if isinstance(salary_data, dict) else None

    teaser = item.get("teaser") or item.get("abstract") or item.get("snippet") or ""

    return Job(
        platform="jobstreet",
        external_id=external_id,
        url=job_url,
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


def _extract_jobs_from_response(data: Any) -> list[dict]:
    """Walk common JobStreet (Seek) response shapes."""
    if not isinstance(data, dict):
        return []
    # Chalice: data.data[]
    items = data.get("data") or []
    if isinstance(items, list) and items:
        return items
    # Wrapped: jobs[]
    items = data.get("jobs") or data.get("results") or data.get("jobSummaries") or []
    if isinstance(items, list):
        return items
    # NextData embedded: props.pageProps.jobDetails or .jobs
    props = (data.get("props") or {}).get("pageProps") or {}
    for key in ("jobs", "jobDetails", "results"):
        items = props.get(key) or []
        if isinstance(items, list) and items:
            return items
    return []


class JobStreetScraper(BaseScraper):
    platform = "jobstreet"

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("playwright_not_installed", hint="pip install playwright && playwright install chromium")
            return []

        if not settings.jobstreet_session_cookie:
            log.warning("jobstreet_no_session_cookie",
                        hint="Set JOBSTREET_SESSION_COOKIE in .env — log in at id.jobstreet.com, copy cookie header value")

        jobs: list[Job] = []
        seen_ids: set[str] = set()
        scraped_at = datetime.now(timezone.utc).isoformat()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="id-ID",
            )

            if settings.jobstreet_session_cookie:
                for name, val in _parse_cookie_string(settings.jobstreet_session_cookie):
                    try:
                        await context.add_cookies([{
                            "name": name, "value": val,
                            "domain": ".jobstreet.com", "path": "/",
                        }])
                    except Exception:
                        pass

            page = await context.new_page()
            captured: list[dict] = []

            async def on_response(response):
                url = response.url
                # Intercept Seek/JobStreet API calls
                if response.status == 200 and (
                    "chalice-search" in url
                    or "job-search" in url
                    or "jobsummary" in url
                    or ("jobstreet" in url and "/api/" in url)
                ):
                    try:
                        data = await response.json()
                        items = _extract_jobs_from_response(data)
                        if items:
                            captured.extend(items)
                            log.debug("jobstreet_intercepted", count=len(items), url=url)
                    except Exception:
                        pass

            page.on("response", on_response)

            for keyword in keywords:
                log.info("jobstreet_scrape_keyword", keyword=keyword)
                # JobStreet URL pattern: /Software-Engineer-jobs/in-Indonesia?page=N
                slug = keyword.replace(" ", "-")
                for page_num in range(1, max_pages + 1):
                    captured.clear()
                    url = f"{_BASE_URL}/{slug}-jobs/in-Indonesia?page={page_num}"
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=20000)
                    except Exception as e:
                        log.warning("jobstreet_page_load_timeout", keyword=keyword, page=page_num, error=str(e))
                        break

                    if not captured:
                        # Try __NEXT_DATA__ embedded JSON
                        items = await _extract_next_data(page)
                        if items:
                            captured.extend(items)

                    if not captured:
                        log.warning("jobstreet_no_data_intercepted", keyword=keyword, page=page_num,
                                    hint="Try logging in and updating JOBSTREET_SESSION_COOKIE")
                        break

                    before = len(jobs)
                    for item in captured:
                        job = _parse_job_item(item, scraped_at)
                        if job and job.external_id and job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            jobs.append(job)

                    if len(jobs) == before:
                        break
                    await asyncio.sleep(random.uniform(2.0, 4.0))

            await browser.close()

        log.info("jobstreet_scrape_complete", total=len(jobs))
        return jobs

    async def fetch_description(self, external_id: str) -> str | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        url = f"{_BASE_URL}/job/{external_id}"
        description: list[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            if settings.jobstreet_session_cookie:
                for name, val in _parse_cookie_string(settings.jobstreet_session_cookie):
                    try:
                        await context.add_cookies([{"name": name, "value": val, "domain": ".jobstreet.com", "path": "/"}])
                    except Exception:
                        pass
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                pass

            # Try __NEXT_DATA__ for full description
            items = await _extract_next_data(page)
            if items:
                for item in items:
                    desc = item.get("description") or item.get("jobDescription") or ""
                    if desc:
                        description.append(desc)
                        break

            if not description:
                el = await page.query_selector("[data-automation='jobDescription'], [class*='job-description']")
                if el:
                    description.append(await el.inner_text())

            await browser.close()

        return description[0] if description else None


async def _extract_next_data(page) -> list[dict]:
    """Extract job items from Next.js __NEXT_DATA__ JSON blob in page."""
    try:
        content = await page.evaluate(
            "() => document.getElementById('__NEXT_DATA__')?.textContent"
        )
        if not content:
            return []
        nd = json.loads(content)
        props = (nd.get("props") or {}).get("pageProps") or {}
        for key in ("jobs", "jobDetails", "results", "jobSummaries"):
            items = props.get(key)
            if isinstance(items, list) and items:
                return items
        # Some versions nest deeper
        data = props.get("data") or {}
        for key in ("jobs", "results", "jobSummaries"):
            items = data.get(key)
            if isinstance(items, list) and items:
                return items
    except Exception:
        pass
    return []


def _parse_cookie_string(cookie_str: str) -> list[tuple[str, str]]:
    """Parse 'name=value; name2=value2' into list of (name, value) pairs."""
    pairs = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, val = part.partition("=")
            pairs.append((name.strip(), val.strip()))
        elif part:
            pairs.append(("jobsdb_session", part))
    return pairs
