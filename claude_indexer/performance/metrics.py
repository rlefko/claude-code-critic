"""Performance metrics collection with percentile calculations.

This module provides a singleton metrics collector that accumulates
timing measurements and calculates statistical summaries including
percentiles (p50, p95, p99).

Example usage:
    collector = PerformanceMetricsCollector()

    # Record a measurement
    collector.record("search_latency", 45.2)

    # Record with context manager
    with collector.measure("index_file"):
        process_file(path)

    # Get statistics
    stats = collector.get_stats("search_latency")
    print(f"P95 latency: {stats['p95_ms']}ms")

    # Export all metrics
    all_stats = collector.get_all_stats()
"""

import time
from collections import deque
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class MetricWindow:
    """Time-windowed metric collection.

    Stores timestamped measurements with automatic pruning
    of old values outside the window.

    Attributes:
        values: Deque of (timestamp, value) tuples.
        window_seconds: Duration of the time window.
        max_samples: Maximum number of samples to keep.
    """

    values: deque = field(default_factory=lambda: deque(maxlen=1000))
    window_seconds: int = 300  # 5 minute default window
    max_samples: int = 1000

    def add(self, value: float) -> None:
        """Add a measurement to the window.

        Args:
            value: The measurement value in milliseconds.
        """
        self.values.append((time.time(), value))

    def get_values_in_window(self) -> list[float]:
        """Get all values within the current time window.

        Returns:
            List of values within the window.
        """
        now = time.time()
        return [v for t, v in self.values if now - t < self.window_seconds]


class PerformanceMetricsCollector:
    """Singleton for collecting performance metrics across operations.

    Provides thread-safe recording of timing measurements with
    statistical analysis including percentiles.

    This is a singleton - all instances share the same data.

    Example:
        collector = PerformanceMetricsCollector()
        collector.record("api_call", 150.5)

        stats = collector.get_stats("api_call")
        # {'count': 1, 'avg_ms': 150.5, 'p50_ms': 150.5, ...}
    """

    _instance = None
    _lock = Lock()

    def __new__(cls) -> "PerformanceMetricsCollector":
        """Return the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._metrics: dict[str, MetricWindow] = {}
                    instance._metrics_lock = Lock()
                    cls._instance = instance
        return cls._instance

    def record(self, operation: str, duration_ms: float) -> None:
        """Record a metric value.

        Args:
            operation: Name of the operation.
            duration_ms: Duration in milliseconds.
        """
        with self._metrics_lock:
            if operation not in self._metrics:
                self._metrics[operation] = MetricWindow()
            self._metrics[operation].add(duration_ms)

    @contextmanager
    def measure(self, operation: str) -> Generator[None, None, None]:
        """Context manager to measure and record operation duration.

        Args:
            operation: Name of the operation to measure.

        Yields:
            None - duration is recorded when context exits.

        Example:
            with collector.measure("parse_file"):
                parse(file)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.record(operation, duration_ms)

    def get_stats(self, operation: str) -> dict[str, float]:
        """Get statistics for an operation.

        Calculates count, average, min, max, and percentiles
        (p50, p95, p99) for all values in the time window.

        Args:
            operation: Name of the operation.

        Returns:
            Dictionary with statistical measures, or empty dict if no data.
        """
        with self._metrics_lock:
            if operation not in self._metrics:
                return {}

            window = self._metrics[operation]
            values = window.get_values_in_window()

            if not values:
                return {}

            sorted_values = sorted(values)
            n = len(sorted_values)

            return {
                "count": n,
                "avg_ms": sum(values) / n,
                "min_ms": sorted_values[0],
                "max_ms": sorted_values[-1],
                "p50_ms": self._percentile(sorted_values, 50),
                "p95_ms": self._percentile(sorted_values, 95),
                "p99_ms": self._percentile(sorted_values, 99),
            }

    def get_all_stats(self) -> dict[str, dict[str, float]]:
        """Get statistics for all operations.

        Returns:
            Dictionary mapping operation names to their statistics.
        """
        with self._metrics_lock:
            operations = list(self._metrics.keys())

        return {op: self.get_stats(op) for op in operations}

    def get_operations(self) -> list[str]:
        """Get list of all tracked operations.

        Returns:
            List of operation names.
        """
        with self._metrics_lock:
            return list(self._metrics.keys())

    def clear(self, operation: str | None = None) -> None:
        """Clear collected metrics.

        Args:
            operation: Specific operation to clear, or None for all.
        """
        with self._metrics_lock:
            if operation is None:
                self._metrics.clear()
            elif operation in self._metrics:
                del self._metrics[operation]

    def set_window(self, operation: str, window_seconds: int) -> None:
        """Set the time window for an operation's metrics.

        Args:
            operation: Name of the operation.
            window_seconds: New window duration in seconds.
        """
        with self._metrics_lock:
            if operation in self._metrics:
                self._metrics[operation].window_seconds = window_seconds
            else:
                window = MetricWindow(window_seconds=window_seconds)
                self._metrics[operation] = window

    def export(self) -> dict[str, Any]:
        """Export all metrics data for persistence.

        Returns:
            Dictionary with timestamp and all metrics data.
        """
        return {
            "timestamp": time.time(),
            "metrics": self.get_all_stats(),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], percentile: int) -> float:
        """Calculate a percentile value from sorted data.

        Args:
            sorted_values: Pre-sorted list of values.
            percentile: Percentile to calculate (0-100).

        Returns:
            The percentile value.
        """
        if not sorted_values:
            return 0.0

        n = len(sorted_values)
        if n == 1:
            return sorted_values[0]

        # Calculate index using nearest-rank method
        k = (percentile / 100) * (n - 1)
        f = int(k)
        c = f + 1 if f + 1 < n else f

        # Linear interpolation
        if f == c:
            return sorted_values[f]
        return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


# Module-level convenience instance
_collector = PerformanceMetricsCollector()


def record(operation: str, duration_ms: float) -> None:
    """Record a metric value using the global collector.

    Args:
        operation: Name of the operation.
        duration_ms: Duration in milliseconds.
    """
    _collector.record(operation, duration_ms)


def measure(operation: str):
    """Context manager for measuring operation duration.

    Args:
        operation: Name of the operation.

    Returns:
        Context manager that records duration on exit.
    """
    return _collector.measure(operation)


def get_stats(operation: str) -> dict[str, float]:
    """Get statistics for an operation.

    Args:
        operation: Name of the operation.

    Returns:
        Dictionary with statistical measures.
    """
    return _collector.get_stats(operation)


def get_all_stats() -> dict[str, dict[str, float]]:
    """Get statistics for all operations.

    Returns:
        Dictionary mapping operation names to statistics.
    """
    return _collector.get_all_stats()


__all__ = [
    "MetricWindow",
    "PerformanceMetricsCollector",
    "record",
    "measure",
    "get_stats",
    "get_all_stats",
]
