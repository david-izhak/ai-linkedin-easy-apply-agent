from playwright.async_api import Page

from core.selectors import selectors


async def click_next_button(page: Page) -> None:
    """
    Clicks the 'Next' or 'Review' button in the application form.
    """
    await page.click(selectors["next_button"])
    # Wait for the next/submit button to be enabled before proceeding
    await page.wait_for_selector(
        selectors["enabled_submit_or_next_button"], timeout=1000
    )
