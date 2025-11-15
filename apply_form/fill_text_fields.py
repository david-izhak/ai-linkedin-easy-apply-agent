from playwright.async_api import Page
import logging
import re

from core.selectors import selectors
from .change_text_input import change_text_input


logger = logging.getLogger(__name__)


async def fill_text_fields(page: Page, text_fields: dict):
    """
    Fills text input fields based on a label regex match.
    """
    inputs = await page.query_selector_all(selectors["text_input"])

    for input_element in inputs:
        label_text = ""
        try:
            # Get the ID of the input to find its associated label
            input_id = await input_element.get_attribute("id")
            if input_id:
                label_selector = selectors["label_for"].format(id=input_id)
                label_element = await page.query_selector(label_selector)
                if label_element:
                    label_text = await label_element.inner_text()
        except Exception as e:
            # If label lookup fails, log it and continue to the next input
            logger.warning(
                f"Could not find label for an input field. Exception: {e}",
                exc_info=True,
            )
            continue

        # Check if any of the provided regex keys match the label
        for label_regex, value in text_fields.items():
            if label_text and re.search(label_regex, label_text, re.IGNORECASE):
                logger.debug(
                    f"Found text field matching regex '{label_regex}'. "
                    + "Filling with value."
                )
                await change_text_input(input_element, "", str(value))
                break  # Move to the next input after a match is found and filled
