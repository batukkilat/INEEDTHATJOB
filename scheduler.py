from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None
_enabled_override: bool | None = None   # None = use settings.schedule_enabled
_cron_override: str | None = None       # None = use settings.schedule_cron


def _is_enabled() -> bool:
    return _enabled_override if _enabled_override is not None else settings.schedule_enabled


def _get_cron() -> str:
    return _cron_override if _cron_override is not None else settings.schedule_cron


async def _run_pipeline_job() -> None:
    from pipeline import run_pipeline, is_running
    if is_running():
        log.info("scheduler_skip_already_running")
        return
    log.info("scheduler_pipeline_trigger")
    await run_pipeline()


def _add_pipeline_job() -> None:
    if not (_scheduler and _scheduler.running):
        return
    _scheduler.add_job(
        _run_pipeline_job,
        trigger=CronTrigger.from_crontab(_get_cron()),
        id="pipeline",
        replace_existing=True,
        misfire_grace_time=300,
    )


def start_scheduler() -> None:
    if not _is_enabled():
        log.info("scheduler_disabled")
        return
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.start()
    _add_pipeline_job()
    log.info("scheduler_started", cron=_get_cron())


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()


def set_enabled(enabled: bool) -> None:
    global _enabled_override
    _enabled_override = enabled
    if enabled:
        if not (_scheduler and _scheduler.running):
            start_scheduler()
    else:
        stop_scheduler()
    log.info("scheduler_toggled", enabled=enabled)


def set_cron(cron: str) -> None:
    global _cron_override
    _cron_override = cron
    if _scheduler and _scheduler.running:
        _add_pipeline_job()
    log.info("scheduler_cron_updated", cron=cron)


def get_status() -> dict:
    running = bool(_scheduler and _scheduler.running)
    next_run = None
    if running:
        job = _scheduler.get_job("pipeline")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    return {
        "enabled": _is_enabled(),
        "running": running,
        "cron": _get_cron(),
        "next_run": next_run,
    }
