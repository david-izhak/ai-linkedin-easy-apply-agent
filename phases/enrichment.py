import logging
import asyncio
import inspect
import os
from datetime import datetime
from typing import List, Sequence, Tuple
from playwright.async_api import BrowserContext, Error as PlaywrightError, Page

from config import config, AppConfig # Import the new config object
from actions.fetch_jobs import fetch_job_details
from core.database import get_jobs_to_enrich, save_enrichment_data, update_job_status
from core.resilience import get_resilience_executor
from diagnostics import DiagnosticOptions, DiagnosticContext, capture_on_failure

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


async def _save_error_snapshot(page: Page | None, job_id: int, link: str) -> None:
    """Save an HTML snapshot of the page when enrichment fails.
    
    Args:
        page: The Playwright page instance, if available.
        job_id: Database identifier of the job.
        link: URL of the job page.
    """
    if not page:
        logger.debug(f"Could not save snapshot for job ID {job_id}: page is not available.")
        return
    
    try:
        is_closed_result = page.is_closed()
        is_closed = await is_closed_result if inspect.isawaitable(is_closed_result) else bool(is_closed_result)
        if is_closed:
            logger.debug(f"Could not save snapshot for job ID {job_id}: page is already closed.")
            return
    except Exception:
        logger.debug(f"Could not check page state for job ID {job_id}: page may be invalid.")
        return

    try:
        html_content = await page.content()
        
        snapshot_dir = "logs/html_snapshots"
        os.makedirs(snapshot_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"enrichment_error_job_{job_id}_{timestamp}.html"
        filepath = os.path.join(snapshot_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Saved HTML snapshot for failed job ID {job_id} (URL: {link}) to {filepath}")

    except Exception as e:
        logger.error(f"Failed to save HTML snapshot for job ID {job_id}. Error: {e}", exc_info=True)


async def _enrich_single_job(context: BrowserContext, job_id: int, link: str, title: str, app_config: AppConfig, noncritical_error_tracker: dict | None = None) -> bool:
    """Enrich a single job by opening its page and fetching details.

    Uses unified retry mechanism with exponential backoff and cleanup between attempts.

    Args:
        context: The Playwright browser context to create pages from.
        job_id: Database identifier of the job.
        link: URL to the job details page.
        title: Title of the job, used for logging.
        app_config: The application configuration object.
        noncritical_error_tracker: Optional tracker for noncritical errors.

    Returns:
        bool: True if enrichment was successful, False otherwise.
    """
    logger.info(f"Enriching job: {title} (ID: {job_id})")
    
    # Store page reference for cleanup
    page: Page | None = None
    
    async def _enrich_job_operation() -> bool:
        """Internal operation function for enrichment workflow."""
        nonlocal page
        
        # Close previous page if it exists (from retry)
        if page:
            await _safe_close_page(page)
            page = None
        
        # Create new page for this attempt
        page = await context.new_page()
        
        # Pass noncritical error tracker to allow systemic error detection downstream
        details = await fetch_job_details(page, link, noncritical_error_tracker)  # type: ignore[arg-type]
        
        if not details:
            raise ValueError("No details were fetched for the job.")
        
        logger.info(f"Successfully scraped details for job ID {job_id}.")

        logger.debug(f"Attempting to save details for job ID {job_id} to the database.")
        save_enrichment_data(job_id, details, app_config.session.db_conn)
        logger.info(f"Successfully saved details for job ID {job_id}.")
        
        # Success - close page
        await _safe_close_page(page)
        page = None
        return True
    
    async def cleanup_between_attempts() -> None:
        """Cleanup function called between retry attempts."""
        nonlocal page
        if page:
            await _safe_close_page(page)
            page = None
    
    # Create a temporary page for executor initialization
    # The executor needs a page instance, but the actual page for enrichment is created in the operation
    temp_page: Page | None = None
    try:
        temp_page = await context.new_page()
        executor = get_resilience_executor(temp_page)
        
        result = await executor.execute_workflow_with_retry(
            operation_name="enrich_job",
            operation=_enrich_job_operation,
            cleanup_between_attempts=cleanup_between_attempts,
            context={"job_id": job_id, "link": link, "title": title}
        )
        return result
    except PlaywrightError as e:
        logger.error(
            f"All attempts exhausted. A Playwright error occurred "
            f"while enriching job ID {job_id} at URL {link}: {e}"
        )
        # Collect diagnostics if enabled
        await capture_on_failure(
            context,
            page,
            DiagnosticOptions(
                enable_on_failure=app_config.diagnostics.enable_on_failure,
                capture_screenshot=app_config.diagnostics.capture_screenshot,
                capture_html=app_config.diagnostics.capture_html,
                capture_console_log=app_config.diagnostics.capture_console_log,
                capture_har=app_config.diagnostics.capture_har,
                capture_trace=app_config.diagnostics.capture_trace,
                output_dir=app_config.diagnostics.output_dir,
                max_artifacts_per_run=app_config.diagnostics.max_artifacts_per_run,
                pii_mask_patterns=app_config.diagnostics.pii_mask_patterns,
                phases_enabled=app_config.diagnostics.phases_enabled,
            ),
            DiagnosticContext(
                phase="enrichment",
                job_id=job_id,
                link=link,
                error=e,
                tracker_state=noncritical_error_tracker or {},
            ),
        )
        update_job_status(job_id, "enrichment_error", app_config.session.db_conn)
        return False
    except Exception as e:  # noqa: BLE001
        logger.error(
            f"All attempts exhausted. An unexpected error occurred "
            f"while enriching job ID {job_id} at URL {link}. Exception: {e}",
            exc_info=True,
        )
        await capture_on_failure(
            context,
            page,
            DiagnosticOptions(
                enable_on_failure=app_config.diagnostics.enable_on_failure,
                capture_screenshot=app_config.diagnostics.capture_screenshot,
                capture_html=app_config.diagnostics.capture_html,
                capture_console_log=app_config.diagnostics.capture_console_log,
                capture_har=app_config.diagnostics.capture_har,
                capture_trace=app_config.diagnostics.capture_trace,
                output_dir=app_config.diagnostics.output_dir,
                max_artifacts_per_run=app_config.diagnostics.max_artifacts_per_run,
                pii_mask_patterns=app_config.diagnostics.pii_mask_patterns,
                phases_enabled=app_config.diagnostics.phases_enabled,
            ),
            DiagnosticContext(
                phase="enrichment",
                job_id=job_id,
                link=link,
                error=e,
                tracker_state=noncritical_error_tracker or {},
            ),
        )
        update_job_status(job_id, "enrichment_error", app_config.session.db_conn)
        return False
    finally:
        # Ensure all pages are closed
        await _safe_close_page(page)
        await _safe_close_page(temp_page)
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
    # Track noncritical, potentially systemic errors occurring in details fetching
    noncritical_error_tracker: dict[str, int] = {
        "company_link_query": 0,
        "company_about_scrape": 0,
    }
    max_nc_errors = app_config.performance.max_noncritical_consecutive_errors
    consecutive_errors = 0
    max_consecutive_errors = 3  # Stop after 3 consecutive errors

    for index, (job_id, link, title, company_name) in enumerate(limited_jobs, start=1):
        logger.info(f"Processing {index}/{total}: {title} (ID: {job_id})")
        
        success = await _enrich_single_job(
            browser_context, job_id, link, title, app_config, noncritical_error_tracker
        )
        
        if success:
            consecutive_errors = 0
            logger.debug(f"Enrichment successful. Consecutive error count reset to 0.")
        else:
            consecutive_errors += 1
            logger.warning(
                f"Enrichment failed for job ID {job_id}. "
                f"Consecutive error count: {consecutive_errors}/{max_consecutive_errors}"
            )
        
        # Stop on systemic noncritical errors
        if any(v >= max_nc_errors for v in noncritical_error_tracker.values()):
            logger.error(
                "Stopping enrichment phase due to systemic noncritical errors: %s",
                noncritical_error_tracker,
            )
            break

        if consecutive_errors >= max_consecutive_errors:
            logger.error(
                f"Stopping enrichment phase due to {max_consecutive_errors} consecutive errors. "
                f"Processed {index}/{total} jobs before stopping."
            )
            break

    logger.info("--- Finished Enrichment Phase ---")
