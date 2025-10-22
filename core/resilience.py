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
from typing import Dict, Any, Optional, Callable, TypeVar, Union, cast, Awaitable

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
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

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

