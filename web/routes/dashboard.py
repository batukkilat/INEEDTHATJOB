from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application, ActivityLog

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


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
    return templates.TemplateResponse(request, "dashboard.html", {
        "current_page": "dashboard",
        "total_jobs": total_jobs,
        "pending_review": pending_review,
        "applied": applied,
        "recent_activity": recent_activity,
    })
