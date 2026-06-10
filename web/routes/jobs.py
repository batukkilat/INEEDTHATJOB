import math

from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select, func, or_
from db.database import get_session
from db.models import Job

router = APIRouter()

PER_PAGE = 25


@router.get("/", response_class=HTMLResponse)
def jobs_list(
    request: Request,
    session: Session = Depends(get_session),
    status: str = Query(None),
    platform: str = Query(None),
    q: str = Query(None),
    page: int = Query(1, ge=1),
):
    filters = []
    if status:
        filters.append(Job.status == status)
    if platform:
        filters.append(Job.platform == platform)
    if q and q.strip():
        like = f"%{q.strip()}%"
        filters.append(or_(Job.title.like(like), Job.company.like(like)))

    count_query = select(func.count(Job.id))
    query = select(Job).order_by(Job.compatibility_score.desc(), Job.scraped_at.desc())
    for f in filters:
        count_query = count_query.where(f)
        query = query.where(f)

    total = session.exec(count_query).one()
    pages = max(1, math.ceil(total / PER_PAGE))
    page = min(page, pages)
    jobs = list(session.exec(query.offset((page - 1) * PER_PAGE).limit(PER_PAGE)).all())

    return templates.TemplateResponse(request, "jobs/list.html", {
        "current_page": "jobs",
        "jobs": jobs,
        "filter_status": status,
        "filter_platform": platform,
        "q": q or "",
        "page": page,
        "pages": pages,
        "total": total,
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
