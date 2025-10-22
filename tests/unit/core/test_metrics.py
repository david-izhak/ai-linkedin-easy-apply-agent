"""
Unit tests for the metrics module.
"""

import json
import os
import pytest
import time
from unittest.mock import MagicMock, patch
from tempfile import TemporaryDirectory
from dataclasses import dataclass, replace
from pathlib import Path

from core.metrics import MetricsCollector, get_metrics_collector
from config import config, AppConfig


@pytest.fixture
def mock_logger():
    """Fixture to provide a mock structlog logger."""
    logger = MagicMock()
    logger.info.return_value = None
    logger.debug.return_value = None
    logger.warning.return_value = None
    logger.error.return_value = None
    return logger


@pytest.fixture
def metrics_collector(mock_logger):
    """Fixture to provide a MetricsCollector instance with mock logger."""
    with patch("structlog.get_logger", return_value=mock_logger):
        collector = MetricsCollector(config={
            "max_duration_samples": 5,
            "max_errors": 3,
        })
        # Set a fixed session_id for testing
        collector.session_id = "test_session"
        collector.start_time = time.time() - 60  # Started 60 seconds ago
        return collector


class TestMetricsCollector:
    """Tests for the MetricsCollector class."""
    
    def test_record_selector_execution_success(self, metrics_collector):
        """Test recording a successful selector execution."""
        # Record a successful execution
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="success",
            duration_ms=100.0,
            attempt=1,
        )
        
        # Verify metrics were recorded
        assert "test_selector" in metrics_collector.selector_metrics
        metrics = metrics_collector.selector_metrics["test_selector"]
        assert metrics["total_executions"] == 1
        assert metrics["successes"] == 1
        assert metrics["failures"] == 0
        assert metrics["retries"] == 0
        assert metrics["total_duration_ms"] == 100.0
        assert len(metrics["durations"]) == 1
        assert metrics["durations"][0] == 100.0
        
    def test_record_selector_execution_failure(self, metrics_collector):
        """Test recording a failed selector execution."""
        # Record a failed execution
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="failure",
            duration_ms=200.0,
            attempt=2,
            error="Element not found",
            context={"job_id": "12345"}
        )
        
        # Verify metrics were recorded
        assert "test_selector" in metrics_collector.selector_metrics
        metrics = metrics_collector.selector_metrics["test_selector"]
        assert metrics["total_executions"] == 1
        assert metrics["successes"] == 0
        assert metrics["failures"] == 1
        assert metrics["retries"] == 0
        assert metrics["total_duration_ms"] == 200.0
        assert len(metrics["durations"]) == 1
        assert metrics["durations"][0] == 200.0
        
        # Verify error was recorded
        assert len(metrics["errors"]) == 1
        assert metrics["errors"][0]["error"] == "Element not found"
        assert metrics["errors"][0]["attempt"] == 2
        assert metrics["errors"][0]["context"] == {"job_id": "12345"}
        
    def test_record_selector_execution_retry(self, metrics_collector):
        """Test recording a retry selector execution."""
        # Record a retry execution
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="retry",
            duration_ms=50.0,
            attempt=1,
        )
        
        # Verify metrics were recorded
        assert "test_selector" in metrics_collector.selector_metrics
        metrics = metrics_collector.selector_metrics["test_selector"]
        assert metrics["total_executions"] == 1
        assert metrics["successes"] == 0
        assert metrics["failures"] == 0
        assert metrics["retries"] == 1
        assert metrics["total_duration_ms"] == 50.0
        
    def test_record_circuit_breaker_state_change(self, metrics_collector):
        """Test recording a circuit breaker state change."""
        # Record a state change from closed to open
        metrics_collector.record_circuit_breaker_state_change(
            breaker_name="selector_test_selector",
            old_state="closed",
            new_state="open"
        )
        
        # Verify metrics were recorded
        assert "test_selector" in metrics_collector.selector_metrics
        metrics = metrics_collector.selector_metrics["test_selector"]
        assert metrics["circuit_breaker_trips"] == 1
        
        # Record another state change, but not from closed to open
        metrics_collector.record_circuit_breaker_state_change(
            breaker_name="selector_test_selector",
            old_state="open",
            new_state="half-open"
        )
        
        # Verify trip count didn't change
        assert metrics_collector.selector_metrics["test_selector"]["circuit_breaker_trips"] == 1
        
    def test_record_job_application(self, metrics_collector):
        """Test recording a job application."""
        # Record a successful job application
        metrics_collector.record_job_application(
            job_id="12345",
            status="success",
            duration_ms=5000.0,
            job_info={
                "title": "Software Engineer",
                "company": "Example Inc."
            }
        )
        
        # Verify metrics were recorded
        assert "jobs" in metrics_collector.metrics
        jobs_metrics = metrics_collector.metrics["jobs"]
        assert jobs_metrics["total_attempted"] == 1
        assert jobs_metrics["successes"] == 1
        assert jobs_metrics["failures"] == 0
        assert jobs_metrics["skipped"] == 0
        assert jobs_metrics["total_duration_ms"] == 5000.0
        
        # Verify job-specific metrics
        assert "12345" in metrics_collector.job_metrics
        job_metrics = metrics_collector.job_metrics["12345"]
        assert job_metrics["status"] == "success"
        assert job_metrics["duration_ms"] == 5000.0
        assert job_metrics["job_info"] == {
            "title": "Software Engineer",
            "company": "Example Inc."
        }
        
    def test_get_selector_metrics_single(self, metrics_collector):
        """Test getting metrics for a single selector."""
        # Record some metrics
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="success",
            duration_ms=100.0
        )
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="success",
            duration_ms=200.0
        )
        
        # Get metrics for this selector
        metrics = metrics_collector.get_selector_metrics("test_selector")
        
        # Verify metrics
        assert metrics["total_executions"] == 2
        assert metrics["successes"] == 2
        assert metrics["failures"] == 0
        assert metrics["success_rate"] == 100.0
        assert metrics["avg_duration_ms"] == 150.0
        assert metrics["p95_duration_ms"] == 200.0
        
    def test_get_selector_metrics_all(self, metrics_collector):
        """Test getting metrics for all selectors."""
        # Record metrics for two selectors
        metrics_collector.record_selector_execution(
            selector_name="selector1",
            status="success",
            duration_ms=100.0
        )
        metrics_collector.record_selector_execution(
            selector_name="selector2",
            status="failure",
            duration_ms=200.0
        )
        
        # Get metrics for all selectors
        metrics = metrics_collector.get_selector_metrics()
        
        # Verify metrics for both selectors are included
        assert "selector1" in metrics
        assert "selector2" in metrics
        assert metrics["selector1"]["total_executions"] == 1
        assert metrics["selector1"]["successes"] == 1
        assert metrics["selector2"]["total_executions"] == 1
        assert metrics["selector2"]["failures"] == 1
        
    def test_get_aggregated_metrics(self, metrics_collector):
        """Test getting aggregated metrics."""
        # Record some metrics
        metrics_collector.record_selector_execution(
            selector_name="test_selector",
            status="success",
            duration_ms=100.0
        )
        metrics_collector.record_job_application(
            job_id="12345",
            status="success",
            duration_ms=5000.0
        )
        
        # Get aggregated metrics
        metrics = metrics_collector.get_aggregated_metrics()
        
        # Verify aggregated metrics
        assert metrics["session_id"] == "test_session"
        assert "start_time" in metrics
        assert "current_time" in metrics
        assert metrics["duration_seconds"] >= 60  # Started 60 seconds ago
        assert "selectors" in metrics
        assert "test_selector" in metrics["selectors"]
        assert "jobs" in metrics
        assert metrics["jobs"]["total_attempted"] == 1
        assert metrics["jobs"]["successes"] == 1
        
    def test_max_duration_samples(self, metrics_collector):
        """Test that durations are limited to max_duration_samples."""
        # Record more durations than the limit (5)
        for i in range(10):
            metrics_collector.record_selector_execution(
                selector_name="test_selector",
                status="success",
                duration_ms=i * 100.0
            )
        
        # Verify only the last 5 durations were kept
        durations = metrics_collector.selector_metrics["test_selector"]["durations"]
        assert len(durations) == 5
        assert durations == [500.0, 600.0, 700.0, 800.0, 900.0]
        
    def test_max_errors(self, metrics_collector):
        """Test that errors are limited to max_errors."""
        # Record more errors than the limit (3)
        for i in range(5):
            metrics_collector.record_selector_execution(
                selector_name="test_selector",
                status="failure",
                duration_ms=100.0,
                error=f"Error {i}"
            )
        
        # Verify only the last 3 errors were kept
        errors = metrics_collector.selector_metrics["test_selector"]["errors"]
        assert len(errors) == 3
        assert [e["error"] for e in errors] == ["Error 2", "Error 3", "Error 4"]
        
    def test_export_metrics_to_json(self, metrics_collector, app_config):
        """Test exporting metrics to a JSON file."""
        # Record some metrics
        metrics_collector.record_selector_execution(
            selector_name="test_selector", status="success", duration_ms=100.0
        )

        # Create a temporary directory for the test
        with TemporaryDirectory() as temp_dir:
            metrics_file_path = Path(temp_dir) / "metrics.json"
            test_config = app_config.model_copy(
                update={
                    "logging": app_config.logging.model_copy(
                        update={"metrics_file_path": str(metrics_file_path)}
                    )
                }
            )
            metrics_collector.export_metrics_to_json(test_config.logging.metrics_file_path)

            # Verify the file was created and contains the correct data
            assert metrics_file_path.exists()
            with open(metrics_file_path, "r") as f:
                data = json.load(f)
                assert "aggregated_metrics" in data
                assert "selectors" in data["aggregated_metrics"]
                assert "test_selector" in data["aggregated_metrics"]["selectors"]


def test_get_metrics_collector():
    """Test the singleton metrics collector."""
    # Get the collector twice
    with patch("structlog.get_logger"):
        collector1 = get_metrics_collector()
        collector2 = get_metrics_collector()
        
        # Verify they are the same object
        assert collector1 is collector2

