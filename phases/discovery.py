import logging
import datetime
from playwright.async_api import Page

from config import (
    DEFAULT_JOB_POSTED_FILTER_SECONDS,
    KEYWORDS,
    WORKPLACE,
    GEO_ID,
    DISTANCE,
    SORT_BY,
)
from core.database import get_last_run_timestamp, save_discovered_jobs
from actions.fetch_jobs import fetch_job_links_user

logger = logging.getLogger(__name__)


async def run_discovery_phase(page: Page):
    """Runs the discovery phase: calculating time filter and fetching job links."""
    logger.info("--- Starting Discovery Phase ---")
    last_run_timestamp = get_last_run_timestamp()
    now = datetime.datetime.now()
    if last_run_timestamp:
        seconds_since_last_run = (
            int((now - last_run_timestamp).total_seconds()) + 300
        )  # 5 min buffer
        f_tpr = f"r{seconds_since_last_run}"
    else:
        logger.info("First run detected. Using default time filter.")
        f_tpr = f"r{DEFAULT_JOB_POSTED_FILTER_SECONDS}"
    logger.info(f"Using time filter for job search: {f_tpr}")

    discovered_jobs_data = await fetch_job_links_user(
        page=page,
        keywords=KEYWORDS,
        workplace=WORKPLACE,
        geo_id=GEO_ID,
        distance=DISTANCE,
        f_tpr=f_tpr,
        sort_by=SORT_BY,
    )
    save_discovered_jobs(discovered_jobs_data)
    logger.info("--- Finished Discovery Phase ---")
