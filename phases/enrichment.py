import logging
import asyncio
import inspect
from typing import List, Sequence, Tuple
from playwright.async_api import BrowserContext, Error as PlaywrightError, Page

from config import config, AppConfig # Import the new config object
from actions.fetch_jobs import fetch_job_details
from core.database import get_jobs_to_enrich, save_enrichment_data, update_job_status

logger = logging.getLogger(__name__)


async def wait(time_ms: int) -> None:
    """Asynchronously wait for the specified number of milliseconds.

    Args:
        time_ms: Duration to sleep in milliseconds.
    """
    await asyncio.sleep(time_ms / 1000.0)


def _limit_jobs(jobs: Sequence[Tuple[int, str, str, str]], app_config: AppConfig) -> List[Tuple[int, str, str, str]]:
    """Apply an optional limit to the jobs to enrich.

    Args:
        jobs: Sequence of job tuples as returned by the database layer.
        app_config: The application configuration object.

    Returns:
        A list of jobs limited to the requested size if applicable.
    """
    limit = app_config.job_limits.max_jobs_to_enrich
    if limit and limit < len(jobs):
        logger.info(
            f"Limiting enrichment to {limit} jobs (out of {len(jobs)} discovered)"
        )
        return list(jobs[:limit])
    return list(jobs)


async def _safe_close_page(page: Page | None) -> None:
    """Close a Playwright page if it exists and is not already closed.

    This function supports both synchronous and asynchronous implementations of
    `Page.is_closed`.

    Args:
        page: The page instance to close, if any.
    """
    if not page:
        return
    try:
        is_closed_result = page.is_closed()
        is_closed = await is_closed_result if inspect.isawaitable(is_closed_result) else bool(is_closed_result)
    except Exception:
        is_closed = False
    if not is_closed:
        await page.close()


async def _enrich_single_job(context: BrowserContext, job_id: int, link: str, title: str, app_config: AppConfig) -> None:
    """Enrich a single job by opening its page and fetching details.

    Args:
        context: The Playwright browser context to create pages from.
        job_id: Database identifier of the job.
        link: URL to the job details page.
        title: Title of the job, used for logging.
        app_config: The application configuration object.
    """
    logger.info(f"Enriching job: {title} (ID: {job_id})")
    page: Page | None = None
    try:
        page = await context.new_page()
        details = await fetch_job_details(page, link)
        if not details:
            raise ValueError("No details were fetched for the job.")
        logger.info(f"Successfully scraped details for job ID {job_id}.")

        logger.debug(f"Attempting to save details for job ID {job_id} to the database.")
        save_enrichment_data(job_id, details, app_config.session.db_conn)
        logger.info(f"Successfully saved details for job ID {job_id}.")
    except PlaywrightError as e:
        logger.error(
            f"A Playwright error occurred while enriching job ID {job_id}: {e}"
        )
        update_job_status(job_id, "enrichment_error", app_config.session.db_conn)
    except Exception as e:  # noqa: BLE001
        logger.error(
            f"An unexpected error occurred while enriching job ID {job_id}. Exception: {e}",
            exc_info=True,
        )
        update_job_status(job_id, "enrichment_error", app_config.session.db_conn)
    finally:
        await _safe_close_page(page)

        # Wait for a bit before processing the next job to avoid rate-limiting
        await wait(app_config.general_settings.wait_between_enrichments_ms)


async def run_enrichment_phase(
    app_config: AppConfig, browser_context: BrowserContext
) -> None:
    """Run the enrichment phase by fetching details for discovered jobs.

    Args:
        app_config: The application configuration object.
        browser_context: The Playwright browser context used for opening job pages.
    """
    logger.info("--- Starting Enrichment Phase ---")

    if app_config.job_limits.max_jobs_to_enrich == 0:
        logger.info("max_jobs_to_enrich is set to 0. Skipping enrichment phase.")
        return

    jobs_to_enrich = get_jobs_to_enrich(app_config.session.db_conn)
    if not jobs_to_enrich:
        logger.info("No discovered jobs to enrich.")
        return

    limited_jobs = _limit_jobs(jobs_to_enrich, app_config)

    total = len(limited_jobs)
    for index, (job_id, link, title, company_name) in enumerate(limited_jobs, start=1):
        logger.info(f"Processing {index}/{total}: {title} (ID: {job_id})")
        await _enrich_single_job(browser_context, job_id, link, title, app_config)

    logger.info("--- Finished Enrichment Phase ---")
