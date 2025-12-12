"""Performance measurement and profiling utilities.

This package provides comprehensive tools for measuring, profiling,
and collecting performance metrics:

- **timing**: Basic timing decorators and context managers
  - `@timed` decorator for function timing
  - `PerformanceTimer` context manager
  - `PerformanceAggregator` for batch statistics

- **profiler**: End-to-end operation profiling
  - `EndToEndProfiler` with nested sections
  - `ProfileResult` for structured results
  - Environment-controlled enable/disable

- **metrics**: Metrics collection with percentiles
  - `PerformanceMetricsCollector` singleton
  - Time-windowed measurements
  - p50/p95/p99 percentile calculations

Example usage:

    # Simple timing
    from claude_indexer.performance import timed, PerformanceTimer

    @timed("process_file")
    def process(path):
        ...

    with PerformanceTimer("batch_operation") as timer:
        process_batch(items)
    print(f"Took {timer.duration_ms}ms")

    # End-to-end profiling
    from claude_indexer.performance import profile

    with profile("index_repository") as p:
        with p.section("discover"):
            files = discover(path)
        with p.section("parse"):
            entities = parse(files)
        p.add_metadata("file_count", len(files))

    result = p.result()

    # Metrics collection
    from claude_indexer.performance import record, get_stats

    record("search_latency", 45.2)
    stats = get_stats("search_latency")
    print(f"P95: {stats['p95_ms']}ms")
"""

# Re-export timing utilities (backward compatibility)
from .timing import PerformanceAggregator, PerformanceTimer, timed

# Re-export profiler
from .profiler import (
    PROFILING_ENABLED,
    EndToEndProfiler,
    ProfileResult,
    ProfilerStack,
    profile,
)

# Re-export metrics
from .metrics import (
    MetricWindow,
    PerformanceMetricsCollector,
    get_all_stats,
    get_stats,
    measure,
    record,
)

__all__ = [
    # Timing
    "timed",
    "PerformanceTimer",
    "PerformanceAggregator",
    # Profiler
    "PROFILING_ENABLED",
    "ProfileResult",
    "EndToEndProfiler",
    "ProfilerStack",
    "profile",
    # Metrics
    "MetricWindow",
    "PerformanceMetricsCollector",
    "record",
    "measure",
    "get_stats",
    "get_all_stats",
]
