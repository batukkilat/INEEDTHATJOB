import asyncio
from fastapi import APIRouter, BackgroundTasks, Request, Depends
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application
import pipeline as pipe

router = APIRouter()



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


@router.post("/pipeline/run", response_class=HTMLResponse)
def pipeline_run(request: Request, background_tasks: BackgroundTasks):
    if pipe.is_running():
        return HTMLResponse(
            '<div class="text-yellow-600 text-sm p-2">Pipeline is already running…</div>'
        )
    background_tasks.add_task(_run_pipeline_bg)
    return HTMLResponse(
        '<div id="pipeline-status" class="text-blue-600 text-sm p-2 font-medium">'
        'Pipeline started — scraping LinkedIn… '
        '<span hx-get="/api/pipeline/status" hx-trigger="every 5s" hx-swap="outerHTML"></span>'
        '</div>'
    )


@router.get("/pipeline/status", response_class=HTMLResponse)
def pipeline_status(request: Request):
    if pipe.is_running():
        return HTMLResponse(
            '<span id="pipeline-status-poll" '
            'hx-get="/api/pipeline/status" hx-trigger="every 5s" hx-swap="outerHTML">'
            '⏳ Running…</span>'
        )
    return HTMLResponse(
        '<span id="pipeline-status-poll" class="text-green-600">✓ Done — '
        '<a href="/" hx-boost="true" class="underline">refresh dashboard</a></span>'
    )


async def _run_pipeline_bg():
    await pipe.run_pipeline()
