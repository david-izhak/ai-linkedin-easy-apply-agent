import logging
import re
from playwright.async_api import BrowserContext, TimeoutError
import asyncio
import inspect
from pathlib import Path

from typing import Optional, List, Sequence, Tuple
from config import config, AppConfig
from diagnostics import DiagnosticOptions, DiagnosticContext, capture_on_failure
from actions.apply import apply_to_job
from core.database import get_enriched_jobs, get_error_jobs, update_job_status
from llm.vacancy_filter import is_vacancy_suitable
from core.utils import construct_full_url
from core.form_filler import (
    FormFillCoordinator,
    ModalFlowResources,
    JobApplicationContext,
    FormFillError,
)

logger = logging.getLogger(__name__)


def _limit_jobs(jobs: Sequence[Tuple[int, str, str, str]], app_config: AppConfig) -> List[Tuple[int, str, str, str]]:
    """Apply an optional limit to the jobs to process.

    Args:
        jobs: Sequence of job tuples as returned by the database layer.
        app_config: The application configuration object.

    Returns:
        A list of jobs limited to the requested size if applicable.
    """
    limit = app_config.job_limits.max_jobs_to_process
    if limit and limit < len(jobs):
        logger.info(
            f"Limiting processing to {limit} jobs (out of {len(jobs)} discovered)"
        )
        return list(jobs[:limit])
    return list(jobs)


async def _is_job_suitable(
    job_id: int, title: str, description: str | None, app_config: AppConfig
) -> bool:
    """Determines if a job is suitable based on title, description, and language filters."""
    # LLM-based filtering (primary)
    try:
        suitable, reason = await is_vacancy_suitable(job_id, app_config)
        if suitable:
            logger.debug("LLM filter result for '%s': True", title)
            return True
        else:
            # If LLM says not suitable, we trust it and stop here.
            logger.info(
                "Vacancy '%s' deemed unsuitable by LLM filter. Reason: %s",
                title,
                reason,
            )
            return False
    except Exception as e:
        logger.warning(
            "LLM filtering failed for '%s', falling back to word-based filtering: %s",
            title,
            e,
        )
        # Fallback to original word-based filtering
        if description:
            # Regex matching on description
            if not re.search(
                app_config.job_search.job_description_regex,
                description,
                re.IGNORECASE,
            ):
                logger.debug("Skipping job '%s' due to description mismatch", title)
                return False
            return True  # Explicitly return True if fallback succeeds
        else:
            return False


async def _process_single_job(
    context: BrowserContext,
    job_data: tuple,
    app_config: AppConfig,
    should_submit: bool,
    coordinator: FormFillCoordinator,
) -> bool:
    """Processes a single job application."""
    logger.debug(f"Call to function '{__name__}' started.{inspect.stack()[0][3]}")
    job_id, link, title, _, description = job_data
    full_url = construct_full_url(link)
    logger.debug(f"Full URL: {full_url}")
    cover_letter_path: Optional[Path] = (
        Path(app_config.form_data.cover_letter_path)
        if app_config.form_data.cover_letter_path
        else None
    )

    is_suitable = await _is_job_suitable(job_id, title, description, app_config)
    if not is_suitable:
        update_job_status(job_id, "skipped_filter", app_config.session.db_conn)
        logger.info(f"Skipping job '{title}' as it does not match the filter criteria.")
        return False

    page = None
    try:
        page = await context.new_page()
        await page.goto(full_url, wait_until="load")

        # Skip postings that are no longer open for applications.
        closed_locator = page.locator("text=/No longer accepting applications/i")
        if await closed_locator.count() > 0:
            logger.info(
                "Vacancy '%s' is no longer accepting applications. Skipping.", title
            )
            update_job_status(
                job_id, "applications_closed", app_config.session.db_conn
            )
            return False

        job_context = JobApplicationContext(
            job_id=job_id,
            job_url=full_url,
            job_title=title,
            should_submit=should_submit,
            cover_letter_path=cover_letter_path,
            job_description=description,
        )

        await apply_to_job(
            page=page,
            link=full_url,
            job_context=job_context,
            coordinator=coordinator,
        )
        update_job_status(job_id, "applied", app_config.session.db_conn)
        logger.info(f"Successfully processed application for {title}.")
        return True
    except TimeoutError as e:
        logger.error(f"Timeout error processing job ID {job_id}. Skipping.")
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
                phase="processing",
                job_id=job_id,
                link=full_url,
                error=e,
                tracker_state={},
            ),
        )
        update_job_status(job_id, "error", app_config.session.db_conn)
        return False
    except FormFillError as exc:
        logger.error(
            "Form filling failed for job ID %s: %s", job_id, exc, exc_info=True
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
                phase="processing",
                job_id=job_id,
                link=full_url,
                error=exc,
                tracker_state={},
            ),
        )
        update_job_status(job_id, "error", app_config.session.db_conn)
        return False
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while processing job ID {job_id}: {e}"
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
                phase="processing",
                job_id=job_id,
                link=full_url,
                error=e,
                tracker_state={},
            ),
        )
        update_job_status(job_id, "error", app_config.session.db_conn)
        return False
    finally:
        if page and not page.is_closed():
            await page.close()


