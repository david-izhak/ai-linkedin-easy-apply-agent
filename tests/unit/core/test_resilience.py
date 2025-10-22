"""
Unit tests for the resilience module.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time
from typing import Any, Dict
from dataclasses import dataclass, field
from pybreaker import CircuitBreakerError

from core.resilience import (
    SelectorCircuitBreaker, 
    CircuitBreakerListener, 
    SelectorExecutor,
    get_circuit_breaker_manager,
    get_selector_executor
)
from config import AppConfig


@pytest.fixture
def mock_logger():
    """Fixture to provide a mock structlog logger."""
    logger = MagicMock()
    logger.bind.return_value = logger
    logger.debug.return_value = None
    logger.info.return_value = None
    logger.warning.return_value = None
    logger.error.return_value = None
    return logger


@pytest.fixture
def mock_metrics_collector():
    """Fixture to provide a mock metrics collector."""
    collector = MagicMock()
    collector.record_selector_execution.return_value = None
    collector.record_circuit_breaker_state_change.return_value = None
    return collector


@pytest.fixture
def mock_page():
    """Fixture to provide a mock Playwright page."""
    page = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.click = AsyncMock()
    page.fill = AsyncMock()
    page.set_checked = AsyncMock()
    return page


@pytest.fixture
def circuit_breaker_listener(mock_logger, mock_metrics_collector):
    """Fixture to provide a CircuitBreakerListener instance."""
    return CircuitBreakerListener(
        metrics_collector=mock_metrics_collector,
        logger=mock_logger,
        selector_name="test_selector"
    )


@pytest.fixture
def circuit_breaker_manager(mock_metrics_collector):
    """Fixture to provide a SelectorCircuitBreaker instance."""
    @dataclass
    class MockCircuitBreakerConfig:
        failure_threshold: int = 3
        recovery_timeout: int = 5
        expected_exception: type = Exception

    @dataclass
    class MockSelectorRetryOverrideConfig:
        overrides: Dict[str, Any] = field(default_factory=dict)

    @dataclass
    class MockAppConfig:
        circuit_breaker: MockCircuitBreakerConfig = field(default_factory=MockCircuitBreakerConfig)
        selector_retry_overrides: MockSelectorRetryOverrideConfig = field(default_factory=MockSelectorRetryOverrideConfig)

    with patch("core.resilience.get_metrics_collector", return_value=mock_metrics_collector):
        with patch("core.resilience.get_structured_logger"):
            manager = SelectorCircuitBreaker(app_config=MockAppConfig())
            yield manager


class MockBreaker:
    """Mock circuit breaker for testing."""
    
    def __init__(self, should_fail=False):
        """Initialize with failure flag."""
        self.should_fail = should_fail
        self.call_count = 0
    
    def __call__(self, fn):
        """Return a callable that wraps the function."""
        async def wrapper(*args, **kwargs):
            self.call_count += 1
            if self.should_fail:
                raise CircuitBreakerError("Circuit breaker open")
            return await fn(*args, **kwargs)
        return wrapper


@pytest.fixture
def selector_executor(mock_page, mock_metrics_collector):
    """Fixture to provide a SelectorExecutor instance."""
    @dataclass
    class MockResilienceConfig:
        max_attempts: int = 3
        initial_wait: float = 0.01
        max_wait: float = 0.05
        exponential_base: int = 2
        jitter: bool = False

    @dataclass
    class MockSelectorRetryOverrideConfig:
        overrides: Dict[str, Any] = field(default_factory=dict)
        
    @dataclass
    class MockPerformanceConfig:
        selector_timeout: int = 1000

    @dataclass
    class MockAppConfig:
        resilience: MockResilienceConfig = field(default_factory=MockResilienceConfig)
        selector_retry_overrides: MockSelectorRetryOverrideConfig = field(default_factory=MockSelectorRetryOverrideConfig)
        performance: MockPerformanceConfig = field(default_factory=MockPerformanceConfig)

    with patch("core.resilience.get_metrics_collector", return_value=mock_metrics_collector):
        with patch("core.resilience.get_structured_logger"):
            with patch("core.resilience.get_circuit_breaker_manager") as mock_cb_manager:
                # Create a mock breaker that doesn't fail
                mock_breaker = MockBreaker(should_fail=False)
                # Make the manager return our mock breaker
                mock_cb_manager.return_value.get_breaker.return_value = mock_breaker
                
                executor = SelectorExecutor(
                    page=mock_page,
                    app_config=MockAppConfig()
                )
                yield executor


class TestCircuitBreakerListener:
    """Tests for the CircuitBreakerListener class."""
    
    def test_state_change(self, circuit_breaker_listener, mock_logger, mock_metrics_collector):
        """Test that state changes are logged and recorded."""
        # Create mock states and breaker
        old_state = MagicMock()
        old_state.name = "closed"
        new_state = MagicMock()
        new_state.name = "open"
        breaker = MagicMock()
        breaker.name = "selector_test_selector"
        
        # Call the method
        circuit_breaker_listener.state_change(breaker, old_state, new_state)
        
        # Verify logger was called
        mock_logger.warning.assert_called_once()
        # Verify metrics were recorded
        mock_metrics_collector.record_circuit_breaker_state_change.assert_called_once_with(
            "selector_test_selector", "closed", "open"
        )


class TestSelectorCircuitBreaker:
    """Tests for the SelectorCircuitBreaker class."""
    
    def test_get_breaker(self, circuit_breaker_manager):
        """Test that a circuit breaker is created and cached."""
        # Get a breaker
        breaker1 = circuit_breaker_manager.get_breaker("test_selector")
        
        # Get the same breaker again
        breaker2 = circuit_breaker_manager.get_breaker("test_selector")
        
        # Verify they are the same object
        assert breaker1 is breaker2
        
        # Verify the breaker configuration
        assert breaker1.fail_max == 3
        assert breaker1.reset_timeout == 5
        
    def test_get_all_states(self, circuit_breaker_manager):
        """Test getting the state of all circuit breakers."""
        # Create two breakers
        circuit_breaker_manager.get_breaker("selector1")
        circuit_breaker_manager.get_breaker("selector2")
        
        # Get all states
        states = circuit_breaker_manager.get_all_states()
        
        # Verify we have states for both selectors
        assert "selector1" in states
        assert "selector2" in states
        
        # Verify the states are "closed" (default)
        assert states["selector1"] == "closed"
        assert states["selector2"] == "closed"


@pytest.mark.asyncio
class TestSelectorExecutor:
    """Tests for the SelectorExecutor class."""
    
    async def test_click_success(self, selector_executor, mock_page):
        """Test successful click operation."""
        # Call the method
        await selector_executor.click("test_selector")
        
        # Verify page methods were called
        mock_page.wait_for_selector.assert_called_once()
        mock_page.click.assert_called_once()
        
    async def test_click_with_retry(self, selector_executor, mock_page):
        """Test click operation with retry on failure."""
        # Make the first two attempts fail
        fail_count = 0
        
        async def fail_twice(*args, **kwargs):
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 2:
                raise Exception("Simulated failure")
            
        # Patch the wait_for_selector method to fail twice then succeed
        mock_page.wait_for_selector.side_effect = fail_twice
        
        # Call the method (should retry and succeed on 3rd attempt)
        await selector_executor.click("test_selector")
        
        # Verify it was called 3 times (2 failures + 1 success)
        assert fail_count == 3
        # Verify click was called once (on the success)
        mock_page.click.assert_called_once()
        
    async def test_click_max_retries_exceeded(self, selector_executor, mock_page):
        """Test click operation when max retries are exceeded."""
        # Make all attempts fail
        mock_page.wait_for_selector.side_effect = Exception("Simulated failure")
        
        # Call the method (should raise an exception)
        with pytest.raises(Exception, match="Simulated failure"):
            await selector_executor.click("test_selector")
        
        # Verify page.click was never called
        mock_page.click.assert_not_called()
    
    async def test_circuit_breaker_open(self, selector_executor, mock_page):
        """Test operation when circuit breaker is open."""
        # Get the mock breaker manager
        manager = selector_executor.circuit_breaker_manager
        
        # Replace the mock with one that fails
        manager.get_breaker.return_value = MockBreaker(should_fail=True)
        
        # Call the method (should raise CircuitBreakerError)
        with pytest.raises(CircuitBreakerError, match="Circuit breaker open"):
            await selector_executor.click("test_selector")


def test_get_circuit_breaker_manager(monkeypatch):
    """Test the singleton circuit breaker manager."""
    # Reset singleton for isolated test run
    monkeypatch.setattr("core.resilience._circuit_breaker_manager", None)
    
    # Get the manager twice
    with patch("core.resilience.get_structured_logger"):
        with patch("core.resilience.get_metrics_collector"):
            # Patch config to avoid dependency on global state
            monkeypatch.setattr("core.resilience.config", MagicMock(spec=AppConfig))
            manager1 = get_circuit_breaker_manager()
            manager2 = get_circuit_breaker_manager()
            
            # Verify they are the same object
            assert manager1 is manager2


@pytest.mark.asyncio
async def test_get_selector_executor(mock_page, monkeypatch):
    """Test the singleton selector executor."""
    # Reset singleton for isolated test run
    monkeypatch.setattr("core.resilience._selector_executor", {})
    
    # Get the executor twice for the same page
    with patch("core.resilience.get_structured_logger"):
        with patch("core.resilience.get_metrics_collector"):
            with patch("core.resilience.get_circuit_breaker_manager"):
                # Patch config to avoid dependency on global state
                monkeypatch.setattr("core.resilience.config", MagicMock(spec=AppConfig))
                executor1 = get_selector_executor(mock_page)
                executor2 = get_selector_executor(mock_page)
                
                # Verify they are the same object
                assert executor1 is executor2
                
                # But different pages get different executors
                mock_page2 = AsyncMock()
                executor3 = get_selector_executor(mock_page2)
                assert executor1 is not executor3
