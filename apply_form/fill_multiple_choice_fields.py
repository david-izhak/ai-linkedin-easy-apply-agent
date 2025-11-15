from playwright.async_api import Page, ElementHandle
import logging
import re

from core.selectors import selectors

logger = logging.getLogger(__name__)


async def _process_select_element(
    page: Page, select_element: ElementHandle, multiple_choice_fields: dict
):
    """Processes a single select element to find a match and fill it."""
    try:
        select_id = await select_element.get_attribute("id")
        if not select_id:
            return

        label_selector = selectors["label_for"].format(id=select_id)
        label_element = await page.query_selector(label_selector)
        if not label_element:
            return

        label_text = await label_element.inner_text()

        for label_regex, desired_option_text in multiple_choice_fields.items():
            if re.search(label_regex, label_text, re.IGNORECASE):
                logger.debug(
                    f"Found select field '{label_text}' matching regex '{label_regex}'."
                )
                options = await select_element.query_selector_all(selectors["select_option"])
                for option_element in options:
                    option_text = await option_element.inner_text()
                    # Use strip() and lower() for a more robust comparison
                    if option_text.strip().lower() == desired_option_text.lower():
                        option_value = await option_element.get_attribute("value")
                        await select_element.select_option(value=option_value)
                        logger.debug(
                            f"Selected option '{option_text}' "
                            + f"for select field '{label_text}'."
                        )
                        return  # Exit after successfully filling the field

    except Exception as e:
        logger.warning(
            f"Could not process a multiple choice select field: {e}", exc_info=True
        )


async def fill_multiple_choice_fields(page: Page, multiple_choice_fields: dict) -> None:
    """
    Orchestrates filling multiple-choice select fields by processing them one by one.
    """
    logger.debug("Starting to fill multiple choice fields...")
    selects = await page.query_selector_all(selectors["select"])
    for select_element in selects:
        await _process_select_element(page, select_element, multiple_choice_fields)
    logger.debug("Finished filling multiple choice fields.")