async def run_processing_phase(
    context: BrowserContext,
    applications_today_count: int,
    should_submit: bool,
    app_config: AppConfig,
) -> None:
    """Runs the processing phase of the bot."""
    logger.info("--- Starting Processing Phase ---")
    max_applications = app_config.general_settings.max_applications_per_day
    
    # Prepare form filling coordinator (modal flow only)
    modal_flow_resources = ModalFlowResources(
        modal_flow_config=app_config.modal_flow,
        llm_config=app_config.llm,
        logger=logger,
    )
    form_fill_coordinator = FormFillCoordinator(
        app_config=app_config,
        resources=modal_flow_resources,
        logger=logger,
    )
    
    # First, process enriched jobs
    enriched_jobs = get_enriched_jobs(app_config.session.db_conn)
    if enriched_jobs:
        logger.info(f"Found {len(enriched_jobs)} enriched jobs to process.")
        limited_enriched_jobs = _limit_jobs(enriched_jobs, app_config)
        for job_data in limited_enriched_jobs:
            job_id, _, title, _, _ = job_data
            logger.info(
                f"Processing enriched job {limited_enriched_jobs.index(job_data) + 1}/{len(limited_enriched_jobs)}: {title} (ID: {job_id})"
            )

            if applications_today_count >= max_applications:
                logger.warning(f"Daily application limit of {max_applications} reached.")
                break

            if await _process_single_job(
                context,
                job_data,
                app_config,
                should_submit,
                form_fill_coordinator,
            ):
                applications_today_count += 1
                if applications_today_count >= max_applications:
                    logger.info(
                        f"Daily application limit of {max_applications} reached after this application."
                    )
                    break
            
            await wait(app_config.general_settings.wait_between_submissions_ms)
    else:
        logger.info("No enriched jobs to process.")
    
    # Second, retry jobs with error status if we haven't reached the daily limit
    if applications_today_count < max_applications:
        error_jobs = get_error_jobs(app_config.session.db_conn)
        if error_jobs:
            logger.info(f"Found {len(error_jobs)} jobs with error status to retry.")
            limited_error_jobs = _limit_jobs(error_jobs, app_config)
            for job_data in limited_error_jobs:
                job_id, _, title, _, _ = job_data
                logger.info(
                    f"Retrying error job {limited_error_jobs.index(job_data) + 1}/{len(limited_error_jobs)}: {title} (ID: {job_id})"
                )

                if applications_today_count >= max_applications:
                    logger.warning(f"Daily application limit of {max_applications} reached.")
                    break

                if await _process_single_job(
                    context,
                    job_data,
                    app_config,
                    should_submit,
                    form_fill_coordinator,
                ):
                    applications_today_count += 1
                    if applications_today_count >= max_applications:
                        logger.info(
                            f"Daily application limit of {max_applications} reached after this application."
                        )
                        break
                
                await wait(app_config.general_settings.wait_between_submissions_ms)
        else:
            logger.info("No error jobs to retry.")
    else:
        logger.info("Daily application limit reached. Skipping error job retry.")

    logger.info("--- Finished Processing Phase ---")
    await context.close()


async def wait(time_ms: int) -> None:
    """Asynchronously wait for the specified number of milliseconds."""
    await asyncio.sleep(time_ms / 1000.0)
