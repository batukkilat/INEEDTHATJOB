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
    good_matches = session.exec(
        select(func.count(Job.id)).where(Job.compatibility_score >= 0.55)
    ).one()
    pending_review = session.exec(
        select(func.count(Application.id)).where(Application.apply_status == "pending_review")
    ).one()
    applied = session.exec(
        select(func.count(Application.id)).where(Application.apply_status.in_(["submitted", "applied_manually"]))
    ).one()
    return templates.TemplateResponse(request, "partials/stats.html", {
        "total_jobs": total_jobs,
        "good_matches": good_matches,
        "pending_review": pending_review,
        "applied": applied,
    })


import random as _random

_DONE_QUIPS = [
    "your opportunities await, bestie 🎯",
    "go check your queue, champ",
    "jobs found. snacks not included.",
    "results are in. your move.",
    "done! the ball is in your court now.",
    "mission accomplished. mostly.",
    "the hunt is over. for now.",
    "fresh jobs, just for you.",
]

_PROGRESS_SCRIPT = """
<script>
(function() {
  var bar = document.getElementById('pipeline-progress');
  if (!bar) return;
  bar.style.width = '{pct}%';
})();
</script>
"""

_DONE_SCRIPT = """
<script>
(function() {
  // Stop the fun messages, reset button
  if (window._msgTimer) clearInterval(window._msgTimer);
  var btn = document.getElementById('pipeline-btn');
  if (btn) {
    btn.disabled = false;
    btn.querySelector('.btn-loader').style.display = 'none';
    btn.querySelector('.btn-label').style.display = 'flex';
    document.getElementById('btn-text').textContent = 'Search Again';
  }
  var bar = document.getElementById('pipeline-progress');
  if (bar) { bar.classList.remove('progress-shimmer'); bar.style.width = '0%'; }
  // Refresh stats cards in place — no manual page reload needed
  if (window.htmx && document.getElementById('stats')) {
    htmx.ajax('GET', '/api/stats', {target: '#stats', swap: 'innerHTML'});
  }
})();
</script>
"""


def _progress(pct: int, label: str, poll: bool = True) -> str:
    poll_attr = 'hx-get="/api/pipeline/status" hx-trigger="every 5s" hx-swap="outerHTML"' if poll else ''
    # Hidden span carries the stage label for JS to detect; no visible text
    return (
        f'<span id="pipeline-status" style="display:none" data-stage="{label}" {poll_attr}></span>'
        + _PROGRESS_SCRIPT.replace("{pct}", str(pct))
    )


def _done() -> str:
    quip = _random.choice(_DONE_QUIPS)
    return (
        f'<div id="pipeline-status" class="flex items-center gap-2">'
        f'<a href="/" class="btn btn-sm border border-gray-200 text-gray-600 hover:bg-gray-50 font-medium">'
        f'↻ Refresh page</a>'
        f'<span class="text-xs text-gray-400 italic">{quip}</span>'
        f'</div>'
        + _PROGRESS_SCRIPT.replace("{pct}", "0")
        + _DONE_SCRIPT
    )


@router.post("/pipeline/run", response_class=HTMLResponse)
def pipeline_run(
    request: Request,
    background_tasks: BackgroundTasks,
    platforms: list[str] = Form(default=["linkedin"]),
):
    if pipe.is_running():
        return HTMLResponse(_progress(60, "scraping"))
    known = {"linkedin", "glints", "jobstreet"}
    active = [p for p in platforms if p in known]
    if not active:
        active = ["linkedin"]
    background_tasks.add_task(_run_pipeline_bg, active)
    return HTMLResponse(_progress(15, "scraping"))


@router.get("/pipeline/status", response_class=HTMLResponse)
def pipeline_status(request: Request):
    if pipe.is_running():
        stage = pipe.current_stage()
        pct_map = {"scraping": 20, "fetching": 40, "scoring": 65, "queuing": 88}
        pct = pct_map.get(stage, 55)
        return HTMLResponse(_progress(pct, stage or "running"))
    return HTMLResponse(_done())


async def _run_pipeline_bg(platforms: list[str]):
    await pipe.run_pipeline(platforms=platforms)


@router.post("/pipeline/stop", response_class=HTMLResponse)
def pipeline_stop():
    pipe.request_stop()
    return HTMLResponse(_progress(95, "Stopping after current step…"))


@router.post("/pipeline/rescore", response_class=HTMLResponse)
def pipeline_rescore(session: Session = Depends(get_session)):
    """Reset all jobs still in 'scored' status back to 'new' so the pipeline re-scores them."""
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
