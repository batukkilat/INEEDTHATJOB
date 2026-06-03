import asyncio
import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from config import settings
from db.database import engine
from db.models import Job, Application, ActivityLog, Preferences
from generation.common import extract_contact_email
from jobs.scrapers.linkedin import LinkedInScraper
from jobs.scrapers.glints import GlintsScraper
from jobs.scrapers.jobstreet import JobStreetScraper
from jobs.scrapers.x import XScraper
from jobs.scrapers.threads import ThreadsScraper
from jobs.scorer import score_job, score_jobs_batch, title_matches_roles
from jobs.service import upsert_job
from utils.logging import get_logger

MIN_SCORE_TO_GENERATE = 0.55
SCORE_BATCH_SIZE = 10  # jobs per scoring batch
SCORE_CALL_DELAY = 0   # seconds between batches (0 = heuristic scorer, no rate limiting needed)

log = get_logger(__name__)

_running = False
_stage = ""
_stop_requested = False


def is_running() -> bool:
    return _running


def current_stage() -> str:
    return _stage


def request_stop() -> None:
    global _stop_requested
    _stop_requested = True


def stop_requested() -> bool:
    return _stop_requested


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


_SCRAPER_MAP = {
    "linkedin": LinkedInScraper,
    "glints": GlintsScraper,
    "jobstreet": JobStreetScraper,
    "x": XScraper,
    "threads": ThreadsScraper,
}


async def _scrape_phase(session: Session, max_pages: int, platforms: list[str]) -> list[Job]:
    keywords = _get_keywords(session)
    log.info("pipeline_scrape_start", keywords=keywords, max_pages=max_pages, platforms=platforms)
    _log_activity(session, "pipeline_scrape_start", details=f"platforms: {platforms} | keywords: {keywords}")

    raw_jobs: list[Job] = []
    for platform in platforms:
        cls = _SCRAPER_MAP.get(platform)
        if not cls:
            log.warning("scraper_not_found", platform=platform)
            continue
        scraper = cls()
        jobs = await scraper.scrape(max_pages=max_pages, keywords=keywords)
        before = len(jobs)
        jobs = [j for j in jobs if title_matches_roles(j.title, keywords)]
        filtered = before - len(jobs)
        if filtered:
            log.info("title_filter_dropped", platform=platform, count=filtered)
        raw_jobs.extend(jobs)
        _log_activity(session, "scraped", details=f"{platform}: {len(jobs)} listings found ({filtered} filtered by title)")

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
    needs_desc = [j for j in jobs if j.status == "new" and not j.description and j.external_id]
    log.info("pipeline_fetch_descriptions", count=len(needs_desc))
    scrapers: dict = {}
    for job in needs_desc:
        if _stop_requested:
            break
        cls = _SCRAPER_MAP.get(job.platform)
        if not cls:
            continue
        if job.platform not in scrapers:
            scrapers[job.platform] = cls()
        desc = await scrapers[job.platform].fetch_description(job.external_id)
        if desc:
            job.description = desc
            session.add(job)
        await asyncio.sleep(0.3)
    session.commit()


async def _score_phase(session: Session) -> int:
    new_jobs = list(session.exec(select(Job).where(Job.status == "new")).all())
    log.info("pipeline_score_start", count=len(new_jobs))
    _log_activity(session, "pipeline_score_start", details=f"Scoring {len(new_jobs)} jobs in batches of {SCORE_BATCH_SIZE}")

    scored = 0
    for i in range(0, len(new_jobs), SCORE_BATCH_SIZE):
        if _stop_requested:
            log.info("pipeline_score_stopped_early", scored=scored)
            break
        batch = new_jobs[i:i + SCORE_BATCH_SIZE]
        try:
            results = await asyncio.to_thread(score_jobs_batch, batch, session)
            for job, (overall, breakdown) in zip(batch, results):
                job.compatibility_score = overall
                job.score_breakdown = json.dumps(breakdown)
                job.status = "scored"
                session.add(job)
                _log_activity(session, "scored", job_id=job.id, details=f"{job.title} @ {job.company} — {overall:.0%}")
                scored += 1
            session.commit()
            log.info("pipeline_score_batch_done", batch=i // SCORE_BATCH_SIZE + 1, scored=scored)
        except Exception as e:
            log.error("score_batch_failed", batch_start=i, error=str(e))
            for job in batch:
                job.status = "scored"
                job.compatibility_score = 0.0
                session.add(job)
            session.commit()
        await asyncio.sleep(SCORE_CALL_DELAY)

    log.info("pipeline_score_done", scored=scored)
    return scored


async def _queue_phase(session: Session) -> int:
    """Move high-scoring jobs into review_ready and create stub Applications.
    No generation happens here — user triggers resume/cover letter/email on demand."""
    candidates = list(session.exec(
        select(Job)
        .where(Job.status == "scored")
        .where(Job.compatibility_score >= MIN_SCORE_TO_GENERATE)
        .order_by(Job.compatibility_score.desc())
    ).all())
    log.info("pipeline_queue_start", count=len(candidates))
    _log_activity(session, "pipeline_queue_start",
                  details=f"Queuing {len(candidates)} jobs (score ≥ {MIN_SCORE_TO_GENERATE:.0%}) for review")

    queued = 0
    for job in candidates:
        if _stop_requested:
            break
        try:
            # Skip if already queued (re-run dedup)
            existing = session.exec(
                select(Application).where(Application.job_id == job.id)
            ).first()
            if existing:
                job.status = "review_ready"
                session.add(job)
                session.commit()
                continue
            recipient_email = extract_contact_email(job.description or "")
            app = Application(
                job_id=job.id,
                recipient_email=recipient_email,
                apply_status="pending_review",
                created_at=_now(),
            )
            session.add(app)
            job.status = "review_ready"
            session.add(job)
            session.commit()
            queued += 1
        except Exception as e:
            log.error("queue_failed", job_id=job.id, error=str(e))

    log.info("pipeline_queue_done", queued=queued)
    return queued


async def run_pipeline(max_pages: int = 3, platforms: list[str] | None = None) -> dict:
    global _running, _stage, _stop_requested
    if _running:
        log.warning("pipeline_already_running")
        return {"status": "already_running"}

    _running = True
    _stop_requested = False
    if platforms is None:
        platforms = ["linkedin"]
    result = {"scraped": 0, "new": 0, "scored": 0, "status": "ok"}

    try:
        with Session(engine) as session:
            _log_activity(session, "pipeline_start")

            _stage = "scraping"
            jobs = await _scrape_phase(session, max_pages, platforms)
            result["scraped"] = len(jobs)
            result["new"] = sum(1 for j in jobs if j.status == "new")

            if _stop_requested:
                result["status"] = "stopped"
                _log_activity(session, "pipeline_stopped")
                return result

            _stage = "fetching"
            await _fetch_descriptions(session, jobs)

            if _stop_requested:
                result["status"] = "stopped"
                _log_activity(session, "pipeline_stopped")
                return result

            _stage = "scoring"
            scored = await _score_phase(session)
            result["scored"] = scored

            if _stop_requested:
                result["status"] = "stopped"
                _log_activity(session, "pipeline_stopped")
                return result

            _stage = "queuing"
            queued = await _queue_phase(session)
            result["queued"] = queued

            _log_activity(session, "pipeline_complete", details=json.dumps(result))
            log.info("pipeline_complete", **result)

    except Exception as e:
        log.error("pipeline_error", error=str(e))
        result["status"] = f"error: {e}"
        with Session(engine) as session:
            _log_activity(session, "failed", details=str(e))
    finally:
        _running = False
        _stage = ""

    return result
