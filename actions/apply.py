from playwright.async_api import Page
import logging
from typing import Optional

from core.selectors import selectors
from core import resilience
from core.form_filler import (
    FormFillCoordinator,
    JobApplicationContext,
    FillResult,
)
from core.form_filler.models import FormFillError

logger = logging.getLogger(__name__)


async def click_easy_apply_button(page: Page) -> None:
    """Clicks the easy apply button using a resilient selector."""
    logger.info("Clicking easy apply button...")
    executor = resilience.get_selector_executor(page)
    await executor.click(selectors.get("easy_apply_button", "div.jobs-apply-button--top-card button"))
    logger.debug("Easy apply button is clicked")


async def apply_to_job(
    page: Page,
    link: str,
    job_context: JobApplicationContext,
    coordinator: FormFillCoordinator,
) -> FillResult:
    """
    Applies to a single job by navigating to the link, clicking Easy Apply,
    filling the form, and optionally submitting.
    """
    # The details page is already loaded by the main loop,
    # so no need for page.goto(link)
    logger.info("Starting application process...")

    try:
        await click_easy_apply_button(page)
    except Exception as e:
        logger.error(
            f"Easy Apply button not found or not clickable for posting: {link}."
            + "Skipping application.",
            exc_info=True,
        )
        raise

    try:
        result = await coordinator.fill(page, job_context)
        logger.info(
            "Form filling completed in mode=%s submitted=%s",
            result.mode,
            result.submitted,
        )
        return result
    except FormFillError as exc:
        logger.error(
            "Form filling failed for job_id=%s: %s",
            job_context.job_id,
            exc,
            exc_info=True,
        )
        raise
