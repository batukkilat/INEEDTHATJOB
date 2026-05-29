from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse
from web.templates_env import templates
from sqlmodel import Session, select
from db.database import get_session
from db.models import Application, Job
from generation.cover_letter import generate_cover_letter
from generation.email_composer import compose_email
from apply.engine import send_application

router = APIRouter()


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
def approve_application(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.apply_status = "approved"
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/reject", response_class=HTMLResponse)
def reject_application(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.apply_status = "rejected"
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/generate-cover-letter", response_class=HTMLResponse)
async def generate_cover_letter_route(app_id: int, request: Request,
                                      session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Application not found", status_code=404)
    job = session.get(Job, app.job_id)
    app.cover_letter = await generate_cover_letter(job, session)
    session.add(app)
    session.commit()
    return templates.TemplateResponse(request, "partials/cover_letter_block.html", {"app": app})


@router.post("/review/{app_id}/generate-email", response_class=HTMLResponse)
async def generate_email_route(app_id: int, request: Request,
                               session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Application not found", status_code=404)
    job = session.get(Job, app.job_id)
    app.email_subject, app.email_body = await compose_email(job, session)
    session.add(app)
    session.commit()
    return templates.TemplateResponse(request, "partials/email_block.html", {"app": app})


@router.put("/review/{app_id}/cover-letter", response_class=HTMLResponse)
def update_cover_letter(app_id: int, cover_letter: str = Form(...),
                        session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.cover_letter = cover_letter
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.put("/review/{app_id}/email", response_class=HTMLResponse)
def update_email(app_id: int, email_body: str = Form(...),
                 session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.email_body = email_body
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.put("/review/{app_id}/recipient-email", response_class=HTMLResponse)
def update_recipient_email(app_id: int, recipient_email: str = Form(...),
                           session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.recipient_email = recipient_email.strip() or None
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/send", response_class=HTMLResponse)
async def send_application_route(app_id: int, request: Request,
                                 session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Not found", status_code=404)
    if app.apply_status == "pending_review":
        app.apply_status = "approved"
        session.add(app)
        session.commit()
    result = await send_application(app_id)
    if result["ok"]:
        return HTMLResponse(
            '<span class="text-green-600 text-sm font-medium">Sent!</span>',
        )
    return HTMLResponse(
        f'<span class="text-red-500 text-sm">Failed: {result["error"]}</span>',
    )


@router.get("/review/{app_id}/download")
def download_resume(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app or not app.resume_path:
        return HTMLResponse("Resume not found", status_code=404)
    job = session.get(Job, app.job_id)
    filename = f"resume_{job.company if job else app_id}.docx".replace(" ", "_")
    return FileResponse(app.resume_path, filename=filename,
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


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
