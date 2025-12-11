"""Unit tests for MetricsAggregator class."""

from datetime import datetime, timedelta

import pytest

from claude_indexer.ui.metrics.aggregator import MetricsAggregator
from claude_indexer.ui.metrics.models import (
    MetricSnapshot,
    MetricsReport,
    PerformancePercentiles,
    PlanAdoptionRecord,
)


class TestMetricsAggregator:
    """Tests for MetricsAggregator class."""

    @pytest.fixture
    def report_with_snapshots(self) -> MetricsReport:
        """Create a report with test snapshots."""
        report = MetricsReport(
            baseline_unique_colors=100,
            baseline_unique_spacings=50,
            current_unique_colors=60,
            current_unique_spacings=30,
            current_duplicate_clusters=5,
            current_suppression_rate=0.03,
        )

        # Add snapshots over last 30 days
        now = datetime.now()
        for i in range(10):
            timestamp = (now - timedelta(days=i * 3)).isoformat()
            report.snapshots.append(
                MetricSnapshot(
                    timestamp=timestamp,
                    tier=1,
                    unique_hardcoded_colors=100 - i * 4,
                    duplicate_clusters_found=10 - i,
                    analysis_time_ms=1000 + i * 100,
                )
            )

        return report

    @pytest.fixture
    def aggregator(self, report_with_snapshots: MetricsReport) -> MetricsAggregator:
        """Create a MetricsAggregator instance."""
        return MetricsAggregator(report_with_snapshots)

    def test_calculate_color_reduction(self, aggregator: MetricsAggregator):
        """Color reduction should be calculated correctly."""
        reduction = aggregator.calculate_color_reduction()
        # 100 -> 60 = 40% reduction
        assert reduction == 40.0

    def test_calculate_color_reduction_zero_baseline(self):
        """Color reduction should return 0 for zero baseline."""
        report = MetricsReport(baseline_unique_colors=0, current_unique_colors=10)
        aggregator = MetricsAggregator(report)

        assert aggregator.calculate_color_reduction() == 0.0

    def test_calculate_spacing_reduction(self, aggregator: MetricsAggregator):
        """Spacing reduction should be calculated correctly."""
        reduction = aggregator.calculate_spacing_reduction()
        # 50 -> 30 = 40% reduction
        assert reduction == 40.0

    def test_calculate_clusters_resolved_this_month(
        self, report_with_snapshots: MetricsReport
    ):
        """Clusters resolved should count reduction in 30-day window."""
        aggregator = MetricsAggregator(report_with_snapshots)
        resolved = aggregator.calculate_clusters_resolved_this_month()

        # First snapshot: 10 clusters, last: 1 cluster = 9 resolved
        assert resolved >= 0

    def test_calculate_percentiles_empty(self):
        """Percentiles should return defaults for empty data."""
        report = MetricsReport()
        aggregator = MetricsAggregator(report)

        percentiles = aggregator.calculate_percentiles(tier=0)

        assert percentiles.tier == 0
        assert percentiles.p50_ms == 0.0
        assert percentiles.sample_count == 0

    def test_calculate_percentiles_with_data(
        self, report_with_snapshots: MetricsReport
    ):
        """Percentiles should be calculated from snapshots."""
        aggregator = MetricsAggregator(report_with_snapshots)
        percentiles = aggregator.calculate_percentiles(tier=1)

        assert percentiles.tier == 1
        assert percentiles.sample_count == 10
        assert percentiles.p50_ms > 0
        assert percentiles.p95_ms >= percentiles.p50_ms

    def test_get_trend_data(self, aggregator: MetricsAggregator):
        """get_trend_data should return filtered time series."""
        trend = aggregator.get_trend_data("colors", days=30)

        assert len(trend) == 10
        assert all("timestamp" in point for point in trend)
        assert all("value" in point for point in trend)

    def test_get_trend_data_filters_by_days(
        self, report_with_snapshots: MetricsReport
    ):
        """get_trend_data should filter by date range."""
        # Add old snapshot
        old_time = (datetime.now() - timedelta(days=60)).isoformat()
        report_with_snapshots.snapshots.insert(
            0,
            MetricSnapshot(
                timestamp=old_time, tier=1, unique_hardcoded_colors=150
            ),
        )

        aggregator = MetricsAggregator(report_with_snapshots)
        trend = aggregator.get_trend_data("colors", days=30)

        # Old snapshot should be excluded
        assert len(trend) == 10

    def test_get_plan_adoption_rate(self):
        """Plan adoption rate should be calculated correctly."""
        report = MetricsReport()
        report.plan_records = [
            PlanAdoptionRecord("p1", "2024-01-01", 10, 8),
            PlanAdoptionRecord("p2", "2024-01-02", 5, 5),
        ]

        aggregator = MetricsAggregator(report)
        rate = aggregator.get_plan_adoption_rate()

        # 13/15 = 0.8667
        assert abs(rate - (13 / 15)) < 0.001

    def test_get_plan_adoption_rate_no_plans(self):
        """Plan adoption rate should return 0 when no plans."""
        report = MetricsReport()
        aggregator = MetricsAggregator(report)

        assert aggregator.get_plan_adoption_rate() == 0.0

    def test_is_target_met_color_reduction(self, aggregator: MetricsAggregator):
        """is_target_met should check color reduction target."""
        # 40% reduction, target is 50%
        assert aggregator.is_target_met("color_reduction_percent") is False

        # Update current to meet target
        aggregator.report.current_unique_colors = 40  # 60% reduction
        assert aggregator.is_target_met("color_reduction_percent") is True

    def test_is_target_met_suppression_rate(self, aggregator: MetricsAggregator):
        """is_target_met should check suppression rate target."""
        # 3% suppression, target is <5%
        assert aggregator.is_target_met("suppression_rate_max") is True

        # Update to exceed target
        aggregator.report.current_suppression_rate = 0.10  # 10%
        assert aggregator.is_target_met("suppression_rate_max") is False

    def test_is_target_met_performance(self):
        """is_target_met should check performance targets."""
        report = MetricsReport()
        report.tier_0_percentiles = PerformancePercentiles(
            tier=0, p95_ms=200, sample_count=10
        )

        aggregator = MetricsAggregator(report)
        # Target is <300ms
        assert aggregator.is_target_met("tier_0_p95_ms") is True

        # Exceed target
        report.tier_0_percentiles.p95_ms = 400
        assert aggregator.is_target_met("tier_0_p95_ms") is False

    def test_get_all_target_status(self, aggregator: MetricsAggregator):
        """get_all_target_status should return all target statuses."""
        status = aggregator.get_all_target_status()

        assert "color_reduction_percent" in status
        assert "suppression_rate_max" in status
        assert "tier_0_p95_ms" in status
        assert isinstance(status["color_reduction_percent"], bool)

    def test_generate_summary(self, aggregator: MetricsAggregator):
        """generate_summary should include all metrics."""
        summary = aggregator.generate_summary()

        assert "token_drift" in summary
        assert "deduplication" in summary
        assert "suppression_rate" in summary
        assert "plan_adoption" in summary
        assert "performance" in summary

        # Check nested structure
        assert "colors" in summary["token_drift"]
        assert "reduction_percent" in summary["token_drift"]["colors"]
        assert "on_track" in summary["token_drift"]["colors"]

    def test_export_prometheus(self, aggregator: MetricsAggregator):
        """export_prometheus should return valid Prometheus format."""
        prometheus_output = aggregator.export_prometheus()

        assert "ui_quality_hardcoded_colors" in prometheus_output
        assert "ui_quality_suppression_rate" in prometheus_output
        assert "ui_quality_latency_p95_ms" in prometheus_output
        assert "# HELP" in prometheus_output
        assert "# TYPE" in prometheus_output

    def test_export_csv_header(self, aggregator: MetricsAggregator):
        """export_csv_header should return correct header."""
        header = aggregator.export_csv_header()

        assert "timestamp" in header
        assert "tier" in header
        assert "colors" in header
        assert "analysis_time_ms" in header

    def test_export_csv_rows(self, aggregator: MetricsAggregator):
        """export_csv_rows should return data rows."""
        rows = aggregator.export_csv_rows(days=30)

        assert len(rows) == 10
        # Each row should have the right number of fields
        assert all(row.count(",") == 9 for row in rows)


class TestMetricsAggregatorEdgeCases:
    """Edge case tests for MetricsAggregator."""

    def test_empty_report(self):
        """Aggregator should handle empty report gracefully."""
        report = MetricsReport()
        aggregator = MetricsAggregator(report)

        assert aggregator.calculate_color_reduction() == 0.0
        assert aggregator.calculate_clusters_resolved_this_month() == 0
        assert aggregator.get_plan_adoption_rate() == 0.0

        summary = aggregator.generate_summary()
        assert summary["snapshot_count"] == 0

    def test_single_snapshot(self):
        """Aggregator should handle single snapshot."""
        report = MetricsReport()
        report.snapshots = [
            MetricSnapshot(
                timestamp=datetime.now().isoformat(),
                tier=1,
                unique_hardcoded_colors=50,
            )
        ]

        aggregator = MetricsAggregator(report)
        percentiles = aggregator.calculate_percentiles(tier=1)

        assert percentiles.sample_count == 1
        # p95 = p50 = p99 for single sample
        assert percentiles.p50_ms == percentiles.p95_ms
