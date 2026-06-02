"""X (Twitter) job scraper — Playwright + LLM extraction.

Searches X for job-related posts using Indonesian and English queries.
Requires X_AUTH_TOKEN in .env (auth_token cookie from a logged-in session).
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

_BASE_URL = "https://x.com"

# Search queries per keyword — mix Indonesian and English
_QUERY_TEMPLATES = [
    "{kw} loker indonesia",
    "{kw} hiring indonesia",
    "lowongan {kw} indonesia",
    "{kw} job opening indonesia",
]


class XScraper(BaseScraper):
    platform = "x"

    async def scrape(self, max_pages: int = 3, keywords: list[str] | None = None) -> list[Job]:
        if not keywords:
            keywords = ["Backend Engineer", "Software Engineer", "Python Developer"]

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("playwright_not_installed", hint="pip install playwright && playwright install chromium")
            return []

        if not settings.x_auth_token:
            log.warning("x_no_auth_token",
                        hint="Set X_AUTH_TOKEN in .env — log in at x.com, copy 'auth_token' cookie value from DevTools")
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
                {"name": "auth_token", "value": settings.x_auth_token,
                 "domain": ".x.com", "path": "/"},
                {"name": "auth_token", "value": settings.x_auth_token,
                 "domain": ".twitter.com", "path": "/"},
            ])
            page = await context.new_page()

            for keyword in keywords:
                for template in _QUERY_TEMPLATES:
                    query = template.format(kw=keyword)
                    log.info("x_scrape_query", query=query)

                    posts = await self._scrape_search(page, query, max_pages)
                    log.info("x_posts_found", query=query, count=len(posts))

                    for post_id, post_text, post_url in posts:
                        if post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)
                        job = parse_post_to_job(
                            post_text=post_text,
                            post_url=post_url,
                            post_id=post_id,
                            platform="x",
                        )
                        if job:
                            jobs.append(job)
                            log.info("x_job_extracted", title=job.title, company=job.company)

                    await asyncio.sleep(random.uniform(2.0, 4.0))

            await browser.close()

        log.info("x_scrape_complete", total=len(jobs))
        return jobs

    async def _scrape_search(self, page, query: str,
                              max_pages: int) -> list[tuple[str, str, str]]:
        """Return list of (post_id, text, url) from X search results."""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"{_BASE_URL}/search?q={encoded}&f=live&src=typed_query"

        try:
            await page.goto(url, wait_until="networkidle", timeout=20000)
        except Exception as e:
            log.warning("x_page_load_timeout", query=query, error=str(e))
            return []

        posts = []
        # Scroll to load more posts
        for _ in range(max_pages):
            batch = await self._extract_posts(page)
            posts.extend(batch)
            if len(posts) >= 50:
                break
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            new_batch = await self._extract_posts(page)
            if len(new_batch) <= len(batch):
                break
            posts = new_batch

        # Deduplicate
        seen = set()
        unique = []
        for item in posts:
            if item[0] not in seen:
                seen.add(item[0])
                unique.append(item)
        return unique

    async def _extract_posts(self, page) -> list[tuple[str, str, str]]:
        """Extract (post_id, text, url) from current page state."""
        return await page.evaluate("""
            () => {
                const results = [];
                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                articles.forEach(article => {
                    try {
                        const textEl = article.querySelector('[data-testid="tweetText"]');
                        const text = textEl ? textEl.innerText : '';
                        if (!text || text.length < 30) return;

                        // Get permalink
                        const links = article.querySelectorAll('a[href*="/status/"]');
                        let href = '';
                        links.forEach(l => {
                            if (l.href.includes('/status/')) href = l.href;
                        });
                        if (!href) return;

                        const postId = href.match(/status\\/([0-9]+)/)?.[1] || href;
                        results.push([postId, text, href]);
                    } catch(e) {}
                });
                return results;
            }
        """)

    async def fetch_description(self, external_id: str) -> str | None:
        # Description already stored from post text at scrape time
        return None
