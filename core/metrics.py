"""
Metrics collection and aggregation for LinkedIn Easy Apply Bot.

This module provides functionality for collecting, aggregating, and exporting
metrics about selector operations, application performance, and error rates.
"""

import json
import os
import time
import threading
from typing import Dict, List, Any, Optional, Union
import structlog
from config import config # Import the new config object


class MetricsCollector:
    """
    Collects and aggregates metrics for application operations.
    
    This class tracks operation statistics like success/failure rates,
    durations, and circuit breaker trips. It provides both real-time
    access to metrics and periodic export to JSON files.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize a new metrics collector.
        
        Args:
            config: Optional configuration dictionary for metrics collection
        """
        self.config = config or {}
        self.logger = structlog.get_logger(__name__)
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self.selector_metrics: Dict[str, Dict[str, Any]] = {}
        self.job_metrics: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()  # Ensure thread safety
        self.session_id = f"session_{int(time.time())}"
        self.start_time = time.time()
        
    def record_selector_execution(
        self, 
        selector_name: str, 
        status: str, 
        duration_ms: float, 
        attempt: int = 1,
        error: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record a single selector execution.
        
        Args:
            selector_name: Name of the selector used
            status: Status of the operation ("success", "failure", "retry")
            duration_ms: Duration of the operation in milliseconds
            attempt: Attempt number (for retry operations)
            error: Error message if operation failed
            context: Additional context like job_id, page_url, etc.
        """
        with self.lock:
            # Initialize selector metrics if needed
            if selector_name not in self.selector_metrics:
                self.selector_metrics[selector_name] = {
                    "total_executions": 0,
                    "successes": 0,
                    "failures": 0,
                    "retries": 0,
                    "total_duration_ms": 0,
                    "durations": [],  # For percentile calculations
                    "circuit_breaker_trips": 0,
                    "last_execution_time": time.time(),
                    "errors": [],  # Last few errors
                }
            
            # Update metrics
            metrics = self.selector_metrics[selector_name]
            metrics["total_executions"] += 1
            metrics["total_duration_ms"] += duration_ms
            metrics["durations"].append(duration_ms)
            metrics["last_execution_time"] = time.time()
            
            # Limit size of durations array to prevent memory issues
            max_samples = self.config.get("max_duration_samples", 100)
            if len(metrics["durations"]) > max_samples:
                metrics["durations"] = metrics["durations"][-max_samples:]
            
            # Update status counters
            if status == "success":
                metrics["successes"] += 1
            elif status == "failure":
                metrics["failures"] += 1
                # Store error with timestamp and context
                error_entry = {
                    "timestamp": time.time(),
                    "error": error or "Unknown error",
                    "attempt": attempt,
                    "context": context or {}
                }
                metrics["errors"].append(error_entry)
                # Limit error history
                if len(metrics["errors"]) > self.config.get("max_errors", 10):
                    metrics["errors"] = metrics["errors"][-self.config.get("max_errors", 10):]
            elif status == "retry":
                metrics["retries"] += 1
    
    def record_circuit_breaker_state_change(
        self, 
        breaker_name: str, 
        old_state: str, 
        new_state: str
    ) -> None:
        """
        Record a circuit breaker state change.
        
        Args:
            breaker_name: Name of the circuit breaker
            old_state: Previous state of the circuit breaker
            new_state: New state of the circuit breaker
        """
        # Extract selector name from breaker name (e.g., "selector_easy_apply_button" -> "easy_apply_button")
        selector_name = breaker_name.replace("selector_", "")
        
        with self.lock:
            # Initialize selector metrics if needed
            if selector_name not in self.selector_metrics:
                self.selector_metrics[selector_name] = {
                    "total_executions": 0,
                    "successes": 0,
                    "failures": 0,
                    "retries": 0,
                    "total_duration_ms": 0,
                    "durations": [],
                    "circuit_breaker_trips": 0,
                    "errors": [],
                    "last_execution_time": time.time(),
                }
            
            # Record trip count when circuit opens
            if old_state == "closed" and new_state == "open":
                self.selector_metrics[selector_name]["circuit_breaker_trips"] += 1
    
    def record_job_application(
        self, 
        job_id: str, 
        status: str, 
        duration_ms: float,
        job_info: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Record metrics for a job application attempt.
        
        Args:
            job_id: ID of the job
            status: Status of the application ("success", "failure", "skipped")
            duration_ms: Duration of the application process in milliseconds
            job_info: Additional job information
        """
        with self.lock:
            # Initialize job metrics counter if needed
            if "jobs" not in self.metrics:
                self.metrics["jobs"] = {
                    "total_attempted": 0,
                    "successes": 0,
                    "failures": 0,
                    "skipped": 0,
                    "total_duration_ms": 0,
                }
            
            # Update job metrics
            self.metrics["jobs"]["total_attempted"] += 1
            self.metrics["jobs"]["total_duration_ms"] += duration_ms
            
            if status == "success":
                self.metrics["jobs"]["successes"] += 1
            elif status == "failure":
                self.metrics["jobs"]["failures"] += 1
            elif status == "skipped":
                self.metrics["jobs"]["skipped"] += 1
            
            # Store individual job metrics
            self.job_metrics[job_id] = {
                "status": status,
                "duration_ms": duration_ms,
                "timestamp": time.time(),
                "job_info": job_info or {}
            }
    
    def get_selector_metrics(self, selector_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for a specific selector or all selectors.
        
        Args:
            selector_name: Name of the selector to get metrics for, or None for all
            
        Returns:
            Dictionary with selector metrics
        """
        with self.lock:
            if selector_name and selector_name in self.selector_metrics:
                return self._calculate_derived_metrics_for_selector(selector_name)
            else:
                result = {}
                for name in self.selector_metrics:
                    result[name] = self._calculate_derived_metrics_for_selector(name)
                return result
    
    def _calculate_derived_metrics_for_selector(self, selector_name: str) -> Dict[str, Any]:
        """
        Calculate derived metrics like averages and percentiles for a selector.
        
        Args:
            selector_name: Name of the selector
            
        Returns:
            Dictionary with calculated metrics
        """
        metrics = self.selector_metrics[selector_name]
        
        # Calculate percentiles if we have data
        p95_duration = None
        avg_duration = None
        
        if metrics["durations"]:
            sorted_durations = sorted(metrics["durations"])
            p95_idx = int(len(sorted_durations) * 0.95)
            p95_duration = sorted_durations[min(p95_idx, len(sorted_durations) - 1)]
            avg_duration = metrics["total_duration_ms"] / metrics["total_executions"]
        
        # Create result with calculated metrics
        result = {
            "total_executions": metrics["total_executions"],
            "successes": metrics["successes"],
            "failures": metrics["failures"],
            "retries": metrics["retries"],
            "success_rate": round(metrics["successes"] / max(metrics["total_executions"], 1) * 100, 2),
            "avg_duration_ms": round(avg_duration, 2) if avg_duration is not None else None,
            "p95_duration_ms": round(p95_duration, 2) if p95_duration is not None else None,
            "circuit_breaker_trips": metrics["circuit_breaker_trips"],
            "last_execution_time": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(metrics["last_execution_time"])
            ),
            "recent_errors": metrics.get("errors", [])[-3:],  # Last 3 errors
        }
        
        return result
    
    def get_aggregated_metrics(self) -> Dict[str, Any]:
        """
        Get aggregated metrics for the current session.
        
        Returns:
            Dictionary with all aggregated metrics
        """
        with self.lock:
            # Calculate overall session metrics
            aggregated = {
                "session_id": self.session_id,
                "start_time": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start_time)
                ),
                "current_time": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time())
                ),
                "duration_seconds": int(time.time() - self.start_time),
                "selectors": self.get_selector_metrics(),
                "jobs": self.metrics.get("jobs", {
                    "total_attempted": 0,
                    "successes": 0,
                    "failures": 0,
                    "skipped": 0,
                }),
            }
            
            return aggregated
    
    def export_metrics_to_json(self, file_path: Optional[str] = None) -> str:
        """
        Export metrics to a JSON file.
        
        Args:
            file_path: Path to save the JSON file, defaults to config value
            
        Returns:
            Path to the exported metrics file
        """
        if not file_path:
            file_path = str(config.logging.metrics_file_path) # Use the new config object
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # Write metrics to file
        with open(file_path, "w") as f:
            json.dump({"aggregated_metrics": self.get_aggregated_metrics()}, f, indent=2)
        
        self.logger.info("metrics_exported", file_path=file_path)
        return file_path


# Singleton instance for app-wide metrics
_instance: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """
    Get the global metrics collector instance.
    
    Returns:
        The singleton MetricsCollector instance
    """
    global _instance
    if _instance is None:
        _instance = MetricsCollector()
    return _instance

