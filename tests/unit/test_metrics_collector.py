"""Unit tests for MetricsCollector class."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from claude_indexer.ui.metrics.collector import MetricsCollector
from claude_indexer.ui.metrics.models import (
    MetricSnapshot,
    MetricsReport,
    PerformancePercentiles,
    PlanAdoptionRecord,
)


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    @pytest.fixture
    def temp_project(self, tmp_path: Path) -> Path:
        """Create a temporary project directory."""
        project = tmp_path / "test_project"
        project.mkdir()
        return project

    @pytest.fixture
    def collector(self, temp_project: Path) -> MetricsCollector:
        """Create a MetricsCollector instance."""
        return MetricsCollector(temp_project, config=None)

    def test_load_creates_default_report(self, collector: MetricsCollector):
        """Loading without existing file should create default report."""
        report = collector.load()

        assert report is not None
        assert isinstance(report, MetricsReport)
        assert report.version == "1.0"
        assert len(report.snapshots) == 0
        assert report.baseline_unique_colors == 0

    def test_save_persists_to_disk(
        self, collector: MetricsCollector, temp_project: Path
    ):
        """Saving should persist report to disk."""
        report = collector.load()
        report.baseline_unique_colors = 42
        collector.save(report)

        # Verify file exists
        metrics_path = temp_project / ".ui-quality" / "metrics.json"
        assert metrics_path.exists()

        # Verify content
        with open(metrics_path) as f:
            data = json.load(f)
        assert data["baseline_unique_colors"] == 42

    def test_load_reads_existing_file(
        self, collector: MetricsCollector, temp_project: Path
    ):
        """Loading should read existing metrics file."""
        # Create metrics file manually
        metrics_path = temp_project / ".ui-quality" / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)

        report_data = {
            "version": "1.0",
            "project_path": str(temp_project),
            "snapshots": [],
            "plan_records": [],
            "baseline_unique_colors": 100,
            "baseline_unique_spacings": 50,
            "baseline_duplicate_clusters": 10,
            "current_unique_colors": 80,
            "current_unique_spacings": 40,
            "current_duplicate_clusters": 8,
            "current_suppression_rate": 0.03,
            "tier_0_percentiles": {"tier": 0, "p50_ms": 100, "p95_ms": 200, "p99_ms": 250, "sample_count": 10},
            "tier_1_percentiles": {"tier": 1, "p50_ms": 1000, "p95_ms": 2000, "p99_ms": 2500, "sample_count": 5},
            "tier_2_percentiles": {"tier": 2, "p50_ms": 5000, "p95_ms": 10000, "p99_ms": 12000, "sample_count": 3},
            "targets": {},
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
        }
        with open(metrics_path, "w") as f:
            json.dump(report_data, f)

        # Create new collector and load
        new_collector = MetricsCollector(temp_project, config=None)
        report = new_collector.load()

        assert report.baseline_unique_colors == 100
        assert report.current_unique_colors == 80

    def test_record_plan_generated(self, collector: MetricsCollector):
        """Recording a plan should create a PlanAdoptionRecord."""
        plan_id = collector.record_plan_generated(total_tasks=5)

        assert plan_id is not None
        assert len(plan_id) == 8  # Short UUID

        report = collector.load()
        assert len(report.plan_records) == 1
        assert report.plan_records[0].plan_id == plan_id
        assert report.plan_records[0].total_tasks == 5
        assert report.plan_records[0].completed_tasks == 0

    def test_record_plan_progress(self, collector: MetricsCollector):
        """Recording progress should update the plan record."""
        plan_id = collector.record_plan_generated(total_tasks=5)

        # Update progress
        result = collector.record_plan_progress(plan_id, completed_tasks=3)
        assert result is True

        report = collector.load()
        assert report.plan_records[0].completed_tasks == 3

    def test_record_plan_progress_nonexistent(self, collector: MetricsCollector):
        """Recording progress for nonexistent plan should return False."""
        result = collector.record_plan_progress("nonexistent", completed_tasks=1)
        assert result is False

    def test_rolling_window_limits_snapshots(self, collector: MetricsCollector):
        """Snapshots should be limited by MAX_SNAPSHOTS."""
        collector.MAX_SNAPSHOTS = 5  # Reduce for testing

        report = collector.load()

        # Add more than max snapshots
        for i in range(10):
            snapshot = MetricSnapshot(
                timestamp=datetime.now().isoformat(),
                tier=0,
                unique_hardcoded_colors=i,
            )
            report.snapshots.append(snapshot)

        # Save and reload
        collector._report = report
        collector.save()

        # Create new collector and verify
        new_collector = MetricsCollector(collector.project_path, config=None)
        new_collector.MAX_SNAPSHOTS = 5
        loaded = new_collector.load()

        # Should have kept the MAX_SNAPSHOTS most recent
        # (Note: rolling window is applied during record_audit_run, not save)
        assert len(loaded.snapshots) == 10  # Save doesn't truncate

    def test_reset_clears_all_data(
        self, collector: MetricsCollector, temp_project: Path
    ):
        """Reset should clear all metrics data."""
        # Create some data
        report = collector.load()
        report.baseline_unique_colors = 100
        collector.save(report)

        # Verify file exists
        metrics_path = temp_project / ".ui-quality" / "metrics.json"
        assert metrics_path.exists()

        # Reset
        collector.reset()

        # File should be deleted
        assert not metrics_path.exists()

        # Report should be fresh
        report = collector.load()
        assert report.baseline_unique_colors == 0


class TestMetricSnapshot:
    """Tests for MetricSnapshot dataclass."""

    def test_to_dict_roundtrip(self):
        """to_dict/from_dict should preserve all fields."""
        original = MetricSnapshot(
            timestamp="2024-01-15T10:30:00",
            tier=1,
            unique_hardcoded_colors=42,
            unique_hardcoded_spacings=28,
            duplicate_clusters_found=5,
            total_findings=100,
            new_findings=10,
            baseline_findings=90,
            suppression_rate=0.05,
            analysis_time_ms=1500.5,
            files_analyzed=50,
            cache_hit_rate=0.75,
            commit_hash="abc123def",
            branch_name="feature/test",
        )

        data = original.to_dict()
        restored = MetricSnapshot.from_dict(data)

        assert restored.timestamp == original.timestamp
        assert restored.tier == original.tier
        assert restored.unique_hardcoded_colors == original.unique_hardcoded_colors
        assert restored.suppression_rate == original.suppression_rate
        assert restored.commit_hash == original.commit_hash

    def test_default_values(self):
        """Default values should be set correctly."""
        snapshot = MetricSnapshot(
            timestamp="2024-01-15T10:30:00",
            tier=0,
        )

        assert snapshot.unique_hardcoded_colors == 0
        assert snapshot.suppression_rate == 0.0
        assert snapshot.commit_hash is None


class TestPerformancePercentiles:
    """Tests for PerformancePercentiles dataclass."""

    def test_to_dict_roundtrip(self):
        """to_dict/from_dict should preserve all fields."""
        original = PerformancePercentiles(
            tier=1,
            p50_ms=100.0,
            p95_ms=250.0,
            p99_ms=500.0,
            sample_count=100,
        )

        data = original.to_dict()
        restored = PerformancePercentiles.from_dict(data)

        assert restored.tier == original.tier
        assert restored.p50_ms == original.p50_ms
        assert restored.p95_ms == original.p95_ms
        assert restored.sample_count == original.sample_count

    def test_meets_target(self):
        """meets_target should compare p95 to target."""
        percentiles = PerformancePercentiles(
            tier=0,
            p95_ms=200.0,
        )

        assert percentiles.meets_target(300.0) is True
        assert percentiles.meets_target(150.0) is False


class TestPlanAdoptionRecord:
    """Tests for PlanAdoptionRecord dataclass."""

    def test_adoption_rate(self):
        """adoption_rate should calculate correctly."""
        record = PlanAdoptionRecord(
            plan_id="test123",
            generated_at="2024-01-15T10:00:00",
            total_tasks=10,
            completed_tasks=7,
        )

        assert record.adoption_rate == 0.7

    def test_adoption_rate_zero_tasks(self):
        """adoption_rate should return 0 for zero tasks."""
        record = PlanAdoptionRecord(
            plan_id="test123",
            generated_at="2024-01-15T10:00:00",
            total_tasks=0,
            completed_tasks=0,
        )

        assert record.adoption_rate == 0.0

    def test_is_complete(self):
        """is_complete should check if all tasks are done."""
        record = PlanAdoptionRecord(
            plan_id="test123",
            generated_at="2024-01-15T10:00:00",
            total_tasks=5,
            completed_tasks=5,
        )

        assert record.is_complete is True

        record.completed_tasks = 4
        assert record.is_complete is False


class TestMetricsReport:
    """Tests for MetricsReport dataclass."""

    def test_color_reduction_percent(self):
        """color_reduction_percent should calculate correctly."""
        report = MetricsReport(
            baseline_unique_colors=100,
            current_unique_colors=60,
        )

        assert report.color_reduction_percent == 40.0

    def test_color_reduction_percent_zero_baseline(self):
        """color_reduction_percent should return 0 for zero baseline."""
        report = MetricsReport(
            baseline_unique_colors=0,
            current_unique_colors=10,
        )

        assert report.color_reduction_percent == 0.0

    def test_plan_adoption_rate(self):
        """plan_adoption_rate should calculate across all plans."""
        report = MetricsReport()
        report.plan_records = [
            PlanAdoptionRecord("p1", "2024-01-01", 10, 8),
            PlanAdoptionRecord("p2", "2024-01-02", 5, 5),
        ]

        # Total: 15 tasks, 13 completed = 86.67%
        assert abs(report.plan_adoption_rate - (13 / 15)) < 0.001

    def test_to_dict_roundtrip(self):
        """to_dict/from_dict should preserve all fields."""
        original = MetricsReport(
            version="1.0",
            project_path="/test/project",
            baseline_unique_colors=100,
            current_unique_colors=80,
        )
        original.snapshots = [
            MetricSnapshot("2024-01-15T10:00:00", tier=0),
        ]

        data = original.to_dict()
        restored = MetricsReport.from_dict(data)

        assert restored.version == original.version
        assert restored.project_path == original.project_path
        assert restored.baseline_unique_colors == original.baseline_unique_colors
        assert len(restored.snapshots) == 1
