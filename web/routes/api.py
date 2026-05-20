from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/stats", response_class=HTMLResponse)
def stats(request: Request, session: Session = Depends(get_session)):
    total_jobs = session.exec(select(func.count(Job.id))).one()
    pending_review = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "pending_review")
    ).one()
    applied = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "submitted")
    ).one()
    return templates.TemplateResponse(request, "partials/stats.html", {
        "total_jobs": total_jobs,
        "pending_review": pending_review,
        "applied": applied,
    })
