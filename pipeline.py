from utils.logging import get_logger

log = get_logger(__name__)


async def run_pipeline() -> None:
    """Phase 2+: scrape → score → generate → queue for review."""
    log.info("pipeline_start")
    # TODO Phase 2: scrape jobs
    # TODO Phase 2: score jobs
    # TODO Phase 3: generate materials
    log.info("pipeline_complete")
