import logging
import re
from playwright.async_api import BrowserContext, Error as PlaywrightError
from langdetect import detect

from config import (
    JOB_TITLE,
    JOB_DESCRIPTION,
    MAX_APPLICATIONS_PER_DAY,
    WAIT_BETWEEN_APPLICATIONS,
    JOB_DESCRIPTION_LANGUAGES,
)
from core.utils import wait
from actions.apply import apply_to_job
from core.database import get_enriched_jobs, update_job_status

logger = logging.getLogger(__name__)


def _is_job_suitable(job_data: tuple, patterns: dict) -> bool:
    """Checks if a job matches the defined filter criteria."""
    _, _, title, _, description = job_data
    job_title_pattern = patterns["title"]
    job_description_pattern = patterns["description"]

    try:
        job_desc_language = detect(description) if description else "unknown"
    except Exception as e:
        logger.warning("Could not detect language for job title '%s': %s", title, e)
        job_desc_language = "unknown"

    matches_title = job_title_pattern.search(title) is not None
    matches_description = job_description_pattern.search(description) is not None
    matches_language = (
        "any" in JOB_DESCRIPTION_LANGUAGES
        or job_desc_language in JOB_DESCRIPTION_LANGUAGES
    )

    logger.debug(
        f"Filter results for '{title}': title={matches_title}, desc={matches_description}, lang={matches_language}"
    )
    return matches_title and matches_description and matches_language


async def _process_single_job(
    context: BrowserContext,
    job_data: tuple,
    patterns: dict,
    should_submit: bool,
    config_globals: dict,
) -> bool:
    """
    Processes a single enriched job: final filtering and application.
    Returns True if an application was successfully submitted, False otherwise.
    """
    job_id, link, title, _, _ = job_data

    if not _is_job_suitable(job_data, patterns):
        logger.info("Skipping job: Does not match filter criteria.")
        update_job_status(job_id, "skipped_filter")
        return False

    apply_page = None
    was_applied = False
    try:
        apply_page = await context.new_page()
        await apply_to_job(
            page=apply_page,
            link=link,
            config=config_globals,
            should_submit=should_submit,
        )
        logger.info(f"Successfully processed application for {title}.")
        update_job_status(job_id, "applied")
        was_applied = True
    except PlaywrightError as e:
        logger.error(
            f"A Playwright error occurred while applying to job ID {job_id}: {e}"
        )
        update_job_status(job_id, "error")
    except Exception as e:
        logger.error(
            f"An unexpected error occurred while applying to job ID {job_id}",
            exc_info=True,
        )
        update_job_status(job_id, "error")
    finally:
        if apply_page and not (await apply_page.is_closed()):
            await apply_page.close()

    return was_applied


async def run_processing_phase(
    context: BrowserContext,
    applications_today_count: int,
    should_submit: bool,
    config_globals: dict,
):
    """Runs the processing phase: filtering and applying to enriched jobs."""
    logger.info("--- Starting Processing Phase ---")
    patterns = {
        "title": re.compile(JOB_TITLE, re.IGNORECASE),
        "description": re.compile(JOB_DESCRIPTION, re.IGNORECASE),
    }

    jobs_to_process = get_enriched_jobs()
    if not jobs_to_process:
        logger.info("No enriched jobs to process.")
        return

    for i, job_data in enumerate(jobs_to_process):
        job_id, _, title, _, _ = job_data
        logger.info(
            f"Processing job {i + 1}/{len(jobs_to_process)}: {title} (ID: {job_id})"
        )

        if applications_today_count >= MAX_APPLICATIONS_PER_DAY:
            logger.warning("Daily application limit reached. Stopping processing.")
            break

        was_applied = await _process_single_job(
            context, job_data, patterns, should_submit, config_globals
        )
        if was_applied:
            applications_today_count += 1
            logger.info(
                f"Application count for today is now: {applications_today_count}/{MAX_APPLICATIONS_PER_DAY}"
            )

        wait(WAIT_BETWEEN_APPLICATIONS)

    logger.info("--- Finished Processing Phase ---")
