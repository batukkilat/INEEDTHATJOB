"""Phase 2: job ingestion, deduplication, and status management."""
from sqlmodel import Session, select
from db.models import Job


def get_job(session: Session, job_id: int) -> Job | None:
    return session.get(Job, job_id)


def upsert_job(session: Session, job: Job) -> Job:
    """Insert job or skip if (platform, external_id) already exists."""
    if job.platform and job.external_id:
        existing = session.exec(
            select(Job).where(Job.platform == job.platform, Job.external_id == job.external_id)
        ).first()
        if existing:
            return existing
    session.add(job)
    session.commit()
    session.refresh(job)
    return job
