from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application, ActivityLog
from config import settings
from utils import usage_tracker
import pipeline as pipe

router = APIRouter()


def _usage_meter(model: str, limit: int, today: dict) -> dict:
    entry = today.get(model, {})
    used = entry.get("prompt_tokens", 0) + entry.get("completion_tokens", 0)
    pct = min(100, round(used / limit * 100, 1)) if limit else 0
    return {"model": model, "used": used, "limit": limit, "calls": entry.get("calls", 0), "pct": pct}



@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)):
    total_jobs = session.exec(select(func.count(Job.id))).one()
    pending_review = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "pending_review")
    ).one()
    applied = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "submitted")
    ).one()
    recent_activity = list(
        session.exec(select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(20)).all()
    )
    # Last successful pipeline run
    last_run_log = session.exec(
        select(ActivityLog)
        .where(ActivityLog.action == "pipeline_complete")
        .order_by(ActivityLog.timestamp.desc())
    ).first()

    log_entries = list(session.exec(
        select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(40)
    ).all())
    log_entries.reverse()

    recent_jobs = list(session.exec(
        select(Job)
        .where(Job.compatibility_score.is_not(None))
        .order_by(Job.scraped_at.desc())
        .limit(20)
    ).all())

    today_usage = usage_tracker.get_today()
    usage_meters = [
        _usage_meter(settings.scoring_model, settings.scoring_model_tpd, today_usage),
        _usage_meter(settings.generation_model, settings.generation_model_tpd, today_usage),
    ]

    return templates.TemplateResponse(request, "dashboard.html", {
        "current_page": "dashboard",
        "total_jobs": total_jobs,
        "pending_review": pending_review,
        "applied": applied,
        "recent_activity": recent_activity,
        "last_run": last_run_log.timestamp if last_run_log else None,
        "is_pipeline_running": pipe.is_running(),
        "entries": log_entries,
        "recent_jobs": recent_jobs,
        "stage": pipe.current_stage(),
        "is_running": pipe.is_running(),
        "usage_meters": usage_meters,
    })
