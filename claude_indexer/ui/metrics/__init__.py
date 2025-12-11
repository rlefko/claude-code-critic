"""Metrics collection and analysis for UI consistency checking.

This module provides metrics tracking to measure the effectiveness of
UI quality enforcement over time, including:
- Token drift reduction
- Deduplication progress
- Suppression rates
- Performance percentiles
"""

from .aggregator import MetricsAggregator
from .collector import MetricsCollector
from .models import (
    MetricSnapshot,
    MetricsReport,
    PerformancePercentiles,
    PlanAdoptionRecord,
)

__all__ = [
    "MetricSnapshot",
    "MetricsReport",
    "PerformancePercentiles",
    "PlanAdoptionRecord",
    "MetricsCollector",
    "MetricsAggregator",
]
