import asyncio
import logging
import random
from typing import Optional, Union
from playwright.async_api import Page, ElementHandle, Locator
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

BASE_URL = "https://www.linkedin.com"


def construct_full_url(relative_path: str) -> str:
    """Constructs a full URL from a relative path."""
    return urljoin(BASE_URL, relative_path)


def ask_user(prompt: str) -> str:
    """
    Asks the user for input and returns the response.
    """
    print(prompt, end="")
    return input()


# def wait(time_ms: int):
#     """
#     Waits for a specified amount of time in milliseconds.
#     """
#     time.sleep(time_ms / 1000.0)


async def wait_for_any_selector(
    page: Page,
    selectors: list[str],
    timeout: int = 10000,
    state: str = "visible"
) -> Optional[tuple[str, ElementHandle]]:
    """
    Efficiently waits for ANY of the provided selectors to appear on the page.
    
    This is a performance-optimized alternative to wait_for_load_state that waits
    for specific elements rather than generic page state. Uses parallel checks
    for multiple selectors.
    
    Args:
        page: Playwright page instance.
        selectors: List of CSS selectors to wait for.
        timeout: Maximum time to wait in milliseconds.
        state: Element state to wait for ("visible", "attached", "hidden").
    
    Returns:
        Tuple of (matched_selector, element_handle) if found, None if timeout.
    
    Example:
        >>> result = await wait_for_any_selector(
        ...     page,
        ...     ["div.job-list", "ul.jobs", "div.no-results"],
        ...     timeout=5000
        ... )
        >>> if result:
        ...     selector, element = result
        ...     print(f"Found element with selector: {selector}")
    """
    async def wait_single(selector: str) -> Optional[tuple[str, ElementHandle]]:
        """Helper to wait for a single selector."""
        try:
            element = await page.wait_for_selector(
                selector,
                state=state,
                timeout=timeout
            )
            if element:
                return (selector, element)
        except Exception as e:
            logger.debug(f"Selector '{selector}' not found: {e}")
        return None
    
    # Create tasks explicitly for all selectors (Python 3.13+ requirement)
    tasks = [asyncio.create_task(wait_single(selector)) for selector in selectors]
    
    # Wait for the first one to complete successfully
    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
            timeout=timeout / 1000.0
        )
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Check if any task succeeded
        for task in done:
            result = await task
            if result:
                logger.debug(f"Found element with selector: {result[0]}")
                return result
        
        logger.debug(f"None of the selectors found: {selectors}")
        return None
        
    except asyncio.TimeoutError:
        logger.debug(f"Timeout waiting for any of: {selectors}")
        # Cancel all tasks on timeout
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        return None


# async def check_any_selector_present(
#     page: Page,
#     selectors: list[str]
# ) -> Optional[tuple[str, list[ElementHandle]]]:
#     """
#     Immediately checks if any of the provided selectors are present on the page.
#
#     Non-blocking check without waiting. Useful for quick verification of page state.
#
#     Args:
#         page: Playwright page instance.
#         selectors: List of CSS selectors to check.
#
#     Returns:
#         Tuple of (matched_selector, list_of_elements) if found, None otherwise.
#
#     Example:
#         >>> result = await check_any_selector_present(
#         ...     page,
#         ...     ["div.job-list", "ul.jobs"]
#         ... )
#         >>> if result:
#         ...     selector, elements = result
#         ...     print(f"Found {len(elements)} elements with selector: {selector}")
#     """
#     for selector in selectors:
#         try:
#             elements = await page.query_selector_all(selector)
#             if elements:
#                 logger.debug(f"Found {len(elements)} elements with selector: {selector}")
#                 return (selector, elements)
#         except Exception as e:
#             logger.debug(f"Error checking selector '{selector}': {e}")
#             continue
#
#     return None


async def simulate_human_typing(
    element: Union[Locator, ElementHandle],
    text: str,
    clear_first: bool = True,
    pre_delay_range: tuple[int, int] = (200, 800),
    char_delay_range: tuple[int, int] = (50, 150),
) -> None:
    """
    Simulates human-like typing into an input element.
    
    Types text character-by-character with random delays to mimic human behavior
    and avoid bot detection systems.
    
    Args:
        element: Playwright Locator or ElementHandle to type into.
        text: Text to type.
        clear_first: If True, clears the field before typing (using triple-click to select all).
        pre_delay_range: Tuple of (min_ms, max_ms) for random delay before typing starts.
        char_delay_range: Tuple of (min_ms, max_ms) for random delay between each character.
    
    Example:
        >>> await simulate_human_typing(page.locator("input#email"), "user@example.com")
        >>> await simulate_human_typing(combo_element, "Python", clear_first=True)
    """
    # Random pre-typing delay to simulate human hesitation
    pre_delay_ms = random.randint(pre_delay_range[0], pre_delay_range[1])
    await asyncio.sleep(pre_delay_ms / 1000.0)

    # Clear the field if requested (using fill is more reliable than triple-click)
    if clear_first:
        await element.fill("")
        # Small delay after clearing
        await asyncio.sleep(random.randint(50, 100) / 1000.0)

    # Calculate random delay for this typing session
    char_delay_ms = random.randint(char_delay_range[0], char_delay_range[1])
    
    # Type text character by character with random delays
    await element.press_sequentially(str(text), delay=char_delay_ms)


async def random_sleep(base_delay_s: float) -> None:
    """
    Waits for a random duration between base_delay_s and base_delay_s * 2.

    Args:
        base_delay_s: The minimum delay in seconds.
    """
    delay = base_delay_s + random.uniform(0, base_delay_s)
    await asyncio.sleep(delay)


async def random_wait_ms(base_time_ms: int) -> None:
    """
    Waits for a random duration based on a millisecond value.

    Args:
        base_time_ms: The minimum delay in milliseconds.
    """
    await random_sleep(base_time_ms / 1000.0)