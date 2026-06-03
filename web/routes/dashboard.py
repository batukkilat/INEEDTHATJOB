import json
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application, ActivityLog, Skill, Experience, Preferences
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
    good_matches = session.exec(
        select(func.count(Job.id))
        .where(Job.compatibility_score >= 0.55)
    ).one()
    pending_review = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "pending_review")
    ).one()
    applied = session.exec(
        select(func.count(Application.id)).where(Application.apply_status.in_(["submitted", "applied_manually"]))
    ).one()

    # Onboarding state
    skills_count = session.exec(select(func.count(Skill.id))).one()
    exp_count = session.exec(select(func.count(Experience.id))).one()
    has_profile = (skills_count + exp_count) > 0
    prefs = session.get(Preferences, 1)
    has_target_roles = bool(
        prefs and prefs.target_roles and
        json.loads(prefs.target_roles if isinstance(prefs.target_roles, str) else "[]")
    )

    # Score distribution bands
    scored_total = session.exec(
        select(func.count(Job.id)).where(Job.compatibility_score.is_not(None))
    ).one()
    score_bands = []
    for label, lo, hi, color in [
        ("Excellent", 0.75, 1.01, "bg-emerald-500"),
        ("Good",      0.55, 0.75, "bg-blue-500"),
        ("Weak",      0.35, 0.55, "bg-amber-400"),
        ("Poor",      0.00, 0.35, "bg-gray-300"),
    ]:
        n = session.exec(
            select(func.count(Job.id))
            .where(Job.compatibility_score >= lo)
            .where(Job.compatibility_score < hi)
        ).one()
        pct = round(n / scored_total * 100) if scored_total else 0
        score_bands.append({"label": label, "count": n, "pct": pct, "color": color})

    last_run_log = session.exec(
        select(ActivityLog)
        .where(ActivityLog.action == "pipeline_complete")
        .order_by(ActivityLog.timestamp.desc())
    ).first()

    last_run_summary = None
    if last_run_log and last_run_log.details:
        try:
            d = json.loads(last_run_log.details)
            last_run_summary = {
                "scraped": d.get("scraped", 0),
                "scored": d.get("scored", 0),
                "queued": d.get("queued", 0),
                "timestamp": last_run_log.timestamp,
            }
        except Exception:
            pass

    log_entries = list(session.exec(
        select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(40)
    ).all())
    log_entries.reverse()

    recent_jobs = list(session.exec(
        select(Job)
        .where(Job.compatibility_score.is_not(None))
        .order_by(Job.compatibility_score.desc())
        .limit(10)
    ).all())

    today_usage = usage_tracker.get_today()
    usage_meters = [
        _usage_meter(settings.scoring_model, settings.scoring_model_tpd, today_usage),
        _usage_meter(settings.generation_model, settings.generation_model_tpd, today_usage),
    ]
    ai_pct = max((m["pct"] for m in usage_meters), default=0)

    return templates.TemplateResponse(request, "dashboard.html", {
        "current_page": "dashboard",
        "total_jobs": total_jobs,
        "good_matches": good_matches,
        "pending_review": pending_review,
        "applied": applied,
        "has_profile": has_profile,
        "has_target_roles": has_target_roles,
        "last_run": last_run_log.timestamp if last_run_log else None,
        "last_run_summary": last_run_summary,
        "score_bands": score_bands,
        "scored_total": scored_total,
        "is_pipeline_running": pipe.is_running(),
        "entries": log_entries,
        "recent_jobs": recent_jobs,
        "stage": pipe.current_stage(),
        "is_running": pipe.is_running(),
        "usage_meters": usage_meters,
        "ai_pct": ai_pct,
    })
