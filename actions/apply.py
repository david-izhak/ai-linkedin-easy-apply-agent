from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
import logging
import re
import asyncio

from core.selectors import selectors
from core.form_filler import (
    FormFillCoordinator,
    JobApplicationContext,
    FillResult,
)
from core.form_filler.models import FormFillError
from core.logger import get_structured_logger
from config import config
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)
import types
from core.resilience import get_resilience_executor, get_selector_executor  # for test patch compatibility

logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)

# Backward-compatibility shim for tests expecting actions.apply.resilience.get_selector_executor
resilience = types.SimpleNamespace(
    get_selector_executor=get_selector_executor,
    get_resilience_executor=get_resilience_executor
)


async def click_easy_apply_button(page: Page) -> None:
    """
    Clicks the easy apply button using resilient SelectorExecutor with Locator API.
    
    Uses multiple selector fallbacks and selects the second element if multiple
    elements are found (as required for LinkedIn pages). Also waits for modal
    window to appear after clicking.
    
    Delegates resilience (retries, circuit breaker) to core.resilience.SelectorExecutor
    while providing enhanced logic for element selection and modal detection.
    """
    logger.info("Clicking easy apply button...")
    structured_logger.info("clicking_easy_apply_button")
    
    # Get timeout from config
    timeout = config.performance.selector_timeout
    
    # Get executor for resilience patterns
    executor = resilience.get_resilience_executor(page)
    
    # Build locator chain using .or() for automatic fallback
    # Start with the primary CSS selector (most reliable based on testing)
    primary_selector = selectors.get("easy_apply_button", "div.jobs-apply-button--top-card button")
    locator = page.locator(primary_selector)
    
    # Chain CSS selector fallbacks using .or() (only if they exist in selectors dict)
    fallback_1 = selectors.get("easy_apply_button_fallback_1")
    if fallback_1:
        locator = locator.or_(page.locator(fallback_1))
    
    fallback_2 = selectors.get("easy_apply_button_fallback_2")
    if fallback_2:
        locator = locator.or_(page.locator(fallback_2))
    
    fallback_3 = selectors.get("easy_apply_button_fallback_3")
    if fallback_3:
        locator = locator.or_(page.locator(fallback_3))
    
    # Add get_by_role as additional fallbacks (for both link and button roles)
    role_locator = page.get_by_role("link", name=re.compile(r'^Easy Apply$', re.IGNORECASE))
    locator = locator.or_(role_locator)
    
    # Also try button role as fallback
    button_role_locator = page.get_by_role("button", name=re.compile(r'^Easy Apply$', re.IGNORECASE))
    locator = locator.or_(button_role_locator)
    
    # Define the operation that will be executed with resilience
    async def click_operation():
        """Internal function that performs the actual click with element selection logic."""
        logger.debug("Waiting for Easy Apply button to be visible...")
        # Wait for at least one element to be visible
        await locator.first.wait_for(state="visible", timeout=timeout)
        
        # Check how many elements match
        count = await locator.count()
        logger.info(f"Found {count} Easy Apply button(s) on the page")
        structured_logger.debug(
            "easy_apply_button_elements_found",
            count=count,
            selector_used="multiple_with_or"
        )
        
        if count == 0:
            raise PlaywrightTimeoutError("No Easy Apply button found with any selector")
        
        # Select the second element if multiple are found, otherwise use the last one
        if count >= 2:
            logger.info(f"Selecting second Easy Apply button (index 1) from {count} found")
            structured_logger.debug(
                "selecting_second_easy_apply_button",
                total_elements=count,
                selected_index=1
            )
            element_locator = locator.nth(1)
        else:
            logger.info(f"Selecting the only Easy Apply button found")
            structured_logger.debug(
                "selecting_last_easy_apply_button",
                total_elements=count
            )
            element_locator = locator.last
        
        # Wait for the selected element to be visible and clickable
        logger.debug("Waiting for selected button to be visible and clickable...")
        await element_locator.wait_for(state="visible", timeout=timeout)
        
        # Get button text for logging
        try:
            button_text = await element_locator.text_content()
            if button_text:
                logger.info(f"Button text: '{button_text.strip()}'")
        except Exception:
            pass
        
        # Click the element
        logger.info("Clicking Easy Apply button...")
        await element_locator.click()
        logger.info("Easy Apply button clicked successfully")
        structured_logger.info("easy_apply_button_clicked_successfully")
        
        # Wait a bit for the modal to start appearing (same as test script)
        await asyncio.sleep(2)
        
        # Wait for modal window to appear after clicking
        # This is crucial - the modal needs time to open before ModalFlowRunner tries to find it
        logger.info("Waiting for Easy Apply modal window to appear...")
        
        # Use the same approach as test script - check for .jobs-easy-apply-modal first
        # Then fallback to role="dialog" (same as ModalFlowRunner)
        modal_found = False
        try:
            # First, try the specific Easy Apply modal class (most reliable)
            try:
                await page.wait_for_selector(
                    '.jobs-easy-apply-modal',
                    state="visible",
                    timeout=5000
                )
                logger.info("Easy Apply modal window appeared (detected by: .jobs-easy-apply-modal)")
                modal_found = True
            except PlaywrightTimeoutError:
                # Fallback: try waiting for dialog using get_by_role (same as ModalFlowRunner)
                logger.debug("Modal class not found, trying get_by_role('dialog')...")
                try:
                    dialogs = page.get_by_role("dialog")
                    await dialogs.first.wait_for(state="visible", timeout=5000)
                    dialog_count = await dialogs.count()
                    logger.info(f"Easy Apply modal window appeared (found {dialog_count} dialog(s) using get_by_role)")
                    modal_found = True
                except PlaywrightTimeoutError:
                    # Last fallback: try generic role="dialog" selector
                    logger.debug("Dialog not found with get_by_role, trying generic selector...")
                    try:
                        await page.wait_for_selector(
                            '[role="dialog"]',
                            state="visible",
                            timeout=3000
                        )
                        logger.info("Easy Apply modal window appeared (detected by: [role='dialog'])")
                        modal_found = True
                    except PlaywrightTimeoutError:
                        pass
            
            if modal_found:
                logger.info("Easy Apply modal window is ready")
                # Small delay to ensure modal is fully initialized
                await asyncio.sleep(0.5)
            else:
                logger.warning(
                    "Modal window did not appear within timeout, but continuing. "
                    "ModalFlowRunner will attempt to find it."
                )
                # Don't raise - let ModalFlowRunner handle it, it might find it with its own logic
        except Exception as e:
            logger.warning(f"Error while waiting for modal: {e}, but continuing anyway")
            # Don't raise - let ModalFlowRunner handle it
    
    # Execute the operation with resilience (retry, circuit breaker, metrics)
    try:
        await executor.execute_operation(
            selector_name="easy_apply_button",
            operation=click_operation,
            context={"operation": "click_easy_apply_button"}
        )
    except Exception as e:
        logger.error(
            f"Failed to click Easy Apply button: {e}",
            exc_info=True
        )
        structured_logger.error(
            "easy_apply_button_click_failed",
            error=str(e),
            error_type=type(e).__name__,
            exc_info=True
        )
        raise


