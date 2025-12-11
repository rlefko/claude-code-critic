"""Metrics aggregator for trend analysis.

This module provides the MetricsAggregator class for analyzing
metrics trends and generating insights.
"""

from datetime import datetime, timedelta
from typing import Any

from .models import MetricsReport, PerformancePercentiles


class MetricsAggregator:
    """Analyzes metrics trends and generates insights.

    Provides trend analysis, target comparison, and summary
    generation for metrics dashboards.
    """

    def __init__(self, report: MetricsReport):
        """Initialize the aggregator.

        Args:
            report: MetricsReport to analyze.
        """
        self.report = report

    def calculate_color_reduction(self) -> float:
        """Calculate % reduction in unique hardcoded colors.

        Compares current value to baseline (first recorded).

        Returns:
            Reduction percentage (0-100). Negative if increased.
        """
        if self.report.baseline_unique_colors == 0:
            return 0.0

        return (
            (self.report.baseline_unique_colors - self.report.current_unique_colors)
            / self.report.baseline_unique_colors
        ) * 100

    def calculate_spacing_reduction(self) -> float:
        """Calculate % reduction in unique hardcoded spacings.

        Returns:
            Reduction percentage (0-100). Negative if increased.
        """
        if self.report.baseline_unique_spacings == 0:
            return 0.0

        return (
            (self.report.baseline_unique_spacings - self.report.current_unique_spacings)
            / self.report.baseline_unique_spacings
        ) * 100

    def calculate_clusters_resolved_this_month(self) -> int:
        """Count dedupe clusters resolved in the past 30 days.

        Compares cluster counts from snapshots within date range.

        Returns:
            Number of clusters resolved (reduction in count).
        """
        cutoff = datetime.now() - timedelta(days=30)

        # Filter snapshots to last 30 days
        recent_snapshots = [
            s for s in self.report.snapshots
            if datetime.fromisoformat(s.timestamp) > cutoff
        ]

        if len(recent_snapshots) < 2:
            return 0

        # Compare first and last snapshot in range
        first_clusters = (
            recent_snapshots[0].duplicate_clusters_found
            + recent_snapshots[0].near_duplicate_clusters_found
        )
        last_clusters = (
            recent_snapshots[-1].duplicate_clusters_found
            + recent_snapshots[-1].near_duplicate_clusters_found
        )

        resolved = first_clusters - last_clusters
        return max(0, resolved)  # Only count reductions

    def calculate_percentiles(self, tier: int) -> PerformancePercentiles:
        """Calculate p50/p95/p99 for a tier from snapshots.

        Args:
            tier: Tier number (0, 1, or 2).

        Returns:
            PerformancePercentiles for the tier.
        """
        times = [
            s.analysis_time_ms for s in self.report.snapshots if s.tier == tier
        ]

        if not times:
            return PerformancePercentiles(tier=tier)

        times_sorted = sorted(times)
        n = len(times_sorted)

        # Calculate percentile indices
        p50_idx = int(n * 0.50)
        p95_idx = min(int(n * 0.95), n - 1)
        p99_idx = min(int(n * 0.99), n - 1)

        return PerformancePercentiles(
            tier=tier,
            p50_ms=times_sorted[p50_idx],
            p95_ms=times_sorted[p95_idx],
            p99_ms=times_sorted[p99_idx],
            sample_count=n,
        )

    def get_trend_data(self, metric: str, days: int = 30) -> list[dict[str, Any]]:
        """Get trend data for charting.

        Args:
            metric: Metric name to get trend for.
            days: Number of days to include.

        Returns:
            List of {timestamp, value} dicts.
        """
        cutoff = datetime.now() - timedelta(days=days)

        # Filter snapshots
        recent = [
            s for s in self.report.snapshots
            if datetime.fromisoformat(s.timestamp) > cutoff
        ]

        # Extract metric values
        trend_data = []
        for snapshot in recent:
            value = self._get_metric_value(snapshot, metric)
            if value is not None:
                trend_data.append({
                    "timestamp": snapshot.timestamp,
                    "value": value,
                })

        return trend_data

    def _get_metric_value(self, snapshot: Any, metric: str) -> float | None:
        """Get a specific metric value from a snapshot.

        Args:
            snapshot: MetricSnapshot to extract from.
            metric: Metric name.

        Returns:
            Metric value or None if not found.
        """
        metric_map = {
            "colors": snapshot.unique_hardcoded_colors,
            "spacings": snapshot.unique_hardcoded_spacings,
            "clusters": (
                snapshot.duplicate_clusters_found
                + snapshot.near_duplicate_clusters_found
            ),
            "suppression": snapshot.suppression_rate * 100,
            "tier0_time": (
                snapshot.analysis_time_ms if snapshot.tier == 0 else None
            ),
            "tier1_time": (
                snapshot.analysis_time_ms if snapshot.tier == 1 else None
            ),
            "tier2_time": (
                snapshot.analysis_time_ms if snapshot.tier == 2 else None
            ),
            "findings": snapshot.total_findings,
            "new_findings": snapshot.new_findings,
        }

        return metric_map.get(metric)

    def get_plan_adoption_rate(self) -> float:
        """Calculate overall plan adoption rate.

        Returns:
            Adoption rate (0.0-1.0).
        """
        if not self.report.plan_records:
            return 0.0

        total_tasks = sum(p.total_tasks for p in self.report.plan_records)
        completed_tasks = sum(p.completed_tasks for p in self.report.plan_records)

        if total_tasks == 0:
            return 0.0

        return completed_tasks / total_tasks

    def is_target_met(self, target_name: str) -> bool:
        """Check if a specific target is met.

        Args:
            target_name: Name of the target to check.

        Returns:
            True if target is met, False otherwise.
        """
        targets = self.report.targets

        if target_name == "color_reduction_percent":
            return self.calculate_color_reduction() >= targets.get(target_name, 50.0)

        elif target_name == "clusters_resolved_monthly":
            return (
                self.calculate_clusters_resolved_this_month()
                >= targets.get(target_name, 10)
            )

        elif target_name == "suppression_rate_max":
            return (
                self.report.current_suppression_rate
                <= targets.get(target_name, 0.05)
            )

        elif target_name == "plan_adoption_min":
            return (
                self.get_plan_adoption_rate()
                >= targets.get(target_name, 0.70)
            )

        elif target_name == "tier_0_p95_ms":
            return self.report.tier_0_percentiles.p95_ms <= targets.get(
                target_name, 300
            )

        elif target_name == "tier_1_p95_ms":
            return self.report.tier_1_percentiles.p95_ms <= targets.get(
                target_name, 600000
            )

        elif target_name == "tier_2_p95_ms":
            return self.report.tier_2_percentiles.p95_ms <= targets.get(
                target_name, 300000
            )

        return False

    def get_all_target_status(self) -> dict[str, bool]:
        """Get status of all targets.

        Returns:
            Dict mapping target names to met status.
        """
        return {
            name: self.is_target_met(name)
            for name in self.report.targets.keys()
        }

    def generate_summary(self) -> dict[str, Any]:
        """Generate comprehensive summary for dashboard/CLI.

        Returns:
            Dict with all metrics and target statuses.
        """
        targets = self.report.targets

        return {
            "token_drift": {
                "colors": {
                    "current": self.report.current_unique_colors,
                    "baseline": self.report.baseline_unique_colors,
                    "reduction_percent": round(self.calculate_color_reduction(), 1),
                    "target": targets.get("color_reduction_percent", 50.0),
                    "on_track": self.is_target_met("color_reduction_percent"),
                },
                "spacings": {
                    "current": self.report.current_unique_spacings,
                    "baseline": self.report.baseline_unique_spacings,
                    "reduction_percent": round(self.calculate_spacing_reduction(), 1),
                },
            },
            "deduplication": {
                "current_clusters": self.report.current_duplicate_clusters,
                "resolved_this_month": self.calculate_clusters_resolved_this_month(),
                "target": targets.get("clusters_resolved_monthly", 10),
                "on_track": self.is_target_met("clusters_resolved_monthly"),
            },
            "suppression_rate": {
                "current": round(self.report.current_suppression_rate * 100, 1),
                "target_max": targets.get("suppression_rate_max", 0.05) * 100,
                "on_track": self.is_target_met("suppression_rate_max"),
            },
            "plan_adoption": {
                "current": round(self.get_plan_adoption_rate() * 100, 1),
                "target_min": targets.get("plan_adoption_min", 0.70) * 100,
                "plans_tracked": len(self.report.plan_records),
                "on_track": self.is_target_met("plan_adoption_min"),
            },
            "performance": {
                "tier_0": {
                    **self.report.tier_0_percentiles.to_dict(),
                    "target_p95_ms": targets.get("tier_0_p95_ms", 300),
                    "on_track": self.is_target_met("tier_0_p95_ms"),
                },
                "tier_1": {
                    **self.report.tier_1_percentiles.to_dict(),
                    "target_p95_ms": targets.get("tier_1_p95_ms", 600000),
                    "on_track": self.is_target_met("tier_1_p95_ms"),
                },
                "tier_2": {
                    **self.report.tier_2_percentiles.to_dict(),
                    "target_p95_ms": targets.get("tier_2_p95_ms", 300000),
                    "on_track": self.is_target_met("tier_2_p95_ms"),
                },
            },
            "snapshot_count": self.report.snapshot_count,
            "last_updated": self.report.last_updated,
        }

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics string.
        """
        lines = [
            "# HELP ui_quality_hardcoded_colors Number of unique hardcoded colors",
            "# TYPE ui_quality_hardcoded_colors gauge",
            f"ui_quality_hardcoded_colors {self.report.current_unique_colors}",
            "",
            "# HELP ui_quality_hardcoded_spacings Number of unique hardcoded spacings",
            "# TYPE ui_quality_hardcoded_spacings gauge",
            f"ui_quality_hardcoded_spacings {self.report.current_unique_spacings}",
            "",
            "# HELP ui_quality_duplicate_clusters Number of duplicate clusters",
            "# TYPE ui_quality_duplicate_clusters gauge",
            f"ui_quality_duplicate_clusters {self.report.current_duplicate_clusters}",
            "",
            "# HELP ui_quality_suppression_rate Suppression rate (0-1)",
            "# TYPE ui_quality_suppression_rate gauge",
            f"ui_quality_suppression_rate {self.report.current_suppression_rate}",
            "",
            "# HELP ui_quality_color_reduction_percent Reduction in hardcoded colors",
            "# TYPE ui_quality_color_reduction_percent gauge",
            f"ui_quality_color_reduction_percent {self.calculate_color_reduction()}",
            "",
        ]

        # Add performance percentiles per tier
        for tier_num, percentiles in [
            (0, self.report.tier_0_percentiles),
            (1, self.report.tier_1_percentiles),
            (2, self.report.tier_2_percentiles),
        ]:
            lines.extend([
                f"# HELP ui_quality_latency_p95_ms P95 latency for tier {tier_num}",
                f"# TYPE ui_quality_latency_p95_ms gauge",
                f'ui_quality_latency_p95_ms{{tier="{tier_num}"}} {percentiles.p95_ms}',
                "",
            ])

        return "\n".join(lines)

    def export_csv_header(self) -> str:
        """Generate CSV header row.

        Returns:
            CSV header string.
        """
        return (
            "timestamp,tier,colors,spacings,duplicate_clusters,"
            "suppression_rate,analysis_time_ms,files_analyzed,"
            "total_findings,new_findings"
        )

    def export_csv_rows(self, days: int = 30) -> list[str]:
        """Export snapshots as CSV rows.

        Args:
            days: Number of days to include.

        Returns:
            List of CSV row strings.
        """
        cutoff = datetime.now() - timedelta(days=days)

        rows = []
        for s in self.report.snapshots:
            if datetime.fromisoformat(s.timestamp) > cutoff:
                rows.append(
                    f"{s.timestamp},{s.tier},{s.unique_hardcoded_colors},"
                    f"{s.unique_hardcoded_spacings},"
                    f"{s.duplicate_clusters_found + s.near_duplicate_clusters_found},"
                    f"{s.suppression_rate},{s.analysis_time_ms},"
                    f"{s.files_analyzed},{s.total_findings},{s.new_findings}"
                )

        return rows


__all__ = ["MetricsAggregator"]
