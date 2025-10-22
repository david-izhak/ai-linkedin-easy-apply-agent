from playwright.async_api import Page


async def wait_for_no_error(page: Page) -> None:
    """
    Waits for a short time to ensure no error messages appear.
    """
    # Wait for a function to evaluate to true,
    # checking for the absence of error elements.
    # This translates the original JS condition:
    # !document.querySelector("div[id*='error'] div[class*='error']")
    # We wait for an element matching the error selector NOT to exist.
    # The original timeout was 1000ms.
    await page.wait_for_function(
        '() => !document.querySelector(\'div[id*="error"] div[class*="error"]\')',
        timeout=1000,
    )
