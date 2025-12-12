"""Tests for the PerformanceMetricsCollector."""

import time
from unittest.mock import patch

import pytest

from claude_indexer.performance.metrics import (
    MetricWindow,
    PerformanceMetricsCollector,
    get_all_stats,
    get_stats,
    measure,
    record,
)


class TestMetricWindow:
    """Tests for MetricWindow dataclass."""

    def test_add_value(self):
        """Test adding values to window."""
        window = MetricWindow()
        window.add(100.0)
        window.add(200.0)

        values = window.get_values_in_window()
        assert len(values) == 2
        assert 100.0 in values
        assert 200.0 in values

    def test_max_samples_limit(self):
        """Test that max_samples is respected."""
        window = MetricWindow()
        window.values = window.values.__class__(maxlen=10)

        for i in range(20):
            window.add(float(i))

        assert len(window.values) == 10

    def test_window_expiration(self):
        """Test that values outside window are excluded."""
        window = MetricWindow(window_seconds=1)

        # Add a value
        window.add(100.0)

        # Should be in window
        values = window.get_values_in_window()
        assert len(values) == 1

        # After window expires, should be excluded
        with patch("time.time", return_value=time.time() + 2):
            values = window.get_values_in_window()
            assert len(values) == 0


class TestPerformanceMetricsCollector:
    """Tests for PerformanceMetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Get a fresh collector instance."""
        # Since it's a singleton, clear it first
        c = PerformanceMetricsCollector()
        c.clear()
        return c

    def test_singleton(self):
        """Test that collector is a singleton."""
        c1 = PerformanceMetricsCollector()
        c2 = PerformanceMetricsCollector()
        assert c1 is c2

    def test_record_and_get_stats(self, collector):
        """Test recording metrics and getting stats."""
        collector.record("test_op", 100.0)
        collector.record("test_op", 200.0)
        collector.record("test_op", 300.0)

        stats = collector.get_stats("test_op")

        assert stats["count"] == 3
        assert stats["avg_ms"] == 200.0
        assert stats["min_ms"] == 100.0
        assert stats["max_ms"] == 300.0

    def test_percentiles(self, collector):
        """Test percentile calculations."""
        # Add 100 values: 1, 2, 3, ..., 100
        for i in range(1, 101):
            collector.record("perc_test", float(i))

        stats = collector.get_stats("perc_test")

        assert stats["count"] == 100
        assert stats["p50_ms"] == pytest.approx(50.5, rel=0.1)
        assert stats["p95_ms"] == pytest.approx(95.05, rel=0.1)
        assert stats["p99_ms"] == pytest.approx(99.01, rel=0.1)

    def test_measure_context_manager(self, collector):
        """Test measure() context manager."""
        with collector.measure("measured_op"):
            time.sleep(0.01)

        stats = collector.get_stats("measured_op")
        assert stats["count"] == 1
        assert stats["avg_ms"] >= 10

    def test_get_all_stats(self, collector):
        """Test get_all_stats returns all operations."""
        collector.record("op1", 100.0)
        collector.record("op2", 200.0)

        all_stats = collector.get_all_stats()

        assert "op1" in all_stats
        assert "op2" in all_stats
        assert all_stats["op1"]["avg_ms"] == 100.0
        assert all_stats["op2"]["avg_ms"] == 200.0

    def test_get_operations(self, collector):
        """Test get_operations returns list of tracked ops."""
        collector.record("op_a", 100.0)
        collector.record("op_b", 100.0)

        ops = collector.get_operations()
        assert "op_a" in ops
        assert "op_b" in ops

    def test_clear_specific_operation(self, collector):
        """Test clearing specific operation."""
        collector.record("keep", 100.0)
        collector.record("remove", 200.0)

        collector.clear("remove")

        assert "keep" in collector.get_operations()
        assert "remove" not in collector.get_operations()

    def test_clear_all(self, collector):
        """Test clearing all metrics."""
        collector.record("op1", 100.0)
        collector.record("op2", 200.0)

        collector.clear()

        assert len(collector.get_operations()) == 0

    def test_set_window(self, collector):
        """Test setting custom window for operation."""
        collector.set_window("custom_window", 60)  # 60 second window

        # This should use the custom window
        collector.record("custom_window", 100.0)

        stats = collector.get_stats("custom_window")
        assert stats["count"] == 1

    def test_export(self, collector):
        """Test export functionality."""
        collector.record("export_test", 100.0)

        export = collector.export()

        assert "timestamp" in export
        assert "metrics" in export
        assert "export_test" in export["metrics"]

    def test_empty_stats(self, collector):
        """Test stats for non-existent operation."""
        stats = collector.get_stats("nonexistent")
        assert stats == {}


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture(autouse=True)
    def clear_collector(self):
        """Clear collector before each test."""
        c = PerformanceMetricsCollector()
        c.clear()
        yield
        c.clear()

    def test_record_function(self):
        """Test record() module function."""
        record("func_test", 100.0)

        stats = get_stats("func_test")
        assert stats["count"] == 1

    def test_measure_function(self):
        """Test measure() module function."""
        with measure("measure_test"):
            time.sleep(0.005)

        stats = get_stats("measure_test")
        assert stats["count"] == 1
        assert stats["avg_ms"] >= 5

    def test_get_all_stats_function(self):
        """Test get_all_stats() module function."""
        record("op1", 100.0)
        record("op2", 200.0)

        all_stats = get_all_stats()
        assert "op1" in all_stats
        assert "op2" in all_stats
