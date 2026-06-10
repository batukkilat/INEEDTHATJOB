"""Regression: the pipeline cron job must be registered when the scheduler starts.

Previously _add_pipeline_job() ran before _scheduler.start(), and its
running-scheduler guard silently skipped registration — the scheduler ran
with zero jobs and scheduled pipelines never fired.
"""
import asyncio

import scheduler


def test_pipeline_job_registered_on_start():
    async def run():
        scheduler._enabled_override = True
        try:
            scheduler.start_scheduler()
            return scheduler._scheduler.get_job("pipeline")
        finally:
            scheduler.stop_scheduler()
            scheduler._enabled_override = None
            scheduler._scheduler = None

    job = asyncio.run(run())
    assert job is not None, "pipeline job missing after start_scheduler()"


def test_get_status_reports_next_run():
    async def run():
        scheduler._enabled_override = True
        try:
            scheduler.start_scheduler()
            return scheduler.get_status()
        finally:
            scheduler.stop_scheduler()
            scheduler._enabled_override = None
            scheduler._scheduler = None

    status = asyncio.run(run())
    assert status["running"] is True
    assert status["next_run"] is not None
