"""Intelligent batch size optimizer with memory-aware scaling.

This module provides adaptive batch sizing based on memory pressure,
error rates, and success streaks for optimal indexing performance.
"""

import gc
from logging import Logger
from typing import Any

import psutil

from ..indexer_logging import get_logger
from .types import BatchMetrics, ThresholdConfig


class BatchOptimizer:
    """Intelligent batch size optimizer with memory-aware scaling.

    Implements adaptive batch sizing based on:
    - Memory pressure (reduce when approaching threshold)
    - Error rates (reduce when errors increase)
    - Success streaks (ramp up after consecutive successes)

    Features:
        - Automatic batch size adjustment
        - Memory monitoring with psutil
        - Configurable thresholds
        - History tracking for trend analysis

    Example:
        >>> optimizer = BatchOptimizer(initial_size=25, max_size=100)
        >>> batch_size = optimizer.get_batch_size()
        >>> # Process batch...
        >>> metrics = BatchMetrics(batch_size=25, processing_time_ms=1000, ...)
        >>> optimizer.record_batch(metrics)
        >>> new_size = optimizer.get_batch_size()  # May be adjusted
    """

    def __init__(
        self,
        initial_size: int = 25,
        max_size: int = 100,
        memory_threshold_mb: int = 2000,
        logger: Logger | None = None,
    ):
        """Initialize batch optimizer.

        Args:
            initial_size: Starting batch size
            max_size: Maximum batch size limit
            memory_threshold_mb: Memory threshold for reduction
            logger: Optional logger instance
        """
        self.logger = logger or get_logger()
        self.config = ThresholdConfig(
            min_batch_size=2,
            max_batch_size=max_size,
            memory_threshold_mb=memory_threshold_mb,
        )

        self._current_size = initial_size
        self._initial_size = initial_size
        self._initial_memory_mb: float = 0.0
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._history: list[BatchMetrics] = []
        self._reduction_reasons: list[str] = []

        # Record initial memory
        self._initial_memory_mb = self._get_memory_mb()

    def get_batch_size(self) -> int:
        """Get current recommended batch size.

        Returns:
            Current batch size, potentially adjusted based on conditions
        """
        # Check memory before returning size
        current_mb, should_reduce = self.check_memory()
        if should_reduce:
            self.force_reduce(f"memory pressure ({current_mb:.0f}MB)")

        return self._current_size

    def record_batch(self, metrics: BatchMetrics) -> None:
        """Record batch metrics and adjust size if needed.

        Args:
            metrics: Metrics from completed batch processing
        """
        self._history.append(metrics)

        # Check error rate
        error_rate = (
            metrics.error_count / metrics.batch_size if metrics.batch_size > 0 else 0.0
        )

        if error_rate > self.config.error_rate_threshold:
            # High error rate - reduce batch size
            self._consecutive_successes = 0
            self._consecutive_failures += 1

            if self._consecutive_failures >= 2:
                self._reduce_size("high error rate")
        else:
            # Success - potentially ramp up
            self._consecutive_failures = 0
            self._consecutive_successes += 1

            if (
                self._consecutive_successes
                >= self.config.consecutive_successes_for_ramp
            ):
                self._increase_size()
                self._consecutive_successes = 0

        # Check memory after batch
        current_mb, should_reduce = self.check_memory()
        if should_reduce:
            self.force_reduce(f"post-batch memory ({current_mb:.0f}MB)")
            # Trigger garbage collection
            gc.collect()

    def check_memory(self) -> tuple[float, bool]:
        """Check memory usage and determine if reduction needed.

        Returns:
            Tuple of (current_memory_mb, should_reduce_batch_size)
        """
        current_mb = self._get_memory_mb()
        should_reduce = current_mb > self.config.memory_threshold_mb

        return current_mb, should_reduce

    def force_reduce(self, reason: str) -> int:
        """Force immediate batch size reduction.

        Args:
            reason: Reason for the reduction (for logging)

        Returns:
            New batch size after reduction
        """
        old_size = self._current_size
        self._current_size = max(
            self.config.min_batch_size,
            int(self._current_size * self.config.ramp_down_factor),
        )
        self._reduction_reasons.append(reason)

        if self._current_size < old_size:
            self.logger.info(
                f"Reduced batch size: {old_size} -> {self._current_size} " f"({reason})"
            )

        return self._current_size

    def _reduce_size(self, reason: str) -> None:
        """Reduce batch size with reason tracking.

        Args:
            reason: Reason for reduction
        """
        self.force_reduce(reason)

    def _increase_size(self) -> None:
        """Increase batch size after successful batches."""
        old_size = self._current_size
        new_size = int(self._current_size * self.config.ramp_up_factor)
        self._current_size = min(new_size, self.config.max_batch_size)

        if self._current_size > old_size:
            self.logger.debug(
                f"Increased batch size: {old_size} -> {self._current_size} "
                f"(consecutive successes)"
            )

    def reset(self) -> None:
        """Reset optimizer to initial state."""
        self._current_size = self._initial_size
        self._consecutive_successes = 0
        self._consecutive_failures = 0
        self._history.clear()
        self._reduction_reasons.clear()
        self._initial_memory_mb = self._get_memory_mb()

    def get_statistics(self) -> dict[str, Any]:
        """Get optimizer statistics for reporting.

        Returns:
            Dictionary with optimizer stats and history summary
        """
        if not self._history:
            return {
                "current_size": self._current_size,
                "initial_size": self._initial_size,
                "batches_processed": 0,
                "avg_processing_time_ms": 0.0,
                "avg_files_per_second": 0.0,
                "total_errors": 0,
                "size_reductions": len(self._reduction_reasons),
                "reduction_reasons": self._reduction_reasons,
                "memory_mb": self._get_memory_mb(),
            }

        total_time = sum(m.processing_time_ms for m in self._history)
        total_files = sum(m.batch_size for m in self._history)
        total_errors = sum(m.error_count for m in self._history)

        return {
            "current_size": self._current_size,
            "initial_size": self._initial_size,
            "batches_processed": len(self._history),
            "avg_processing_time_ms": total_time / len(self._history),
            "avg_files_per_second": (
                total_files / (total_time / 1000) if total_time > 0 else 0.0
            ),
            "total_files_processed": total_files,
            "total_errors": total_errors,
            "error_rate": total_errors / total_files if total_files > 0 else 0.0,
            "size_reductions": len(self._reduction_reasons),
            "reduction_reasons": self._reduction_reasons,
            "consecutive_successes": self._consecutive_successes,
            "memory_mb": self._get_memory_mb(),
            "memory_delta_mb": self._get_memory_mb() - self._initial_memory_mb,
        }

    def _get_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    @property
    def current_size(self) -> int:
        """Current batch size (without memory check)."""
        return self._current_size

    @property
    def can_increase(self) -> bool:
        """Whether batch size can be increased."""
        return self._current_size < self.config.max_batch_size

    @property
    def at_minimum(self) -> bool:
        """Whether batch size is at minimum."""
        return self._current_size <= self.config.min_batch_size
