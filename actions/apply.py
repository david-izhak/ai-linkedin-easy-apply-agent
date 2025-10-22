from playwright.async_api import Page
import logging
from core.selectors import selectors
from apply_form.fill_fields import fill_fields
from apply_form.wait_for_no_error import wait_for_no_error
from apply_form.click_next_button import click_next_button

logger = logging.getLogger(__name__)


async def click_easy_apply_button(page: Page) -> None:
    """
    Clicks the 'Easy Apply' button on a job listing page.
    """
    logger.debug("Waiting for and clicking the 'Easy Apply' button.")
    await page.wait_for_selector(selectors["easy_apply_button_enabled"], timeout=10000)
    await page.click(selectors["easy_apply_button_enabled"])


async def apply_to_job(page: Page, link: str, config, should_submit: bool) -> None:
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
        # We raise the exception to be caught by the main loop for status update
        raise e

    max_pages = 5
    logger.debug(
        f"Starting to loop through a maximum of {max_pages} application pages."
    )
    for i in range(max_pages):
        logger.debug(f"Processing application page {i+1}.")
        await fill_fields(page, config)
        await click_next_button(page)
        await wait_for_no_error(page)

        # Check if the submit button is present, which means we are on the last page
        submit_button = await page.query_selector(selectors["submit"])
        if submit_button:
            logger.info("Submit button found. Reached the final application page.")
            break

    submit_button = await page.query_selector(selectors["submit"])
    if not submit_button:
        raise RuntimeError(
            f"Submit button not found after {max_pages} pages. "
            + "The application form might be too long or have an unknown step."
        )

    if should_submit:
        logger.info("SUBMIT mode is ON. Submitting the application...")
        await submit_button.click()
    else:
        logger.info("DRY RUN mode is ON. Application form filled but not submitted.")
