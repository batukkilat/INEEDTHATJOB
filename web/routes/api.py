import asyncio
from fastapi import APIRouter, BackgroundTasks, Request, Depends, Form
from fastapi.responses import HTMLResponse
from web.templates_env import templates
from sqlmodel import Session, select, func
from db.database import get_session
from db.models import Job, Application, ActivityLog
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


_PROGRESS_SCRIPT = """
<script>
(function() {
  var bar = document.getElementById('pipeline-progress');
  if (!bar) return;
  var pct = {pct};
  bar.style.width = pct + '%';
})();
</script>
"""


def _progress(pct: int, label: str, poll: bool = True) -> str:
    poll_attr = 'hx-get="/api/pipeline/status" hx-trigger="every 5s" hx-swap="outerHTML"' if poll else ''
    return (
        f'<div id="pipeline-status" class="text-blue-600 text-sm font-medium" {poll_attr}>{label}</div>'
        + _PROGRESS_SCRIPT.replace("{pct}", str(pct))
    )


@router.post("/pipeline/run", response_class=HTMLResponse)
def pipeline_run(
    request: Request,
    background_tasks: BackgroundTasks,
    platforms: list[str] = Form(default=["linkedin"]),
):
    if pipe.is_running():
        return HTMLResponse(_progress(60, "Already running…"))
    known = {"linkedin", "glints", "jobstreet", "x", "threads"}
    active = [p for p in platforms if p in known]
    if not active:
        active = ["linkedin"]
    background_tasks.add_task(_run_pipeline_bg, active)
    return HTMLResponse(_progress(15, f"Scraping {', '.join(active)}…"))


@router.get("/pipeline/status", response_class=HTMLResponse)
def pipeline_status(request: Request):
    if pipe.is_running():
        stage = pipe.current_stage()
        pct_map = {"scraping": 25, "fetching": 50, "scoring": 70, "generating": 88}
        pct = pct_map.get(stage, 60)
        label = {"scraping": "Scraping jobs…", "fetching": "Fetching descriptions…",
                 "scoring": "Scoring…", "generating": "Generating resumes…"}.get(stage, "Running…")
        return HTMLResponse(_progress(pct, label))
    return HTMLResponse(
        _progress(100, 'Done — <a href="/" class="underline">refresh</a>', poll=False)
        .replace('text-blue-600', 'text-green-600')
        .replace('bg-blue-500', 'bg-green-500')
    )


async def _run_pipeline_bg(platforms: list[str]):
    await pipe.run_pipeline(platforms=platforms)


@router.post("/pipeline/stop", response_class=HTMLResponse)
def pipeline_stop():
    pipe.request_stop()
    return HTMLResponse(_progress(95, "Stopping after current step…"))


@router.post("/pipeline/rescore", response_class=HTMLResponse)
def pipeline_rescore(session: Session = Depends(get_session)):
    """Reset all zero-scored or failed jobs back to 'new' so the pipeline re-scores them."""
    jobs = list(session.exec(
        select(Job).where(Job.status == "scored")
    ).all())
    for job in jobs:
        job.status = "new"
        job.compatibility_score = None
        job.score_breakdown = None
        session.add(job)
    session.commit()
    reset_count = len(jobs)
    return HTMLResponse(
        f'<span class="text-green-600 text-sm font-medium">Reset {reset_count} jobs — run the pipeline to re-score.</span>'
    )


@router.get("/pipeline/log", response_class=HTMLResponse)
def pipeline_log(request: Request, session: Session = Depends(get_session)):
    # Last 40 activity entries
    entries = list(session.exec(
        select(ActivityLog).order_by(ActivityLog.timestamp.desc()).limit(40)
    ).all())
    entries.reverse()

    # Recent scored jobs
    recent_jobs = list(session.exec(
        select(Job)
        .where(Job.compatibility_score.is_not(None))
        .order_by(Job.scraped_at.desc())
        .limit(20)
    ).all())

    return templates.TemplateResponse(request, "partials/pipeline_log.html", {
        "entries": entries,
        "recent_jobs": recent_jobs,
        "is_running": pipe.is_running(),
        "stage": pipe.current_stage(),
    })
