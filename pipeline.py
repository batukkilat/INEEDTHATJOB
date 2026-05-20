import asyncio
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from config import settings
from db.database import engine
from db.models import Job, ActivityLog, Preferences
from jobs.scrapers.linkedin import LinkedInScraper
from jobs.scorer import score_job
from jobs.service import upsert_job
from utils.logging import get_logger

log = get_logger(__name__)

_running = False


def is_running() -> bool:
    return _running


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_activity(session: Session, action: str, job_id: int | None = None, details: str | None = None) -> None:
    session.add(ActivityLog(timestamp=_now(), action=action, job_id=job_id, details=details))
    session.commit()


def _get_keywords(session: Session) -> list[str]:
    prefs = session.get(Preferences, 1)
    if prefs and prefs.target_roles:
        try:
            roles = json.loads(prefs.target_roles)
            if roles:
                return roles
        except (json.JSONDecodeError, TypeError):
            pass
    return ["Backend Engineer", "Software Engineer", "Python Developer"]


async def _scrape_phase(session: Session, max_pages: int) -> list[Job]:
    keywords = _get_keywords(session)
    log.info("pipeline_scrape_start", keywords=keywords, max_pages=max_pages)
    _log_activity(session, "pipeline_scrape_start", details=f"keywords: {keywords}")

    scraper = LinkedInScraper()
    raw_jobs = await scraper.scrape(max_pages=max_pages, keywords=keywords)

    saved = []
    new_count = 0
    for raw in raw_jobs:
        job = upsert_job(session, raw)
        saved.append(job)
        if job.status == "new":
            new_count += 1

    log.info("pipeline_scrape_done", total=len(raw_jobs), new=new_count)
    _log_activity(session, "scraped", details=f"Found {len(raw_jobs)} listings, {new_count} new")
    return saved


async def _fetch_descriptions(session: Session, jobs: list[Job]) -> None:
    """Fetch full descriptions for new jobs that don't have one yet."""
    scraper = LinkedInScraper()
    needs_desc = [j for j in jobs if j.status == "new" and not j.description and j.external_id]

    log.info("pipeline_fetch_descriptions", count=len(needs_desc))
    for job in needs_desc:
        desc = await scraper.fetch_description(job.external_id)
        if desc:
            job.description = desc
            session.add(job)
        await asyncio.sleep(1.0)
    session.commit()


async def _score_phase(session: Session) -> int:
    new_jobs = list(session.exec(select(Job).where(Job.status == "new")).all())
    log.info("pipeline_score_start", count=len(new_jobs))
    _log_activity(session, "pipeline_score_start", details=f"Scoring {len(new_jobs)} jobs")

    scored = 0
    for job in new_jobs:
        try:
            overall, breakdown = score_job(job, session)
            job.compatibility_score = overall
            job.score_breakdown = json.dumps(breakdown)
            job.status = "scored"
            session.add(job)
            session.commit()
            _log_activity(session, "scored", job_id=job.id, details=f"{job.title} @ {job.company} — {overall:.0%}")
            scored += 1
        except Exception as e:
            log.error("score_failed", job_id=job.id, error=str(e))
            job.status = "scored"  # move on even if scoring fails
            job.compatibility_score = 0.0
            session.add(job)
            session.commit()

    log.info("pipeline_score_done", scored=scored)
    return scored


async def run_pipeline(max_pages: int = 3) -> dict:
    global _running
    if _running:
        log.warning("pipeline_already_running")
        return {"status": "already_running"}

    _running = True
    result = {"scraped": 0, "new": 0, "scored": 0, "status": "ok"}

    try:
        with Session(engine) as session:
            _log_activity(session, "pipeline_start")

            jobs = await _scrape_phase(session, max_pages)
            result["scraped"] = len(jobs)
            result["new"] = sum(1 for j in jobs if j.status == "new")

            # Fetch descriptions for new jobs (best-effort)
            await _fetch_descriptions(session, jobs)

            scored = await _score_phase(session)
            result["scored"] = scored

            _log_activity(session, "pipeline_complete", details=json.dumps(result))
            log.info("pipeline_complete", **result)

    except Exception as e:
        log.error("pipeline_error", error=str(e))
        result["status"] = f"error: {e}"
        with Session(engine) as session:
            _log_activity(session, "failed", details=str(e))
    finally:
        _running = False

    return result
