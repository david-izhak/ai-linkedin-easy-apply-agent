"""
Resilience patterns for LinkedIn Easy Apply Bot.

This module provides mechanisms for building resilient operations using:
- Retry with exponential backoff (using tenacity)
- Circuit breaker pattern (using pybreaker)
- Combined selector operations with metrics
"""

import time
import functools
import logging
import asyncio
from typing import Dict, Any, Optional, Callable, TypeVar, Union, cast, Awaitable, Tuple

import structlog
import pybreaker
from tenacity import (
    retry, 
    stop_after_attempt, 
    wait_exponential,
    retry_if_exception_type,
    before_log, 
    after_log,
    RetryError,
    wait_random
)
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError, Locator, Error as PlaywrightError

from core.metrics import get_metrics_collector
from core.logger import get_structured_logger, bind_context
from config import config, AppConfig # Import the new config object

# Type variables for generic function signatures
T = TypeVar('T')
R = TypeVar('R')

# Configure standard logger for tenacity
logger = logging.getLogger(__name__)
structured_logger = get_structured_logger(__name__)


class CircuitBreakerListener(pybreaker.CircuitBreakerListener):
    """
    Circuit breaker listener that collects metrics and logs state changes.
    """
    
    def __init__(self, metrics_collector, logger: structlog.BoundLogger, selector_name: str):
        """
        Initialize the circuit breaker listener.
        
        Args:
            metrics_collector: Metrics collector instance
            logger: Structured logger instance
            selector_name: Name of the selector this circuit breaker protects
        """
        self.metrics_collector = metrics_collector
        self.logger = logger
        self.selector_name = selector_name
    
    def state_change(self, breaker, old_state, new_state):
        """
        Log state changes and record metrics when the circuit breaker state changes.
        
        Args:
            breaker: Circuit breaker instance
            old_state: Previous state of the circuit breaker
            new_state: New state of the circuit breaker
        """
        self.logger.warning(
            "circuit_breaker_state_change",
            selector=self.selector_name,
            old_state=str(old_state.name),
            new_state=str(new_state.name)
        )
        self.metrics_collector.record_circuit_breaker_state_change(
            breaker.name, str(old_state.name), str(new_state.name)
        )
    
    def failure(self, breaker, exc):
        """
        Log failures that contribute to the circuit breaker counter.
        
        Args:
            breaker: Circuit breaker instance
            exc: Exception that occurred
        """
        self.logger.error(
            "circuit_breaker_failure",
            selector=self.selector_name,
            error=str(exc),
            failure_count=breaker._failure_count,
            threshold=breaker.fail_max
        )
    
    def success(self, breaker):
        """
        Log successful operations that reset the circuit breaker counter.
        
        Args:
            breaker: Circuit breaker instance
        """
        self.logger.debug("circuit_breaker_success", selector=self.selector_name)


class SelectorCircuitBreaker:
    """
    Manages circuit breakers for selectors with metrics collection.
    """
    
    def __init__(
        self, 
        app_config: AppConfig,
    ):
        """
        Initialize the circuit breaker manager.
        
        Args:
            app_config: The application configuration object.
        """
        self.app_config = app_config
        self.metrics_collector = get_metrics_collector()
        self.logger = get_structured_logger(__name__)
        self.breakers: Dict[str, pybreaker.CircuitBreaker] = {}
        
    def get_breaker(self, selector_name: str) -> pybreaker.CircuitBreaker:
        """
        Get or create a circuit breaker for a selector.
        
        Args:
            selector_name: Name of the selector
            
        Returns:
            Circuit breaker instance for the selector
        """
        if selector_name not in self.breakers:
            # Create selector-specific logger
            logger = bind_context(self.logger, selector=selector_name)
            
            # Create listener for metrics collection
            listener = CircuitBreakerListener(
                self.metrics_collector, 
                logger,
                selector_name
            )
            
            # Get selector-specific configuration
            selector_config_override = self.app_config.selector_retry_overrides.overrides.get(selector_name, {})
            
            # Create circuit breaker with configuration
            self.breakers[selector_name] = pybreaker.CircuitBreaker(
                fail_max=selector_config_override.get(
                    "failure_threshold", 
                    self.app_config.circuit_breaker.failure_threshold
                ),
                reset_timeout=selector_config_override.get(
                    "recovery_timeout", 
                    self.app_config.circuit_breaker.recovery_timeout
                ),
                name=f"selector_{selector_name}",
                listeners=[listener],
                exclude=[self.app_config.circuit_breaker.expected_exception]
            )
        
        return self.breakers[selector_name]
    
    def get_all_states(self) -> Dict[str, str]:
        """
        Get the current state of all circuit breakers.
        
        Returns:
            Dictionary mapping selector names to circuit breaker states
        """
        return {
            name: breaker.current_state
            for name, breaker in self.breakers.items()
        }