async def apply_to_job(
    page: Page,
    link: str,
    job_context: JobApplicationContext,
    coordinator: FormFillCoordinator,
) -> FillResult:
    """
    Applies to a single job by navigating to the link, clicking Easy Apply,
    filling the form, and optionally submitting.
    """
    # The details page is already loaded by the main loop,
    # so no need for page.goto(link)
    logger.info("Starting application process...")

    try:
        await click_easy_apply_button(page)
    except Exception as e:
        logger.error(
            f"Easy Apply button not found or not clickable for posting: {link}."
            + "Skipping application.",
            exc_info=True,
        )
        raise

    try:
        result = await coordinator.fill(page, job_context)
        logger.info(
            "Form filling completed in mode=%s submitted=%s completed=%s",
            result.mode,
            result.submitted,
            result.completed,
        )
        
        # Check if the form was actually processed
        # If modal was not found, result.completed might be True but submitted is False
        # and there were no validation errors, which indicates modal was not found
        if result.completed and not result.submitted and not result.validation_errors:
            logger.warning(
                "Form filling completed but no submission occurred. "
                "This might indicate that the modal window was not found or processed."
            )
        
        return result
    except FormFillError as exc:
        logger.error(
            "Form filling failed for job_id=%s: %s",
            job_context.job_id,
            exc,
            exc_info=True,
        )
        raise
