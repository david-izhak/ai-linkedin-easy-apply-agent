from playwright.async_api import Page

from core.selectors import selectors


async def uncheck_follow_company(page: Page) -> None:
    """
    Unchecks the 'Follow company' checkbox if it exists and is checked.
    """
    checkbox_element = await page.query_selector(selectors["follow_company_checkbox"])
    if checkbox_element:
        # Check if the checkbox is currently checked using evaluate
        is_checked = await page.evaluate("el => el.checked", checkbox_element)
        if is_checked:
            # Click the checkbox to uncheck it
            await checkbox_element.click()
