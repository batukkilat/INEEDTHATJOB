"""Phase 4: application engine — picks approved applications and submits them."""
import asyncio
import random
from datetime import datetime, timezone

from sqlmodel import Session, select

from apply.email_sender import send_application_email
from config import settings
from db.database import engine
from db.models import Application, ActivityLog
from utils.logging import get_logger

log = get_logger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(session: Session, action: str, job_id: int | None = None, details: str | None = None) -> None:
    session.add(ActivityLog(timestamp=_now(), action=action, job_id=job_id, details=details))
    session.commit()


async def send_application(app_id: int) -> dict:
    """Send a single approved application. Returns {"ok": bool, "error": str|None}."""
    with Session(engine) as session:
        app = session.get(Application, app_id)
        if not app:
            return {"ok": False, "error": "Application not found"}
        if not app.recipient_email:
            return {"ok": False, "error": "No recipient email set"}
        if not app.email_subject or not app.email_body:
            return {"ok": False, "error": "Email not generated yet"}

        app.apply_status = "applying"
        session.add(app)
        session.commit()

        try:
            send_application_email(
                to=app.recipient_email,
                subject=app.email_subject,
                body=app.email_body,
                resume_path=app.resume_path,
                pdf_path=app.resume_pdf_path,
            )
            app.apply_status = "submitted"
            app.applied_at = _now()
            session.add(app)
            _log(session, "submitted", job_id=app.job_id,
                 details=f"Email sent to {app.recipient_email}")
            return {"ok": True, "error": None}
        except Exception as exc:
            app.apply_status = "failed"
            app.error_log = str(exc)
            session.add(app)
            _log(session, "failed", job_id=app.job_id, details=str(exc))
            log.error("application_send_failed", app_id=app_id, error=str(exc))
            return {"ok": False, "error": str(exc)}


async def run_applications() -> dict:
    """Send all approved applications that have a recipient email set.

    Returns {"sent": int, "failed": int, "skipped": int}.
    """
    with Session(engine) as session:
        approved = list(session.exec(
            select(Application).where(Application.apply_status == "approved")
        ).all())

    sendable = [a for a in approved if a.recipient_email and a.email_subject and a.email_body]
    skipped = len(approved) - len(sendable)

    sent = failed = 0
    for app in sendable:
        result = await send_application(app.id)
        if result["ok"]:
            sent += 1
        else:
            failed += 1
        if sendable.index(app) < len(sendable) - 1:
            delay = random.uniform(settings.apply_delay_min_seconds, settings.apply_delay_max_seconds)
            await asyncio.sleep(delay)

    log.info("run_applications_done", sent=sent, failed=failed, skipped=skipped)
    return {"sent": sent, "failed": failed, "skipped": skipped}
