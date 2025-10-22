import logging
from playwright.async_api import BrowserContext

from config import AppConfig
from actions.fetch_jobs import fetch_job_links_user

logger = logging.getLogger(__name__)

# Constants for validation
MIN_RECOMMENDED_PERIOD = 86400  # 1 day in seconds
MAX_RECOMMENDED_PERIOD = 7776000  # 90 days in seconds


async def run_discovery_phase(app_config: AppConfig, browser_context: BrowserContext) -> None:
    """
    Runs the discovery phase: fetching job links using configured search period.
    
    This function searches for job postings on LinkedIn using a fixed time period
    specified in the configuration (JOB_SEARCH_PERIOD_SECONDS). The period determines
    how far back to search for job postings (e.g., jobs posted in the last 20 days).
    
    Args:
        page (Page): Playwright page object for browser automation.
    
    Raises:
        ValueError: If JOB_SEARCH_PERIOD_SECONDS is not a positive integer.
        TypeError: If JOB_SEARCH_PERIOD_SECONDS is not an integer.
    
    Configuration:
        Requires JOB_SEARCH_PERIOD_SECONDS in config.py.
    
    Example:
        # In config.py:
        # config.job_search.job_search_period_seconds = 1728000  # 20 days
        
        # Usage:
        # async with async_playwright() as p:
        #     browser = await p.chromium.launch()
        #     page = await browser.new_page()
        #     await run_discovery_phase(page)
    
    Note:
        - Discovered jobs are automatically saved to the database
        - The function logs the period being used for transparency
        - Warnings are issued for unusually large or small periods
    """
    logger.info("--- Starting Discovery Phase ---")
    
    job_search_period = app_config.job_search.job_search_period_seconds
    logger.info(f"Using JOB_SEARCH_PERIOD_SECONDS: {job_search_period} seconds")

    # Validate period type
    if not isinstance(job_search_period, int):
        raise TypeError(
            f"JOB_SEARCH_PERIOD_SECONDS must be an integer, got {type(job_search_period).__name__}. "
            f"Current value: {job_search_period}"
        )
    
    # Validate period value
    if job_search_period <= 0:
        raise ValueError(
            f"JOB_SEARCH_PERIOD_SECONDS must be a positive integer, got {job_search_period}. "
            "Please set a valid period in seconds (e.g., 1728000 for 20 days)."
        )
    
    # Warn if period is too large
    if job_search_period > MAX_RECOMMENDED_PERIOD:
        logger.warning(
            f"JOB_SEARCH_PERIOD_SECONDS is set to {job_search_period} seconds "
            f"({job_search_period // 86400} days), which is larger than recommended. "
            "LinkedIn typically shows job postings up to 30-60 days old. "
            "You may get fewer results than expected."
        )
    
    # Warn if period is too small
    if job_search_period < MIN_RECOMMENDED_PERIOD:
        logger.warning(
            f"JOB_SEARCH_PERIOD_SECONDS is set to {job_search_period} seconds "
            f"({job_search_period / 3600:.1f} hours), which is very short. "
            "You may get very few or no results. "
            "Recommended minimum: 86400 seconds (1 day)."
        )
    
    # Log the period being used
    logger.info(
        f"Using job search period: {job_search_period} seconds "
        f"({job_search_period // 86400} days)"
    )
    
    # Build time filter parameter for LinkedIn
    f_tpr = f"r{job_search_period}"
    logger.info(f"Using time filter for job search: {f_tpr}")

    page = browser_context.pages[0] if browser_context.pages else await browser_context.new_page()

    discovered_jobs_data = await fetch_job_links_user(
        page=page,
        app_config=app_config,
        db_conn=app_config.session.db_conn,
    )
    # Note: discovered jobs are already saved inside fetch_job_links_user
    logger.info(f"Discovery phase completed. Found {len(discovered_jobs_data)} new jobs.")
    logger.info("--- Finished Discovery Phase ---")
