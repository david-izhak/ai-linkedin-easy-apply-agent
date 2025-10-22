import time
import json
import hashlib
import asyncio
import logging
from typing import Optional
from playwright.async_api import Page, ElementHandle
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


def make_search_key(params: dict) -> str:
    """
    Builds a deterministic search key (SHA256) from search parameters by
    producing a sorted JSON string to ensure stable hashing regardless of key order.
    """
    normalized = json.dumps(params, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


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