# Singleton circuit breaker manager
_circuit_breaker_manager: Optional[SelectorCircuitBreaker] = None


def get_circuit_breaker_manager() -> SelectorCircuitBreaker:
    """
    Get the global circuit breaker manager instance.
    
    Returns:
        The singleton SelectorCircuitBreaker instance
    """
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = SelectorCircuitBreaker(config)
    return _circuit_breaker_manager


class SelectorExecutor:
    """
    Executes selector operations with retry and circuit breaker protection.
    
    This class provides resilient operations for Playwright selector interactions
    by combining retry with exponential backoff and circuit breaker patterns.
    It also collects metrics and provides structured logging.
    """
    
    def __init__(self, page: Page, app_config: AppConfig):
        """
        Initialize the selector executor.
        
        Args:
            page: Playwright page instance
            app_config: The application configuration object.
        """
        self.page = page
        self.app_config = app_config
        self.logger = get_structured_logger(__name__)
        self.metrics_collector = get_metrics_collector()
        self.circuit_breaker_manager = get_circuit_breaker_manager()
    
    async def _execute_with_resilience(
        self,
        selector_name: str,
        operation: Callable[..., Awaitable[T]],
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs
    ) -> T:
        """
        Execute an operation with retry and circuit breaker protection.
        
        Args:
            selector_name: Name of the selector
            operation: Async function to execute
            context: Additional context for logging
            *args: Positional arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If the operation fails after all retries, or if the circuit breaker is open
        """
        # Get selector-specific configuration
        selector_config_override = self.app_config.selector_retry_overrides.overrides.get(selector_name, {})
        
        # Configure retry with exponential backoff
        max_attempts = selector_config_override.get("max_attempts", self.app_config.resilience.max_attempts)
        initial_wait = selector_config_override.get("initial_wait", self.app_config.resilience.initial_wait)
        max_wait = selector_config_override.get("max_wait", self.app_config.resilience.max_wait)
        exponential_base = selector_config_override.get("exponential_base", self.app_config.resilience.exponential_base)
        use_jitter = selector_config_override.get("jitter", self.app_config.resilience.jitter)
        
        # Create a logger with context
        op_logger = bind_context(
            self.logger, 
            selector=selector_name,
            **(context or {})
        )
        
        # Get circuit breaker for this selector
        breaker = self.circuit_breaker_manager.get_breaker(selector_name)
        
        # Retry decorator configuration
        retry_config = {
            "stop": stop_after_attempt(max_attempts),
            "wait": wait_exponential(
                multiplier=initial_wait,
                min=initial_wait,
                max=max_wait,
                exp_base=exponential_base
            ),
            "retry": retry_if_exception_type((PlaywrightTimeoutError, Exception)),
            "reraise": True,
            "before": before_log(logger, logging.DEBUG),
            "after": after_log(logger, logging.DEBUG),
        }
        
        # Add jitter if configured
        if use_jitter:
            retry_config["wait"] = retry_config["wait"] + wait_random(0, 1)

        attempt = 0
        start_time = time.time()
        
        @retry(**retry_config)  # type: ignore
        async def _operation_with_retry() -> T:
            """Inner function to apply retry decorator."""
            nonlocal attempt
            attempt += 1
            
            op_start_time = time.time()
            
            try:
                op_logger.debug(
                    "selector_operation_start", 
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
                
                # Execute operation inside circuit breaker
                result = await breaker(operation)(*args, **kwargs)
                
                duration_ms = (time.time() - op_start_time) * 1000
                
                op_logger.debug(
                    "selector_operation_success",
                    duration_ms=round(duration_ms, 2),
                    attempt=attempt,
                )
                
                # Record successful execution
                self.metrics_collector.record_selector_execution(
                    selector_name=selector_name,
                    status="success",
                    duration_ms=duration_ms,
                    attempt=attempt,
                    context=context,
                )
                
                return result
                
            except Exception as e:
                duration_ms = (time.time() - op_start_time) * 1000
                
                # If this is the last attempt, log as error
                if attempt >= max_attempts:
                    op_logger.error(
                        "selector_operation_failed",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=round(duration_ms, 2),
                        attempt=attempt,
                    )
                else:
                    op_logger.warning(
                        "selector_operation_retry",
                        error=str(e),
                        error_type=type(e).__name__,
                        duration_ms=round(duration_ms, 2),
                        attempt=attempt,
                        next_attempt_in=f"{initial_wait * (exponential_base ** (attempt-1))}s",
                    )
                    
                    # Record retry metric
                    self.metrics_collector.record_selector_execution(
                        selector_name=selector_name,
                        status="retry",
                        duration_ms=duration_ms,
                        attempt=attempt,
                        error=str(e),
                        context=context,
                    )
                
                raise
        
        try:
            # Execute the operation with retry
            result = await _operation_with_retry()
            return result
            
        except (RetryError, Exception) as e:
            # Calculate total duration
            total_duration_ms = (time.time() - start_time) * 1000
            
            # Record failure metric
            self.metrics_collector.record_selector_execution(
                selector_name=selector_name,
                status="failure",
                duration_ms=total_duration_ms,
                attempt=attempt,
                error=str(e),
                context=context,
            )
            
            # Log the failure
            op_logger.error(
                "selector_operation_failed_all_retries",
                error=str(e),
                error_type=type(e).__name__,
                attempts=attempt,
                max_attempts=max_attempts,
                total_duration_ms=round(total_duration_ms, 2),
            )
            
            # Re-raise the original exception
            if isinstance(e, RetryError) and e.last_attempt.exception():
                raise e.last_attempt.exception() from None
            raise
            
    async def wait_for_selector(
        self, 
        selector_name: str, 
        css_selector: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Any:
        """
        Wait for a selector to be visible with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            css_selector: CSS selector string
            context: Additional context for logging
            timeout: Timeout in milliseconds. Defaults to config.performance.selector_timeout.
            
        Returns:
            Playwright ElementHandle
        """
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout

        async def operation():
            return await self.page.wait_for_selector(css_selector, timeout=timeout)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def click(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """
        Click on an element with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            await self.page.wait_for_selector(css_selector, timeout=timeout)
            await self.page.click(css_selector)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def fill(
        self, 
        selector_name: str, 
        value: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """
        Fill a form field with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            value: Value to fill in the form field
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            await self.page.wait_for_selector(css_selector, timeout=timeout)
            await self.page.fill(css_selector, value)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def check(
        self, 
        selector_name: str, 
        checked: bool = True,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """
        Check or uncheck a checkbox with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            checked: Whether to check or uncheck the checkbox
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            await self.page.wait_for_selector(css_selector, timeout=timeout)
            await self.page.set_checked(css_selector, checked)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def select_option(
        self, 
        selector_name: str, 
        value: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """
        Select an option from a dropdown with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            value: Value of the option to select
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            await self.page.wait_for_selector(css_selector, timeout=timeout)
            await self.page.select_option(css_selector, value)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def upload_file(
        self, 
        selector_name: str, 
        file_path: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """
        Upload a file with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            file_path: Path to the file to upload
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            await self.page.wait_for_selector(css_selector, timeout=timeout)
            await self.page.set_input_files(css_selector, file_path)
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def get_text(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> str:
        """
        Get the text content of an element with resilience.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
            
        Returns:
            Text content of the element
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            element = await self.page.wait_for_selector(css_selector, timeout=timeout)
            return await element.text_content() or ""
            
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context
        )
    
    async def is_visible(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> bool:
        """
        Check if an element is visible with resilience.
        
        This method doesn't throw if element is not found, just returns False.
        
        Args:
            selector_name: Name of the selector (for logs and metrics)
            css_selector: CSS selector string (defaults to selector name if not provided)
            context: Additional context for logging
            timeout: Timeout in milliseconds for wait_for_selector. Defaults to config.performance.selector_timeout.
            
        Returns:
            True if element is visible, False otherwise
        """
        if css_selector is None:
            from core.selectors import selectors
            css_selector = selectors.get(selector_name, selector_name)
        
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
            
        async def operation():
            try:
                element = await self.page.wait_for_selector(
                    css_selector, 
                    timeout=timeout,
                    state="visible"
                )
                return element is not None
            except PlaywrightTimeoutError:
                return False
            
        try:
            return await self._execute_with_resilience(
                selector_name=f"{selector_name}_visibility",
                operation=operation,
                context=context
            )
        except Exception:
            return False
    
    async def execute_operation(
        self,
        selector_name: str,
        operation: Callable[..., Awaitable[T]],
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs
    ) -> T:
        """
        Execute a custom operation with resilience (retry, circuit breaker, metrics).
        
        This is a public API for executing arbitrary operations that need resilience
        patterns but don't fit into the standard selector operations (click, fill, etc).
        
        Args:
            selector_name: Name of the selector/operation (for logs, metrics, and circuit breaker)
            operation: Async function to execute
            context: Additional context for logging
            *args: Positional arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If the operation fails after all retries, or if the circuit breaker is open
        """
        return await self._execute_with_resilience(
            selector_name=selector_name,
            operation=operation,
            context=context,
            *args,
            **kwargs
        )


# Singleton instance for app-wide selector executor
_selector_executor: Dict[int, SelectorExecutor] = {}


def get_selector_executor(page: Page) -> SelectorExecutor:
    """
    Get or create a selector executor for a page.
    
    Args:
        page: Playwright page instance
        
    Returns:
        SelectorExecutor instance for the page
    """
    page_id = id(page)
    if page_id not in _selector_executor:
        _selector_executor[page_id] = SelectorExecutor(page, config)
    return _selector_executor[page_id]


class ResilienceExecutor:
    """
    Universal executor for all types of operations with retry and circuit breaker protection.
    
    This class provides a unified interface for:
    - Selector operations (delegates to SelectorExecutor)
    - Navigation operations
    - Text extraction operations
    - Workflow operations (with cleanup between attempts)
    - DOM query operations
    
    All operations benefit from centralized configuration, metrics, and logging.
    """
    
    def __init__(self, page: Page, app_config: AppConfig):
        """
        Initialize the resilience executor.
        
        Args:
            page: Playwright page instance
            app_config: The application configuration object
        """
        self.page = page
        self.app_config = app_config
        self.selector_executor = SelectorExecutor(page, app_config)
        self.logger = get_structured_logger(__name__)
    
    # Delegate all SelectorExecutor methods for backward compatibility
    async def wait_for_selector(
        self, 
        selector_name: str, 
        css_selector: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Any:
        """Wait for a selector to be visible with resilience."""
        return await self.selector_executor.wait_for_selector(
            selector_name, css_selector, context, timeout
        )
    
    async def click(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """Click on an element with resilience."""
        return await self.selector_executor.click(
            selector_name, css_selector, context, timeout
        )
    
    async def fill(
        self, 
        selector_name: str, 
        value: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """Fill a form field with resilience."""
        return await self.selector_executor.fill(
            selector_name, value, css_selector, context, timeout
        )
    
    async def check(
        self, 
        selector_name: str, 
        checked: bool = True,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """Check or uncheck a checkbox with resilience."""
        return await self.selector_executor.check(
            selector_name, checked, css_selector, context, timeout
        )
    
    async def select_option(
        self, 
        selector_name: str, 
        value: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """Select an option from a dropdown with resilience."""
        return await self.selector_executor.select_option(
            selector_name, value, css_selector, context, timeout
        )
    
    async def upload_file(
        self, 
        selector_name: str, 
        file_path: str,
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> None:
        """Upload a file with resilience."""
        return await self.selector_executor.upload_file(
            selector_name, file_path, css_selector, context, timeout
        )
    
    async def get_text(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> str:
        """Get the text content of an element with resilience."""
        return await self.selector_executor.get_text(
            selector_name, css_selector, context, timeout
        )
    
    async def is_visible(
        self, 
        selector_name: str, 
        css_selector: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> bool:
        """Check if an element is visible with resilience."""
        return await self.selector_executor.is_visible(
            selector_name, css_selector, context, timeout
        )
    
    async def execute_operation(
        self,
        selector_name: str,
        operation: Callable[..., Awaitable[T]],
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs
    ) -> T:
        """Execute a custom operation with resilience."""
        return await self.selector_executor.execute_operation(
            selector_name, operation, context, *args, **kwargs
        )
    
    # New methods for unified retry mechanism
    
    async def navigate(
        self,
        url: str,
        context: Optional[Dict[str, Any]] = None,
        wait_until: str = "load",
        timeout: Optional[int] = None
    ) -> None:
        """
        Navigate to a URL with retry and circuit breaker protection.
        
        Args:
            url: URL to navigate to
            context: Additional context for logging
            wait_until: Navigation wait condition (load, domcontentloaded, networkidle)
            timeout: Timeout in milliseconds. Defaults to config.performance.selector_timeout.
        """
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
        
        # Get navigation-specific configuration
        selector_config_override = self.app_config.selector_retry_overrides.overrides.get("navigation", {})
        max_attempts = selector_config_override.get(
            "max_attempts", 
            self.app_config.resilience.navigation_max_attempts
        )
        
        async def nav_operation():
            await self.page.goto(url, wait_until=wait_until, timeout=timeout)
        
        return await self.selector_executor.execute_operation(
            selector_name="navigation",
            operation=nav_operation,
            context={**(context or {}), "url": url, "wait_until": wait_until}
        )
    
    async def extract_text_with_retry(
        self,
        locator: Locator,
        label: str,
        context: Optional[Dict[str, Any]] = None,
        custom_delays: Optional[Tuple[float, ...]] = None
    ) -> str:
        """
        Extract text from a locator with retries and scrolling.
        
        This method replaces the custom _extract_text_with_retry function.
        It scrolls to the locator, waits with delays, and extracts text until non-empty.
        
        Args:
            locator: Playwright Locator instance
            label: Label for logging (e.g., "Job description")
            context: Additional context for logging
            custom_delays: Custom delay sequence. Defaults to config.resilience.text_extraction_delays.
            
        Returns:
            Extracted text (non-empty)
            
        Raises:
            TimeoutError: If text is still empty after all retries
        """
        delays = custom_delays or self.app_config.resilience.text_extraction_delays
        delay_sequence_label = "/".join(str(delay) for delay in delays)
        
        op_logger = bind_context(
            self.logger,
            operation="extract_text_with_retry",
            label=label,
            **(context or {})
        )
        
        for attempt, delay in enumerate(delays, start=1):
            try:
                # Try to scroll to the locator
                try:
                    await locator.scroll_into_view_if_needed()
                except PlaywrightError as scroll_error:
                    op_logger.debug(
                        f"{label} locator not ready for scrolling (delay {delay}): {scroll_error}"
                    )
                    await asyncio.sleep(0.5)
                    continue
                
                # Wait for the specified delay
                await asyncio.sleep(delay)
                
                # Try to extract text
                try:
                    text = (await locator.inner_text()).strip()
                except PlaywrightError as read_error:
                    op_logger.debug(
                        f"Failed to read {label} text (delay {delay}): {read_error}"
                    )
                    continue
                
                # If we got non-empty text, return it
                if text:
                    op_logger.debug(f"Successfully extracted {label} text after {delay}s delay")
                    return text
                
                op_logger.debug(
                    f"{label} still empty after waiting {delay} seconds."
                )
                
            except Exception as e:
                op_logger.debug(f"Error during text extraction attempt {attempt}: {e}")
                continue
        
        # All attempts failed
        raise TimeoutError(
            f"{label} text did not load after waiting {delay_sequence_label} seconds."
        )
    
    async def execute_workflow_with_retry(
        self,
        operation_name: str,
        operation: Callable[..., Awaitable[T]],
        cleanup_between_attempts: Optional[Callable[[], Awaitable[None]]] = None,
        context: Optional[Dict[str, Any]] = None,
        *args,
        **kwargs
    ) -> T:
        """
        Execute a workflow operation with retry, exponential backoff, and optional cleanup.
        
        This method is designed for operations at the phase level (enrichment, processing)
        that may need cleanup between retry attempts (e.g., closing pages).
        
        Args:
            operation_name: Name of the operation (for logs, metrics, circuit breaker)
            operation: Async function to execute
            cleanup_between_attempts: Optional cleanup function to call between attempts
            context: Additional context for logging
            *args: Positional arguments to pass to the operation
            **kwargs: Keyword arguments to pass to the operation
            
        Returns:
            Result of the operation
            
        Raises:
            Exception: If the operation fails after all retries
        """
        # Get workflow-specific configuration
        selector_config_override = self.app_config.selector_retry_overrides.overrides.get("workflow", {})
        max_attempts = selector_config_override.get(
            "max_attempts",
            self.app_config.resilience.workflow_max_attempts
        )
        initial_wait = selector_config_override.get(
            "initial_wait",
            self.app_config.resilience.workflow_initial_wait
        )
        exponential_base = selector_config_override.get(
            "exponential_base",
            self.app_config.resilience.exponential_base
        )
        
        op_logger = bind_context(
            self.logger,
            operation=operation_name,
            **(context or {})
        )
        
        last_exception: Optional[Exception] = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                op_logger.debug(
                    f"Executing {operation_name} (attempt {attempt}/{max_attempts})"
                )
                
                result = await operation(*args, **kwargs)
                
                op_logger.info(
                    f"Successfully executed {operation_name} on attempt {attempt}"
                )
                return result
                
            except (PlaywrightError, Exception) as e:  # noqa: BLE001
                last_exception = e
                
                if attempt < max_attempts:
                    # Calculate wait time with exponential backoff
                    wait_seconds = initial_wait * (exponential_base ** (attempt - 1))
                    
                    op_logger.warning(
                        f"Attempt {attempt}/{max_attempts} failed for {operation_name}. "
                        f"Error: {e}. Retrying in {wait_seconds:.1f} seconds..."
                    )
                    
                    # Perform cleanup if provided
                    if cleanup_between_attempts:
                        try:
                            await cleanup_between_attempts()
                            op_logger.debug(f"Cleanup completed before retry {attempt + 1}")
                        except Exception as cleanup_error:
                            op_logger.warning(
                                f"Cleanup failed before retry: {cleanup_error}"
                            )
                    
                    await asyncio.sleep(wait_seconds)
                else:
                    # All attempts exhausted
                    op_logger.error(
                        f"All {max_attempts} attempts exhausted for {operation_name}. "
                        f"Last error: {e}"
                    )
                    raise
        
        # This should never be reached, but type checker needs it
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Failed to execute {operation_name} after {max_attempts} attempts")
    
    async def query_selector_with_retry(
        self,
        selector: str,
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None
    ) -> Optional[Any]:
        """
        Query a selector with retry and circuit breaker protection.
        
        Args:
            selector: CSS selector string
            context: Additional context for logging
            timeout: Timeout in milliseconds. Defaults to config.performance.selector_timeout.
            
        Returns:
            ElementHandle if found, None otherwise
        """
        if timeout is None:
            timeout = self.app_config.performance.selector_timeout
        
        async def query_operation():
            # Try to find the element directly
            element = await self.page.query_selector(selector)
            if element:
                return element
            # If not found, try using locator which supports complex selectors better
            try:
                locator = self.page.locator(selector).first
                await locator.wait_for(state="attached", timeout=min(timeout, 2000))
                return await self.page.query_selector(selector)
            except Exception:
                # Return None if selector not found (non-critical operation)
                return None
        
        try:
            return await self.selector_executor.execute_operation(
                selector_name="query_selector",
                operation=query_operation,
                context={**(context or {}), "selector": selector}
            )
        except Exception:
            # Return None if selector not found (non-critical operation)
            return None


# Singleton instance for app-wide resilience executor
_resilience_executor: Dict[int, ResilienceExecutor] = {}


def get_resilience_executor(page: Page) -> ResilienceExecutor:
    """
    Get or create a resilience executor for a page.
    
    Args:
        page: Playwright page instance
        
    Returns:
        ResilienceExecutor instance for the page
    """
    page_id = id(page)
    if page_id not in _resilience_executor:
        _resilience_executor[page_id] = ResilienceExecutor(page, config)
    return _resilience_executor[page_id]

