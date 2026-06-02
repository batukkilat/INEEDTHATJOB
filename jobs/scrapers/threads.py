"""Threads (Meta) job scraper — Playwright + LLM extraction.

Searches Threads for job-related posts using Indonesian hashtags and keywords.
Requires THREADS_SESSION_COOKIE in .env (sessionid cookie from a logged-in session).
"""
import asyncio
import random
from datetime import datetime, timezone

from config import settings
from db.models import Job
from jobs.scrapers.base import BaseScraper
from jobs.scrapers.social_parser import parse_post_to_job
from utils.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://www.threads.net"

_QUERY_TEMPLATES = [
    "loker {kw}",
    "lowongan {kw}",
    "{kw} hiring",
    "{kw} job indonesia",
]


class ThreadsScraper(BaseScraper):
    platform = "threads"

    async def scrape(self, max_pages: int = 3, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("playwright_not_installed", hint="pip install playwright && playwright install chromium")
            return []

        if not settings.threads_session_cookie:
            log.warning("threads_no_session_cookie",
                        hint="Set THREADS_SESSION_COOKIE in .env — log in at threads.net, copy 'sessionid' cookie value")
            return []

        jobs: list[Job] = []
        seen_ids: set[str] = set()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            await context.add_cookies([
                {"name": "sessionid", "value": settings.threads_session_cookie,
                 "domain": ".threads.net", "path": "/"},
            ])
            page = await context.new_page()

            for keyword in keywords:
                for template in _QUERY_TEMPLATES:
                    query = template.format(kw=keyword)
                    log.info("threads_scrape_query", query=query)

                    posts = await self._scrape_search(page, query, max_pages)
                    log.info("threads_posts_found", query=query, count=len(posts))

                    for post_id, post_text, post_url in posts:
                        if post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)
                        job = parse_post_to_job(
                            post_text=post_text,
                            post_url=post_url,
                            post_id=post_id,
                            platform="threads",
                        )
                        if job:
                            jobs.append(job)
                            log.info("threads_job_extracted", title=job.title, company=job.company)

                    await asyncio.sleep(random.uniform(2.0, 4.0))

            await browser.close()

        log.info("threads_scrape_complete", total=len(jobs))
        return jobs

    async def _scrape_search(self, page, query: str,
                              max_pages: int) -> list[tuple[str, str, str]]:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"{_BASE_URL}/search?q={encoded}&serp_type=default"

        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception as e:
            log.warning("threads_page_load_timeout", query=query, error=str(e))
            return []

        posts = []
        for _ in range(max_pages):
            batch = await self._extract_posts(page)
            posts.extend(batch)
            if len(posts) >= 40:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2.5)
            new_batch = await self._extract_posts(page)
            if len(new_batch) <= len(batch):
                break
            posts = new_batch

        seen = set()
        unique = []
        for item in posts:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
        return unique

    async def _extract_posts(self, page) -> list[tuple[str, str, str]]:
        """Extract (post_id, text, url) from current Threads page state."""
        return await page.evaluate("""
            () => {
                const results = [];
                // Threads post containers — class names vary, try multiple selectors
                const candidates = [
                    ...document.querySelectorAll('article'),
                    ...document.querySelectorAll('[class*="post"]'),
                    ...document.querySelectorAll('[class*="thread"]'),
                ].filter((el, i, arr) => arr.indexOf(el) === i);  // dedupe

                candidates.forEach(el => {
                    try {
                        const text = el.innerText;
                        if (!text || text.length < 30) return;

                        // Find permalink — Threads uses /t/{postId}
                        const links = el.querySelectorAll('a[href*="/t/"]');
                        let href = '';
                        links.forEach(l => { if (l.href.includes('/t/')) href = l.href; });
                        if (!href) return;

                        const postId = href.match(/\\/t\\/([A-Za-z0-9_-]+)/)?.[1] || href;
                        results.push([postId, text.slice(0, 1000), href]);
                    } catch(e) {}
                });
                return results;
            }
        """)

    async def fetch_description(self, external_id: str) -> str | None:
        return None
