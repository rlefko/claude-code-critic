"""Unit tests for PipelineProgress."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.indexing.progress import PipelineProgress


class TestPipelineProgress:
    """Tests for PipelineProgress class."""

    @pytest.fixture
    def progress(self):
        """Create a progress instance with terminal disabled."""
        return PipelineProgress(enable_terminal=False)

    def test_init_default(self):
        """Test default initialization."""
        p = PipelineProgress(enable_terminal=False)
        state = p.get_state()
        assert state.phase == "init"
        assert state.total_files == 0
        assert state.processed_files == 0

    def test_start_initializes_state(self, progress):
        """Test start initializes progress state."""
        progress.start(total_files=100, total_batches=4)

        state = progress.get_state()
        assert state.total_files == 100
        assert state.total_batches == 4
        assert state.phase == "discovery"

    def test_start_with_callback(self, progress):
        """Test start with callback registration."""
        callback = MagicMock()
        progress.start(total_files=100, total_batches=4, callback=callback)

        # Callback should be called on start
        assert callback.called

    def test_set_phase(self, progress):
        """Test phase update."""
        progress.start(total_files=100, total_batches=4)
        progress.set_phase("parsing")

        assert progress.get_state().phase == "parsing"

    def test_update_discovery(self, progress):
        """Test discovery phase update."""
        progress.start(total_files=100, total_batches=4)
        progress.update_discovery(files_found=100, files_filtered=30)

        state = progress.get_state()
        assert state.cache_hits == 30
        assert state.cache_misses == 70
        assert state.phase == "filtering"

    def test_update_batch(self, progress):
        """Test batch update."""
        progress.start(total_files=100, total_batches=4)
        progress.update_batch(
            batch_index=0,
            files_in_batch=25,
            tier_stats={"light": 5, "standard": 15, "deep": 5},
        )

        state = progress.get_state()
        assert state.current_batch == 1  # 1-indexed for display
        assert state.phase == "parsing"

    def test_update_file(self, progress):
        """Test file-level update."""
        progress.start(total_files=100, total_batches=4)
        progress.update_file(Path("/test/file.py"), status="processing")

        state = progress.get_state()
        assert state.current_file == "file.py"

    def test_update_file_complete(self, progress):
        """Test completing a file."""
        progress.start(total_files=100, total_batches=4)
        progress.update_file(Path("/test/file.py"), status="complete")

        state = progress.get_state()
        assert state.processed_files == 1

    def test_complete_batch(self, progress):
        """Test batch completion."""
        progress.start(total_files=100, total_batches=4)
        progress.complete_batch(
            batch_index=0,
            entities=50,
            relations=20,
            chunks=30,
            parse_time_ms=500.0,
            embed_time_ms=200.0,
            store_time_ms=100.0,
            files_processed=25,
        )

        state = progress.get_state()
        assert state.entities_created == 50
        assert state.relations_created == 20
        assert state.chunks_created == 30
        assert state.parse_time_ms == 500.0
        assert state.embed_time_ms == 200.0
        assert state.store_time_ms == 100.0
        assert state.processed_files == 25

    def test_increment_files(self, progress):
        """Test incrementing file count."""
        progress.start(total_files=100, total_batches=4)
        progress.increment_files(count=5)

        assert progress.get_state().processed_files == 5

    def test_increment_files_failed(self, progress):
        """Test incrementing failed files."""
        progress.start(total_files=100, total_batches=4)
        progress.increment_files(count=5, failed=True)

        # Failed files shouldn't increment processed count
        assert progress.get_state().processed_files == 0

    def test_finish_success(self, progress):
        """Test successful finish."""
        progress.start(total_files=100, total_batches=4)
        progress._state.processed_files = 100

        final_state = progress.finish(success=True)

        assert final_state.phase == "complete"
        assert final_state.eta_seconds == 0.0

    def test_finish_failure(self, progress):
        """Test failure finish."""
        progress.start(total_files=100, total_batches=4)

        final_state = progress.finish(success=False)

        assert final_state.phase == "complete"

    def test_get_state_returns_copy(self, progress):
        """Test get_state returns a copy."""
        progress.start(total_files=100, total_batches=4)

        state1 = progress.get_state()
        state1.processed_files = 999

        state2 = progress.get_state()
        assert state2.processed_files == 0  # Original unchanged

    def test_get_performance_report(self, progress):
        """Test performance report generation."""
        progress.start(total_files=100, total_batches=4)
        progress.complete_batch(
            batch_index=0,
            entities=50,
            relations=20,
            chunks=30,
            parse_time_ms=500.0,
            embed_time_ms=200.0,
            store_time_ms=100.0,
        )

        report = progress.get_performance_report()

        assert "total_time_seconds" in report
        assert "entities_created" in report
        assert report["entities_created"] == 50
        assert "timing" in report
        assert report["timing"]["parse_ms"] == 500.0

    def test_add_callback(self, progress):
        """Test adding callback."""
        callback = MagicMock()
        progress.add_callback(callback)
        progress.start(total_files=100, total_batches=4)

        # Callback should be called
        assert callback.called

    def test_remove_callback(self, progress):
        """Test removing callback."""
        callback = MagicMock()
        progress.add_callback(callback)
        progress.remove_callback(callback)
        progress.start(total_files=100, total_batches=4)

        # Callback should not be called after removal
        # (it was added and removed before start)
        # Actually the implementation calls notify on start,
        # so we need to verify it's removed
        assert callback not in progress._callbacks

    def test_callbacks_invoked_on_updates(self, progress):
        """Test callbacks are invoked on various updates."""
        callback = MagicMock()
        progress.start(total_files=100, total_batches=4, callback=callback)

        initial_call_count = callback.call_count

        progress.set_phase("parsing")
        assert callback.call_count > initial_call_count

    def test_callback_exception_handled(self, progress):
        """Test callback exceptions are handled gracefully."""

        def bad_callback(state):
            raise ValueError("Test error")

        progress.add_callback(bad_callback)

        # Should not raise
        progress.start(total_files=100, total_batches=4)
        progress.set_phase("parsing")

    @patch("claude_indexer.indexing.progress.psutil")
    def test_memory_tracking(self, mock_psutil, progress):
        """Test memory tracking integration."""
        mock_process = MagicMock()
        mock_process.memory_info.return_value.rss = 500 * 1024 * 1024  # 500 MB
        mock_psutil.Process.return_value = mock_process

        progress.start(total_files=100, total_batches=4)

        state = progress.get_state()
        assert state.memory_mb == pytest.approx(500.0, rel=0.01)

    def test_eta_calculation(self, progress):
        """Test ETA calculation after processing files."""
        progress.start(total_files=100, total_batches=4)

        # Simulate some progress
        progress._state.processed_files = 50
        progress._start_time = progress._start_time - 10  # Pretend 10s elapsed

        progress._update_speed_eta()

        assert progress._state.files_per_second == pytest.approx(5.0, rel=0.1)
        assert progress._state.eta_seconds == pytest.approx(10.0, rel=0.1)

    def test_cumulative_batch_metrics(self, progress):
        """Test metrics accumulate across batches."""
        progress.start(total_files=100, total_batches=4)

        progress.complete_batch(
            batch_index=0,
            entities=25,
            relations=10,
            chunks=15,
            parse_time_ms=100.0,
            embed_time_ms=50.0,
            store_time_ms=25.0,
        )

        progress.complete_batch(
            batch_index=1,
            entities=30,
            relations=15,
            chunks=20,
            parse_time_ms=120.0,
            embed_time_ms=60.0,
            store_time_ms=30.0,
        )

        state = progress.get_state()
        assert state.entities_created == 55  # 25 + 30
        assert state.relations_created == 25  # 10 + 15
        assert state.chunks_created == 35  # 15 + 20
        assert state.parse_time_ms == 220.0  # 100 + 120
