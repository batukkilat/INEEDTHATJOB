import asyncio
from pathlib import Path

from apply.browser.base import BaseATSAdapter, _parse_cookie_string
from config import settings
from db.models import Application, Job
from utils.logging import get_logger

log = get_logger(__name__)

_APPLY_BTNS = [
    "button:has-text('Lamar Sekarang')",
    "button:has-text('Lamar')",
    "a:has-text('Lamar Sekarang')",
    "button:has-text('Apply Now')",
    "button:has-text('Apply')",
    "[data-testid='apply-button']",
    "[data-cy='apply-button']",
]
_SUBMIT_BTNS = [
    "button:has-text('Kirim Lamaran')",
    "button:has-text('Submit Application')",
    "button[type='submit']:has-text('Lamar')",
    "button[type='submit']",
]


class GlintsAdapter(BaseATSAdapter):
    async def apply(self, job: Job, app: Application) -> bool:
        if not settings.glints_session_cookie:
            log.warning("glints_adapter_no_cookie")
            return False

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.error("playwright_not_installed")
            return False

        ss_dir = Path(settings.screenshot_dir)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            )
            for name, val in _parse_cookie_string(settings.glints_session_cookie):
                try:
                    await ctx.add_cookies([{"name": name, "value": val, "domain": ".glints.com", "path": "/"}])
                except Exception:
                    pass

            page = await ctx.new_page()
            try:
                await page.goto(job.url, wait_until="networkidle", timeout=25000)
                await page.screenshot(path=str(ss_dir / f"glints_{app.id}_01_loaded.png"))

                apply_btn = None
                for sel in _APPLY_BTNS:
                    loc = page.locator(sel).first
                    if await loc.count() > 0:
                        apply_btn = loc
                        break

                if not apply_btn:
                    log.warning("glints_no_apply_btn", job_id=job.id)
                    await page.screenshot(path=str(ss_dir / f"glints_{app.id}_fail_no_btn.png"))
                    return False

                await apply_btn.click()
                await asyncio.sleep(2)
                await page.screenshot(path=str(ss_dir / f"glints_{app.id}_02_form.png"))

                # Cover letter textarea
                if app.cover_letter:
                    for sel in [
                        "textarea[placeholder*='cover']", "textarea[placeholder*='lamaran']",
                        "textarea[name*='cover']", "textarea[aria-label*='cover']", "textarea",
                    ]:
                        cl = page.locator(sel).first
                        if await cl.count() > 0:
                            await cl.fill(app.cover_letter[:3000])
                            break

                # Resume upload
                resume_path = app.resume_pdf_path or app.resume_path
                if resume_path and Path(resume_path).exists():
                    file_input = page.locator("input[type='file']").first
                    if await file_input.count() > 0:
                        await file_input.set_input_files(resume_path)
                        await asyncio.sleep(1)

                # Submit
                for sel in _SUBMIT_BTNS:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click()
                        break

                await asyncio.sleep(3)
                await page.screenshot(path=str(ss_dir / f"glints_{app.id}_03_result.png"))

                # Success indicators
                for ind in [
                    "text='Lamaran terkirim'", "text='Application submitted'",
                    "text='Berhasil'", "[data-testid='success-message']",
                ]:
                    if await page.locator(ind).count() > 0:
                        log.info("glints_apply_success", job_id=job.id, app_id=app.id)
                        return True

                # URL left the job page = likely submitted
                if job.external_id and job.external_id not in page.url:
                    log.info("glints_apply_success_redirected", job_id=job.id)
                    return True

                log.warning("glints_apply_uncertain", job_id=job.id)
                return False

            except Exception as e:
                log.error("glints_apply_error", error=str(e), job_id=job.id)
                try:
                    await page.screenshot(path=str(ss_dir / f"glints_{app.id}_error.png"))
                except Exception:
                    pass
                return False
            finally:
                await browser.close()
