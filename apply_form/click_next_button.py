from playwright.async_api import Page
import structlog

from core.selectors import selectors
from core.resilience import get_resilience_executor
from core.logger import get_structured_logger


async def click_next_button(page: Page, job_id: str = None, job_title: str = None) -> None:
    """
    Clicks the 'Next' or 'Review' button in the application form with resilience.
    
    This function uses retry and circuit breaker patterns for reliable operation.
    
    Args:
        page: Playwright page instance
        job_id: Optional job ID for context
        job_title: Optional job title for context
    """
    logger = get_structured_logger(__name__)
    executor = get_resilience_executor(page)
    
    # Create context for logging and metrics
    context = {}
    if job_id:
        context["job_id"] = job_id
    if job_title:
        context["job_title"] = job_title
        
    # Log the operation
    logger.debug("clicking_next_button", **context)
    
    # Click the next button with retry and circuit breaker protection
    await executor.click(
        selector_name="next_button",
        context=context
    )
    
    # Wait for the next/submit button to be enabled before proceeding
    await executor.wait_for_selector(
        selector_name="enabled_submit_or_next_button",
        css_selector=selectors["enabled_submit_or_next_button"],
        context=context,
        timeout=3000  # Increased timeout for more reliability
    )
    
    logger.debug("next_button_clicked_successfully", **context)
