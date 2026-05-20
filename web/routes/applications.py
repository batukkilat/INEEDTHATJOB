from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from db.database import get_session
from db.models import Application, Job

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")


@router.get("/review", response_class=HTMLResponse)
def review_queue(request: Request, session: Session = Depends(get_session)):
    applications = list(
        session.exec(
            select(Application)
            .where(Application.apply_status == "pending_review")
            .order_by(Application.created_at.desc())
        ).all()
    )
    return templates.TemplateResponse(request, "applications/review.html", {
        "current_page": "review",
        "applications": applications,
    })


@router.post("/review/{app_id}/approve", response_class=HTMLResponse)
def approve_application(app_id: int, request: Request, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.apply_status = "approved"
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/reject", response_class=HTMLResponse)
def reject_application(app_id: int, request: Request, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.apply_status = "rejected"
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.get("/history", response_class=HTMLResponse)
def application_history(request: Request, session: Session = Depends(get_session)):
    applications = list(
        session.exec(
            select(Application)
            .where(Application.apply_status != "pending_review")
            .order_by(Application.created_at.desc())
        ).all()
    )
    return templates.TemplateResponse(request, "applications/history.html", {
        "current_page": "history",
        "applications": applications,
    })
