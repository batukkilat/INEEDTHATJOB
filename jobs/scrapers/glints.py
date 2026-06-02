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

_BASE_URL = "https://glints.com"
_EXPLORE_URL = "https://glints.com/id/opportunities/jobs/explore"


def _parse_job_item(item: dict, scraped_at: str) -> Job | None:
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

    city = (
        (item.get("citySubDivision") or {}).get("name")
        or (item.get("city") or {}).get("name")
        or ""
    )
    location = f"{city}, Indonesia".strip(", ") if city else "Indonesia"

    work_arrangement = str(item.get("workArrangement") or item.get("workplaceType") or "").lower()
    remote_type = None
    if "remote" in work_arrangement:
        remote_type = "remote"
    elif "hybrid" in work_arrangement:
        remote_type = "hybrid"

    url = (
        item.get("url")
        or f"{_BASE_URL}/id/opportunities/jobs/{external_id}"
    )

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


def _extract_jobs_from_response(data: Any) -> list[dict]:
    """Walk common Glints GraphQL/REST response shapes."""
    if not isinstance(data, dict):
        return []
    # GraphQL: data.searchJobs.data or data.jobs.data
    gql = data.get("data") or {}
    for key in ("searchJobs", "jobs", "searchOpportunities"):
        node = gql.get(key) or {}
        items = node.get("data") or node.get("edges") or []
        if items:
            # unwrap edges pattern
            return [i.get("node", i) for i in items]
    # REST: data.data[] or data[] or results[]
    if isinstance(gql, list):
        return gql
    inner = data.get("data") or data.get("results") or []
    if isinstance(inner, list):
        return inner
    return []


class GlintsScraper(BaseScraper):
    platform = "glints"

    async def scrape(self, max_pages: int = 5, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("playwright_not_installed", hint="pip install playwright && playwright install chromium")
            return []

        if not settings.glints_session_cookie:
            log.warning("glints_no_session_cookie",
                        hint="Set GLINTS_SESSION_COOKIE in .env — log in at glints.com, copy the 'aqid' or session cookie value")

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
                )
            )

            if settings.glints_session_cookie:
                for name, val in _parse_cookie_string(settings.glints_session_cookie):
                    try:
                        await context.add_cookies([{
                            "name": name, "value": val,
                            "domain": ".glints.com", "path": "/",
                        }])
                    except Exception:
                        pass

            page = await context.new_page()

            # Intercept XHR/fetch responses that carry job data
            captured: list[dict] = []

            async def on_response(response):
                url = response.url
                if ("graphql" in url or "opportunities/jobs" in url or "api/jobs" in url) \
                        and response.status == 200:
                    try:
                        data = await response.json()
                        items = _extract_jobs_from_response(data)
                        if items:
                            captured.extend(items)
                            log.debug("glints_intercepted", count=len(items), url=url)
                    except Exception:
                        pass

            page.on("response", on_response)

            for keyword in keywords:
                log.info("glints_scrape_keyword", keyword=keyword)
                for page_num in range(max_pages):
                    captured.clear()
                    url = (
                        f"{_EXPLORE_URL}"
                        f"?keyword={keyword.replace(' ', '+')}"
                        f"&country=ID&locationName=Indonesia"
                        f"&page={page_num}"
                    )
                    try:
                        await page.goto(url, wait_until="networkidle", timeout=20000)
                    except Exception as e:
                        log.warning("glints_page_load_timeout", keyword=keyword, page=page_num, error=str(e))
                        break

                    if not captured:
                        # Fallback: try scrolling to trigger lazy load
                        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(2)

                    if not captured:
                        log.warning("glints_no_data_intercepted", keyword=keyword, page=page_num,
                                    hint="Try logging in and updating GLINTS_SESSION_COOKIE")
                        break

                    before = len(jobs)
                    for item in captured:
                        job = _parse_job_item(item, scraped_at)
                        if job and job.external_id and job.external_id not in seen_ids:
                            seen_ids.add(job.external_id)
                            jobs.append(job)

                    if len(jobs) == before:
                        break  # no new jobs on this page
                    await asyncio.sleep(random.uniform(1.5, 3.0))

            await browser.close()

        log.info("glints_scrape_complete", total=len(jobs))
        return jobs

    async def fetch_description(self, external_id: str) -> str | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return None

        url = f"{_BASE_URL}/id/opportunities/jobs/{external_id}"
        description: list[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            if settings.glints_session_cookie:
                for name, val in _parse_cookie_string(settings.glints_session_cookie):
                    try:
                        await context.add_cookies([{"name": name, "value": val, "domain": ".glints.com", "path": "/"}])
                    except Exception:
                        pass
            page = await context.new_page()

            async def on_response(response):
                if ("graphql" in response.url or f"jobs/{external_id}" in response.url) \
                        and response.status == 200:
                    try:
                        data = await response.json()
                        desc = (
                            (data.get("data") or {}).get("job", {}).get("description")
                            or (data.get("data") or {}).get("description")
                            or data.get("description")
                        )
                        if desc:
                            description.append(desc)
                    except Exception:
                        pass

            page.on("response", on_response)
            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
            except Exception:
                pass

            if not description:
                # DOM fallback
                el = await page.query_selector("[class*='description'], [class*='job-detail']")
                if el:
                    description.append(await el.inner_text())

            await browser.close()

        return description[0] if description else None


def _parse_cookie_string(cookie_str: str) -> list[tuple[str, str]]:
    """Parse 'name=value; name2=value2' into list of (name, value) pairs."""
    pairs = []
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            name, _, val = part.partition("=")
            pairs.append((name.strip(), val.strip()))
        elif part:
            # bare token — likely a single value (e.g. just the session ID)
            pairs.append(("aqid", part))
    return pairs
