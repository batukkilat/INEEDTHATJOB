from apscheduler.schedulers.asyncio import AsyncIOScheduler
from config import settings
from utils.logging import get_logger

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


def start_scheduler() -> None:
    if not settings.schedule_enabled:
        log.info("scheduler_disabled")
        return
    global _scheduler
    _scheduler = AsyncIOScheduler()
    # TODO Phase 5: add pipeline job with settings.schedule_cron
    _scheduler.start()
    log.info("scheduler_started", cron=settings.schedule_cron)


def stop_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
