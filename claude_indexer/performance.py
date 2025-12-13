"""Performance timing decorators and utilities.

This module provides backward-compatible re-exports from the performance package.
New code should import from claude_indexer.performance package directly.

This module provides tools for measuring and logging execution times:
- @timed decorator for function timing
- PerformanceTimer context manager for code block timing
- PerformanceAggregator for collecting timing statistics

New features available in the performance package:
- EndToEndProfiler for operation-level profiling with sections
- PerformanceMetricsCollector for percentile-based metrics
- profile() convenience function

Example:
    from claude_indexer.performance import timed, PerformanceTimer

    @timed("process_file")
    def process(path):
        ...

    with PerformanceTimer("batch") as timer:
        process_batch(items)
    print(f"Took {timer.duration_ms}ms")
"""

# Backward-compatible re-exports from the performance package
from .performance import (  # Core timing (original exports); New profiler exports; New metrics exports
    PROFILING_ENABLED,
    EndToEndProfiler,
    MetricWindow,
    PerformanceAggregator,
    PerformanceMetricsCollector,
    PerformanceTimer,
    ProfileResult,
    ProfilerStack,
    get_all_stats,
    get_stats,
    measure,
    profile,
    record,
    timed,
)

__all__ = [
    # Original exports
    "timed",
    "PerformanceTimer",
    "PerformanceAggregator",
    # New profiler exports
    "PROFILING_ENABLED",
    "ProfileResult",
    "EndToEndProfiler",
    "ProfilerStack",
    "profile",
    # New metrics exports
    "MetricWindow",
    "PerformanceMetricsCollector",
    "record",
    "measure",
    "get_stats",
    "get_all_stats",
]
