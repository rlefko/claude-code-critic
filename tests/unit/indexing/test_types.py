"""Unit tests for indexing pipeline type definitions."""

from datetime import UTC, datetime

from claude_indexer.indexing.types import (
    BatchMetrics,
    BatchResult,
    CheckpointState,
    IndexingPhase,
    PipelineConfig,
    PipelineResult,
    ProgressState,
    ThresholdConfig,
)


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = PipelineConfig()
        assert config.initial_batch_size == 25
        assert config.max_batch_size == 100
        assert config.ramp_up_enabled is True
        assert config.memory_threshold_mb == 2000
        assert config.parallel_threshold == 100
        assert config.checkpoint_interval == 50
        assert config.enable_resume is True
        assert config.max_parallel_workers == 0

    def test_custom_values(self):
        """Test custom configuration values."""
        config = PipelineConfig(
            initial_batch_size=10,
            max_batch_size=50,
            ramp_up_enabled=False,
            memory_threshold_mb=1000,
        )
        assert config.initial_batch_size == 10
        assert config.max_batch_size == 50
        assert config.ramp_up_enabled is False
        assert config.memory_threshold_mb == 1000


class TestBatchResult:
    """Tests for BatchResult dataclass."""

    def test_default_values(self):
        """Test default batch result values."""
        result = BatchResult(batch_index=0)
        assert result.batch_index == 0
        assert result.files_processed == 0
        assert result.files_failed == 0
        assert result.entities_created == 0
        assert result.errors == []
        assert result.processed_files == []

    def test_total_time_ms(self):
        """Test total time calculation."""
        result = BatchResult(
            batch_index=0,
            parse_time_ms=100.0,
            embed_time_ms=50.0,
            store_time_ms=25.0,
        )
        assert result.total_time_ms == 175.0

    def test_success_rate(self):
        """Test success rate calculation."""
        result = BatchResult(
            batch_index=0,
            files_processed=8,
            files_failed=2,
        )
        assert result.success_rate == 0.8

    def test_success_rate_zero_files(self):
        """Test success rate with zero files."""
        result = BatchResult(batch_index=0)
        assert result.success_rate == 0.0


class TestPipelineResult:
    """Tests for PipelineResult dataclass."""

    def test_default_values(self):
        """Test default pipeline result values."""
        result = PipelineResult(success=True)
        assert result.success is True
        assert result.files_processed == 0
        assert result.files_skipped == 0
        assert result.files_failed == 0
        assert result.errors == []
        assert result.warnings == []

    def test_total_files(self):
        """Test total files calculation."""
        result = PipelineResult(
            success=True,
            files_processed=10,
            files_skipped=5,
            files_failed=2,
        )
        assert result.total_files == 17

    def test_files_per_second(self):
        """Test files per second calculation."""
        result = PipelineResult(
            success=True,
            files_processed=100,
            total_time_seconds=10.0,
        )
        assert result.files_per_second == 10.0

    def test_files_per_second_zero_time(self):
        """Test files per second with zero time."""
        result = PipelineResult(success=True, files_processed=100)
        assert result.files_per_second == 0.0


class TestProgressState:
    """Tests for ProgressState dataclass."""

    def test_percent_complete(self):
        """Test percentage completion calculation."""
        state = ProgressState(
            phase="parsing",
            total_files=100,
            processed_files=25,
            current_batch=1,
            total_batches=4,
            files_per_second=5.0,
            eta_seconds=15.0,
            memory_mb=500.0,
        )
        assert state.percent_complete == 25.0

    def test_percent_complete_zero_files(self):
        """Test percentage with zero total files."""
        state = ProgressState(
            phase="init",
            total_files=0,
            processed_files=0,
            current_batch=0,
            total_batches=0,
            files_per_second=0.0,
            eta_seconds=0.0,
            memory_mb=0.0,
        )
        assert state.percent_complete == 0.0

    def test_eta_formatted_seconds(self):
        """Test ETA formatting for seconds."""
        state = ProgressState(
            phase="parsing",
            total_files=100,
            processed_files=50,
            current_batch=2,
            total_batches=4,
            files_per_second=5.0,
            eta_seconds=45.0,
            memory_mb=500.0,
        )
        assert state.eta_formatted == "45s"

    def test_eta_formatted_minutes(self):
        """Test ETA formatting for minutes."""
        state = ProgressState(
            phase="parsing",
            total_files=100,
            processed_files=50,
            current_batch=2,
            total_batches=4,
            files_per_second=5.0,
            eta_seconds=125.0,
            memory_mb=500.0,
        )
        assert state.eta_formatted == "2m 5s"

    def test_eta_formatted_hours(self):
        """Test ETA formatting for hours."""
        state = ProgressState(
            phase="parsing",
            total_files=1000,
            processed_files=50,
            current_batch=1,
            total_batches=40,
            files_per_second=1.0,
            eta_seconds=3725.0,
            memory_mb=500.0,
        )
        assert state.eta_formatted == "1h 2m"

    def test_eta_formatted_calculating(self):
        """Test ETA formatting when calculating."""
        state = ProgressState(
            phase="init",
            total_files=100,
            processed_files=0,
            current_batch=0,
            total_batches=4,
            files_per_second=0.0,
            eta_seconds=0.0,
            memory_mb=500.0,
        )
        assert state.eta_formatted == "calculating..."


