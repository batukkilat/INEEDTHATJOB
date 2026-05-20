from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select
from db.database import get_session
from db.models import Job

router = APIRouter()



@router.get("/", response_class=HTMLResponse)
def jobs_list(
    request: Request,
    session: Session = Depends(get_session),
    status: str = Query(None),
    platform: str = Query(None),
):
    query = select(Job).order_by(Job.compatibility_score.desc(), Job.scraped_at.desc())
    if status:
        query = query.where(Job.status == status)
    if platform:
        query = query.where(Job.platform == platform)
    jobs = list(session.exec(query).all())
    return templates.TemplateResponse(request, "jobs/list.html", {
        "current_page": "jobs",
        "jobs": jobs,
        "filter_status": status,
        "filter_platform": platform,
    })


@router.get("/{job_id}", response_class=HTMLResponse)
def job_detail(job_id: int, request: Request, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job:
        return HTMLResponse("Job not found", status_code=404)
    application = None
    if job.applications:
        application = job.applications[0]
    return templates.TemplateResponse(request, "jobs/detail.html", {
        "current_page": "jobs",
        "job": job,
        "application": application,
    })
