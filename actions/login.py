from playwright.async_api import Page
import logging
from core.selectors import selectors
from core.utils import ask_user, wait_for_any_selector
from core.resilience import get_resilience_executor
from config import config  # Import the new config object

logger = logging.getLogger(__name__)


async def login(page: Page) -> None:
    """Log into LinkedIn if no active session exists.

    Args:
        page: Playwright page instance.

    Raises:
        playwright._impl._errors.TimeoutError: If critical selectors do not appear in time.
    """
    logger.info("Checking for active LinkedIn session...")
    executor = get_resilience_executor(page)
    await executor.navigate("https://www.linkedin.com/feed/", wait_until="load")

    # Wait for either login indicator (authenticated) or login form (not authenticated)
    # This is much faster than wait_for_load_state("networkidle")
    result = await wait_for_any_selector(
        page,
        [selectors["login_indicator"], selectors["email_input"]],
        timeout=config.performance.selector_timeout,
    )

    current_url = page.url
    # If we are on the authenticated feed, consider login successful immediately
    if "linkedin.com/feed" in current_url:
        nav = await executor.query_selector_with_retry(selectors["login_indicator"])  # best-effort check
        if nav is not None:
            logger.info("Active session detected via /feed URL. Skipping login.")
            return
        # Even if nav not found, being on /feed strongly indicates an authenticated session
        logger.info("Active session inferred from /feed URL. Skipping login.")
        return

    logger.info("Did not detect active session; proceeding to explicit login flow.")

    logger.debug("Navigating to login page.")
    await executor.navigate("https://www.linkedin.com/login", wait_until="load")

    logger.debug("Entering login credentials.")
    # Ensure inputs are present and visible before interacting
    await executor.wait_for_selector("email_input", selectors["email_input"], timeout=config.performance.selector_timeout)
    await executor.wait_for_selector("password_input", selectors["password_input"], timeout=config.performance.selector_timeout)
    await executor.fill("email_input", config.login.email, css_selector=selectors["email_input"])
    await executor.fill("password_input", config.login.password, css_selector=selectors["password_input"])

    logger.debug("Clicking login submit button.")
    await executor.click("login_submit", css_selector=selectors["login_submit"])

    # Wait for either successful login (nav indicator/feed) or captcha
    # This replaces wait_for_load_state("load") with specific element waiting
    login_success = await wait_for_any_selector(
        page,
        [selectors["login_indicator"], selectors["captcha"]],
        timeout=20000,
    )

    if not login_success:
        logger.debug("Neither login indicator nor captcha appeared after login submit; continuing.")

    captcha_element = await executor.query_selector_with_retry(selectors["captcha"])
    if captcha_element:
        logger.warning("Captcha detected. Pausing for user intervention.")
        ask_user("Please solve the captcha and then press enter in the terminal.")
        await executor.navigate("https://www.linkedin.com/feed/", wait_until="load")

    logger.info("Successfully logged in to LinkedIn.")

    try:
        logger.debug("Checking for and clicking 'skip' button for post-login prompts.")
        await executor.click("skip_button", css_selector=selectors["skip_button"], timeout=config.performance.selector_timeout)
    except Exception as e:
        logger.debug(f"'Skip' button not found, continuing. Exception: {e}")