class TestBatchMetrics:
    """Tests for BatchMetrics dataclass."""

    def test_auto_calculate_files_per_second(self):
        """Test automatic files_per_second calculation."""
        metrics = BatchMetrics(
            batch_size=25,
            processing_time_ms=5000.0,
            memory_delta_mb=50.0,
            error_count=0,
        )
        assert metrics.files_per_second == 5.0

    def test_explicit_files_per_second(self):
        """Test explicit files_per_second value."""
        metrics = BatchMetrics(
            batch_size=25,
            processing_time_ms=5000.0,
            memory_delta_mb=50.0,
            error_count=0,
            files_per_second=10.0,
        )
        assert metrics.files_per_second == 10.0


class TestThresholdConfig:
    """Tests for ThresholdConfig dataclass."""

    def test_default_values(self):
        """Test default threshold values."""
        config = ThresholdConfig()
        assert config.min_batch_size == 2
        assert config.max_batch_size == 100
        assert config.memory_threshold_mb == 2000
        assert config.error_rate_threshold == 0.1
        assert config.ramp_up_factor == 1.5
        assert config.ramp_down_factor == 0.5
        assert config.consecutive_successes_for_ramp == 3


class TestCheckpointState:
    """Tests for CheckpointState dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(UTC).isoformat()
        state = CheckpointState(
            collection_name="test-collection",
            project_path="/path/to/project",
            total_files=100,
            processed_files=["a.py", "b.py"],
            pending_files=["c.py"],
            failed_files=[],
            last_batch_index=1,
            entities_created=50,
            relations_created=20,
            chunks_created=30,
            started_at=now,
            updated_at=now,
        )
        d = state.to_dict()
        assert d["collection_name"] == "test-collection"
        assert d["total_files"] == 100
        assert len(d["processed_files"]) == 2
        assert d["entities_created"] == 50

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(UTC).isoformat()
        d = {
            "collection_name": "test-collection",
            "project_path": "/path/to/project",
            "total_files": 100,
            "processed_files": ["a.py", "b.py"],
            "pending_files": ["c.py"],
            "failed_files": [],
            "last_batch_index": 1,
            "entities_created": 50,
            "relations_created": 20,
            "chunks_created": 30,
            "started_at": now,
            "updated_at": now,
        }
        state = CheckpointState.from_dict(d)
        assert state.collection_name == "test-collection"
        assert state.total_files == 100
        assert len(state.processed_files) == 2

    def test_round_trip(self):
        """Test serialization round trip."""
        now = datetime.now(UTC).isoformat()
        original = CheckpointState(
            collection_name="test",
            project_path="/path",
            total_files=50,
            processed_files=["x.py"],
            pending_files=["y.py", "z.py"],
            failed_files=[],
            last_batch_index=0,
            entities_created=10,
            relations_created=5,
            chunks_created=8,
            started_at=now,
            updated_at=now,
        )
        restored = CheckpointState.from_dict(original.to_dict())
        assert restored.collection_name == original.collection_name
        assert restored.total_files == original.total_files
        assert restored.processed_files == original.processed_files
        assert restored.pending_files == original.pending_files


class TestIndexingPhase:
    """Tests for IndexingPhase enum."""

    def test_phase_values(self):
        """Test all phase values exist."""
        assert IndexingPhase.INIT.value == "init"
        assert IndexingPhase.DISCOVERY.value == "discovery"
        assert IndexingPhase.FILTERING.value == "filtering"
        assert IndexingPhase.PARSING.value == "parsing"
        assert IndexingPhase.EMBEDDING.value == "embedding"
        assert IndexingPhase.STORAGE.value == "storage"
        assert IndexingPhase.CLEANUP.value == "cleanup"
        assert IndexingPhase.COMPLETE.value == "complete"
