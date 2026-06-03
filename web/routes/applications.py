from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, FileResponse
from web.templates_env import templates
from sqlmodel import Session, select
from db.database import get_session
from db.models import Application, Job
from generation.cover_letter import generate_cover_letter
from generation.email_composer import compose_email
from generation.common import extract_contact_email, extract_contact_email_llm
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


@router.get("/review/{app_id}/reject-options", response_class=HTMLResponse)
def reject_options(app_id: int, request: Request):
    return templates.TemplateResponse(request, "partials/reject_options.html",
                                      {"app_id": app_id})


@router.get("/review/{app_id}/header-actions", response_class=HTMLResponse)
def header_actions(app_id: int, request: Request, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    job = session.get(Job, app.job_id) if app else None
    return templates.TemplateResponse(request, "partials/review_header_actions.html",
                                      {"app": app, "job": job})


@router.post("/review/{app_id}/reject", response_class=HTMLResponse)
def reject_application(app_id: int, reason: str = Form(""),
                       session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        app.apply_status = "rejected"
        app.skip_reason = reason.strip() or None
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/apply-manual", response_class=HTMLResponse)
def apply_manual(app_id: int, session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if app:
        from datetime import datetime, timezone
        app.apply_status = "applied_manually"
        app.applied_at = datetime.now(timezone.utc).isoformat()
        app.skip_reason = "applied via platform URL"
        session.add(app)
        session.commit()
    return HTMLResponse("")


@router.post("/review/{app_id}/generate-resume", response_class=HTMLResponse)
async def generate_resume_route(app_id: int, request: Request,
                                session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Application not found", status_code=404)
    job = session.get(Job, app.job_id)
    import json as _json
    from generation.resume import generate_resume
    docx_path, resume_content = await generate_resume(job, session)
    app.resume_path = docx_path
    app.resume_content = _json.dumps(resume_content)
    session.add(app)
    session.commit()
    return templates.TemplateResponse(request, "partials/resume_preview.html", {"app": app})


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


@router.post("/review/{app_id}/suggest-email", response_class=HTMLResponse)
def suggest_recipient_email(app_id: int, request: Request,
                            session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Not found", status_code=404)
    job = session.get(Job, app.job_id)

    # Regex only — LLM extraction runs in the pipeline (paced), not here
    email = extract_contact_email(job.description if job else "")

    if email:
        app.recipient_email = email
        session.add(app)
        session.commit()

    return templates.TemplateResponse(request, "partials/email_block.html",
                                      {"app": app, "email_searched": True})


@router.post("/review/{app_id}/detect-email", response_class=HTMLResponse)
async def detect_recipient_email(app_id: int, request: Request,
                                 session: Session = Depends(get_session)):
    app = session.get(Application, app_id)
    if not app:
        return HTMLResponse("Not found", status_code=404)
    job = session.get(Job, app.job_id)
    email = await extract_contact_email_llm(job) if job else None
    if email:
        app.recipient_email = email
        session.add(app)
        session.commit()
    return templates.TemplateResponse(request, "partials/email_block.html",
                                      {"app": app, "email_searched": True,
                                       "detect_failed": not email})


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
