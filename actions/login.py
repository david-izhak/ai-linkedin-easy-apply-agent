from playwright.async_api import Page
import logging
from core.selectors import selectors
from core.utils import ask_user

logger = logging.getLogger(__name__)


async def login(page: Page, email: str, password: str) -> None:
    """
    Logs into LinkedIn if no active session is found.
    """
    logger.info("Checking for active LinkedIn session...")
    await page.goto("https://www.linkedin.com/feed/", wait_until="load")

    try:
        await page.wait_for_selector(selectors["login_indicator"], timeout=5000)
        logger.info("Active session found. Skipping login.")
        return
    except Exception as e:
        logger.info(f"No active session found. Proceeding with login. Exception: {e}")

    logger.debug("Navigating to login page.")
    await page.goto("https://www.linkedin.com/login", wait_until="load")

    logger.debug("Entering login credentials.")
    await page.type(selectors["email_input"], email)
    await page.type(selectors["password_input"], password)

    logger.debug("Clicking login submit button.")
    await page.click(selectors["login_submit"])

    await page.wait_for_load_state("load")

    captcha_element = await page.query_selector(selectors["captcha"])
    if captcha_element:
        logger.warning("Captcha detected. Pausing for user intervention.")
        ask_user("Please solve the captcha and then press enter in the terminal.")
        await page.goto("https://www.linkedin.com/feed/", wait_until="load")

    logger.info("Successfully logged in to LinkedIn.")

    try:
        logger.debug("Checking for and clicking 'skip' button for post-login prompts.")
        await page.click(selectors["skip_button"], timeout=3000)
    except Exception as e:
        logger.debug(f"'Skip' button not found, continuing. Exception: {e}")
