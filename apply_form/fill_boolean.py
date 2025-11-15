from playwright.async_api import Page, ElementHandle
import logging
import re
from core.selectors import selectors

logger = logging.getLogger(__name__)


async def _process_single_radio_fieldset(fieldset: ElementHandle, booleans: dict):
    """Processes a single fieldset to find and click a matching radio button."""
    try:
        radio_inputs = await fieldset.query_selector_all(selectors["radio_input"])
        if len(radio_inputs) != 2:
            return  # Not a 2-option radio group

        legend_element = await fieldset.query_selector(selectors["legend"])
        if not legend_element:
            return  # No legend found to match against

        label_text = await legend_element.inner_text()
        for label_regex, value in booleans.items():
            if re.search(label_regex, label_text, re.IGNORECASE):
                radio_value_to_click = "Yes" if value else "No"
                radio_selector = (
                    f"{selectors['radio_input']}[value='{radio_value_to_click}']"
                )
                radio_button = await fieldset.query_selector(radio_selector)
                if radio_button:
                    await radio_button.click()
                    logger.debug(
                        f"Selected '{radio_value_to_click}' for "
                        + f"radio group '{label_text}'."
                    )
                break  # Exit inner loop once a match is found
    except Exception as e:
        logger.warning(f"Could not process a radio button fieldset: {e}", exc_info=True)


async def _fill_radio_buttons(page: Page, booleans: dict):
    """Finds all radio button fieldsets and processes them one by one."""
    fieldsets = await page.query_selector_all(selectors["fieldset"])
    for fieldset in fieldsets:
        await _process_single_radio_fieldset(fieldset, booleans)


async def _process_single_checkbox(page: Page, checkbox: ElementHandle, booleans: dict):
    """Processes a single checkbox element."""
    try:
        checkbox_id = await checkbox.get_attribute("id")
        if not checkbox_id:
            return

        label_selector = selectors["label_for"].format(id=checkbox_id)
        label_element = await page.query_selector(label_selector)
        if not label_element:
            return

        label_text = await label_element.inner_text()
        for label_regex, value in booleans.items():
            if re.search(label_regex, label_text, re.IGNORECASE):
                is_checked = await checkbox.is_checked()
                if is_checked != value:
                    await checkbox.click()
                    logger.debug(f"Set checkbox '{label_text}' to {value}.")
                break
    except Exception as e:
        logger.warning(f"Could not process a checkbox: {e}", exc_info=True)


async def _fill_checkboxes(page: Page, booleans: dict):
    """Finds all checkboxes and processes them one by one."""
    checkboxes = await page.query_selector_all(selectors["checkbox"])
    for checkbox in checkboxes:
        await _process_single_checkbox(page, checkbox, booleans)


async def _process_single_select(
    page: Page, select_element: ElementHandle, booleans: dict
):
    """Processes a single 2-option select dropdown."""
    try:
        options = await select_element.query_selector_all(selectors["select_option"])
        if options and "select" in (await options[0].inner_text()).lower():
            options.pop(0)  # Remove placeholder option

        if len(options) != 2:
            return  # Skip selects that are not 2-option

        select_id = await select_element.get_attribute("id")
        if not select_id:
            return

        label_selector = selectors["label_for"].format(id=select_id)
        label_element = await page.query_selector(label_selector)
        if not label_element:
            return

        label_text = await label_element.inner_text()
        for label_regex, value in booleans.items():
            if re.search(label_regex, label_text, re.IGNORECASE):
                option_to_select = (
                    options[1] if value else options[0]
                )  # Corrected logic
                option_value = await option_to_select.get_attribute("value")
                await select_element.select_option(value=option_value)
                logger.debug(f"Selected option for '{label_text}'.")
                break
    except Exception as e:
        logger.warning(f"Could not process a select dropdown: {e}", exc_info=True)


async def _fill_two_option_selects(page: Page, booleans: dict):
    """Finds all select dropdowns and processes them one by one."""
    selects = await page.query_selector_all(selectors["select"])
    for select_element in selects:
        await _process_single_select(page, select_element, booleans)


async def fill_boolean(page: Page, booleans: dict) -> None:
    """
    Orchestrates the filling of all boolean-type fields (radios, checkboxes, selects).
    """
    logger.debug("Starting to fill boolean fields...")
    await _fill_radio_buttons(page, booleans)
    await _fill_checkboxes(page, booleans)
    await _fill_two_option_selects(page, booleans)
    logger.debug("Finished filling boolean fields.")
