"""Unit tests for BatchOptimizer."""

from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.indexing.batch_optimizer import BatchOptimizer
from claude_indexer.indexing.types import BatchMetrics


class TestBatchOptimizer:
    """Tests for BatchOptimizer class."""

    def test_initial_batch_size(self):
        """Test initial batch size is respected."""
        optimizer = BatchOptimizer(initial_size=30, max_size=100)
        assert optimizer.get_batch_size() == 30

    def test_current_size_property(self):
        """Test current_size property."""
        optimizer = BatchOptimizer(initial_size=25)
        assert optimizer.current_size == 25

    @patch("claude_indexer.indexing.batch_optimizer.psutil")
    def test_get_batch_size_reduces_on_memory_pressure(self, mock_psutil):
        """Test batch size reduction when memory exceeds threshold."""
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 2500 * 1024 * 1024  # 2500 MB
        mock_psutil.Process.return_value = mock_process

        optimizer = BatchOptimizer(
            initial_size=50,
            max_size=100,
            memory_threshold_mb=2000,
        )

        # First call should detect memory pressure and reduce
        size = optimizer.get_batch_size()
        assert size < 50  # Should be reduced

    def test_record_batch_success_increases_counter(self):
        """Test successful batch increases consecutive success counter."""
        optimizer = BatchOptimizer(initial_size=25)

        metrics = BatchMetrics(
            batch_size=25,
            processing_time_ms=1000.0,
            memory_delta_mb=50.0,
            error_count=0,
        )

        optimizer.record_batch(metrics)
        assert optimizer._consecutive_successes == 1

    def test_record_batch_errors_resets_success_counter(self):
        """Test batch with errors resets success counter."""
        optimizer = BatchOptimizer(initial_size=25)
        optimizer._consecutive_successes = 2

        # Batch with 30% error rate (above 10% threshold)
        metrics = BatchMetrics(
            batch_size=10,
            processing_time_ms=1000.0,
            memory_delta_mb=50.0,
            error_count=3,  # 30% error rate
        )

        optimizer.record_batch(metrics)
        assert optimizer._consecutive_successes == 0
        assert optimizer._consecutive_failures == 1

    def test_ramp_up_after_consecutive_successes(self):
        """Test batch size increases after consecutive successes."""
        optimizer = BatchOptimizer(initial_size=25, max_size=100)

        # Record 3 successful batches (threshold for ramp up)
        for _ in range(3):
            metrics = BatchMetrics(
                batch_size=25,
                processing_time_ms=1000.0,
                memory_delta_mb=50.0,
                error_count=0,
            )
            optimizer.record_batch(metrics)

        # Should have ramped up (25 * 1.5 = 37.5 -> 37)
        assert optimizer.current_size > 25

    def test_never_exceeds_max_size(self):
        """Test batch size never exceeds maximum."""
        optimizer = BatchOptimizer(initial_size=90, max_size=100)

        # Try to ramp up beyond max
        for _ in range(10):
            metrics = BatchMetrics(
                batch_size=100,
                processing_time_ms=1000.0,
                memory_delta_mb=50.0,
                error_count=0,
            )
            optimizer.record_batch(metrics)

        assert optimizer.current_size <= 100

    def test_never_goes_below_min_size(self):
        """Test batch size never goes below minimum."""
        optimizer = BatchOptimizer(initial_size=10, max_size=100)

        # Force multiple reductions
        for _ in range(10):
            optimizer.force_reduce("test reduction")

        assert optimizer.current_size >= 2  # Default min

    def test_force_reduce(self):
        """Test force_reduce immediately reduces batch size."""
        optimizer = BatchOptimizer(initial_size=50)
        old_size = optimizer.current_size

        new_size = optimizer.force_reduce("test reason")

        assert new_size < old_size
        assert "test reason" in optimizer._reduction_reasons

    @patch("claude_indexer.indexing.batch_optimizer.psutil")
    def test_check_memory(self, mock_psutil):
        """Test memory checking."""
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 1500 * 1024 * 1024  # 1500 MB
        mock_psutil.Process.return_value = mock_process

        optimizer = BatchOptimizer(memory_threshold_mb=2000)
        current_mb, should_reduce = optimizer.check_memory()

        assert current_mb == pytest.approx(1500.0, rel=0.01)
        assert should_reduce is False

    @patch("claude_indexer.indexing.batch_optimizer.psutil")
    def test_check_memory_exceeds_threshold(self, mock_psutil):
        """Test memory check when exceeding threshold."""
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 2500 * 1024 * 1024  # 2500 MB
        mock_psutil.Process.return_value = mock_process

        optimizer = BatchOptimizer(memory_threshold_mb=2000)
        current_mb, should_reduce = optimizer.check_memory()

        assert current_mb == pytest.approx(2500.0, rel=0.01)
        assert should_reduce is True

    def test_reset(self):
        """Test optimizer reset to initial state."""
        optimizer = BatchOptimizer(initial_size=25)

        # Make some changes
        optimizer._current_size = 50
        optimizer._consecutive_successes = 5
        optimizer._reduction_reasons = ["reason1", "reason2"]

        optimizer.reset()

        assert optimizer.current_size == 25
        assert optimizer._consecutive_successes == 0
        assert optimizer._reduction_reasons == []

    def test_get_statistics(self):
        """Test statistics retrieval."""
        optimizer = BatchOptimizer(initial_size=25, max_size=100)

        # Record some batches
        for _ in range(3):
            metrics = BatchMetrics(
                batch_size=25,
                processing_time_ms=1000.0,
                memory_delta_mb=50.0,
                error_count=0,
            )
            optimizer.record_batch(metrics)

        stats = optimizer.get_statistics()

        assert stats["initial_size"] == 25
        assert stats["batches_processed"] == 3
        assert stats["total_files_processed"] == 75
        assert stats["total_errors"] == 0

    def test_get_statistics_empty(self):
        """Test statistics with no batches processed."""
        optimizer = BatchOptimizer(initial_size=25)
        stats = optimizer.get_statistics()

        assert stats["batches_processed"] == 0
        assert stats["avg_processing_time_ms"] == 0.0

    def test_can_increase_property(self):
        """Test can_increase property."""
        optimizer = BatchOptimizer(initial_size=50, max_size=100)
        assert optimizer.can_increase is True

        optimizer._current_size = 100
        assert optimizer.can_increase is False

    def test_at_minimum_property(self):
        """Test at_minimum property."""
        optimizer = BatchOptimizer(initial_size=50)
        assert optimizer.at_minimum is False

        optimizer._current_size = 2
        assert optimizer.at_minimum is True

    def test_consecutive_failures_reduce_size(self):
        """Test consecutive failures reduce batch size."""
        optimizer = BatchOptimizer(initial_size=50)

        # Record 2 consecutive failed batches (high error rate)
        for _ in range(2):
            metrics = BatchMetrics(
                batch_size=10,
                processing_time_ms=1000.0,
                memory_delta_mb=50.0,
                error_count=5,  # 50% error rate
            )
            optimizer.record_batch(metrics)

        # Size should have been reduced
        assert optimizer.current_size < 50
