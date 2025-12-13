"""Performance timing decorators and utilities.

This module provides tools for measuring and logging execution times:
- @timed decorator for function timing
- PerformanceTimer context manager for code block timing
- PerformanceAggregator for collecting timing statistics
"""

import functools
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, ParamSpec, TypeVar

from ..indexer_logging import get_logger

P = ParamSpec("P")
T = TypeVar("T")


def timed(
    operation_name: str | None = None, log_args: bool = False
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator to time function execution and log results.

    Measures the execution time of a function and logs it at DEBUG level.
    The timing information is also available as extra fields for JSON logging.

    Args:
        operation_name: Custom name for the operation (defaults to function name).
        log_args: Whether to include function arguments in log (use carefully).

    Returns:
        Decorator function.

    Example:
        >>> @timed("index_file")
        ... def process_file(path: Path) -> Entity:
        ...     ...

        >>> @timed(log_args=True)
        ... def expensive_search(query: str, limit: int) -> list:
        ...     ...
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            logger = get_logger()
            op_name = operation_name or func.__name__

            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Build log message
                msg = f"[PERF] {op_name} completed in {duration_ms:.2f}ms"
                if log_args and (args or kwargs):
                    msg += f" (args={args}, kwargs={kwargs})"

                # Log with extra fields for JSON formatter
                logger.debug(
                    msg,
                    extra={
                        "duration_ms": duration_ms,
                        "operation": op_name,
                    },
                )
                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.error(
                    f"[PERF] {op_name} failed after {duration_ms:.2f}ms: {e}",
                    extra={
                        "duration_ms": duration_ms,
                        "operation": op_name,
                    },
                )
                raise

        return wrapper

    return decorator


class PerformanceTimer:
    """Context manager for timing code blocks.

    Measures execution time of a code block and optionally logs it.
    The duration is available as an attribute after the context exits.

    Attributes:
        operation_name: Name of the operation being timed.
        auto_log: Whether to automatically log timing.
        start_time: Unix timestamp when timing started.
        end_time: Unix timestamp when timing ended.
        duration_ms: Execution time in milliseconds.

    Example:
        >>> with PerformanceTimer("embedding_batch") as timer:
        ...     results = embedder.embed(texts)
        >>> print(f"Embedded in {timer.duration_ms:.2f}ms")
    """

    def __init__(self, operation_name: str, auto_log: bool = True):
        """Initialize the timer.

        Args:
            operation_name: Name of the operation being timed.
            auto_log: Whether to log timing automatically on exit.
        """
        self.operation_name = operation_name
        self.auto_log = auto_log
        self.start_time: float = 0
        self.end_time: float = 0
        self.duration_ms: float = 0

    def __enter__(self) -> "PerformanceTimer":
        """Start timing."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop timing and optionally log."""
        self.end_time = time.perf_counter()
        self.duration_ms = (self.end_time - self.start_time) * 1000

        if self.auto_log:
            logger = get_logger()
            if exc_type is None:
                logger.debug(
                    f"[PERF] {self.operation_name}: {self.duration_ms:.2f}ms",
                    extra={
                        "duration_ms": self.duration_ms,
                        "operation": self.operation_name,
                    },
                )
            else:
                logger.error(
                    f"[PERF] {self.operation_name} failed after {self.duration_ms:.2f}ms",
                    extra={
                        "duration_ms": self.duration_ms,
                        "operation": self.operation_name,
                    },
                )


class PerformanceAggregator:
    """Aggregate timing data for performance analysis.

    Collects timing measurements for multiple operations and generates
    statistics including count, total, average, min, and max times.

    Example:
        >>> perf = PerformanceAggregator()
        >>> for file in files:
        ...     with perf.track("parse_file"):
        ...         parse(file)
        ...     with perf.track("embed"):
        ...         embed(file)
        >>> perf.log_report()
    """

    def __init__(self) -> None:
        """Initialize the aggregator with empty timings."""
        self.timings: dict[str, list[float]] = {}

    @contextmanager
    def track(self, operation_name: str) -> Generator[None, None, None]:
        """Track timing for an operation.

        Args:
            operation_name: Name of the operation to track.

        Yields:
            None - timing is recorded when context exits.
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            if operation_name not in self.timings:
                self.timings[operation_name] = []
            self.timings[operation_name].append(duration_ms)

    def record(self, operation_name: str, duration_ms: float) -> None:
        """Manually record a timing measurement.

        Args:
            operation_name: Name of the operation.
            duration_ms: Duration in milliseconds.
        """
        if operation_name not in self.timings:
            self.timings[operation_name] = []
        self.timings[operation_name].append(duration_ms)

    def report(self) -> dict[str, dict[str, float]]:
        """Generate performance report with statistics.

        Returns:
            Dictionary mapping operation names to their statistics:
            - count: Number of measurements
            - total_ms: Total time in milliseconds
            - avg_ms: Average time in milliseconds
            - min_ms: Minimum time in milliseconds
            - max_ms: Maximum time in milliseconds
        """
        report: dict[str, dict[str, float]] = {}
        for op_name, times in self.timings.items():
            if times:
                report[op_name] = {
                    "count": len(times),
                    "total_ms": sum(times),
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                }
        return report

    def log_report(self) -> None:
        """Log the performance report."""
        logger = get_logger()
        report = self.report()

        if not report:
            logger.info("[PERF] No performance data collected")
            return

        logger.info("=== Performance Report ===")
        for op_name, stats in sorted(report.items()):
            logger.info(
                f"  {op_name}: {stats['count']:.0f} calls, "
                f"avg={stats['avg_ms']:.2f}ms, "
                f"total={stats['total_ms']:.2f}ms, "
                f"min={stats['min_ms']:.2f}ms, "
                f"max={stats['max_ms']:.2f}ms"
            )

    def reset(self) -> None:
        """Clear all collected timing data."""
        self.timings.clear()


__all__ = ["timed", "PerformanceTimer", "PerformanceAggregator"]
