"""Type definitions for the indexing pipeline.

This module contains all dataclasses and type definitions used by the
IndexingPipeline and its sub-components.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class IndexingPhase(str, Enum):
    """Phases of the indexing pipeline."""

    INIT = "init"
    DISCOVERY = "discovery"
    FILTERING = "filtering"
    PARSING = "parsing"
    EMBEDDING = "embedding"
    STORAGE = "storage"
    CLEANUP = "cleanup"
    COMPLETE = "complete"


@dataclass
class PipelineConfig:
    """Configuration for the indexing pipeline.

    Attributes:
        initial_batch_size: Starting batch size for processing
        max_batch_size: Maximum batch size limit
        ramp_up_enabled: Whether to gradually increase batch size
        memory_threshold_mb: Memory limit before reducing batch size
        parallel_threshold: Minimum files to enable parallel processing
        checkpoint_interval: Files between checkpoint saves
        enable_resume: Whether to create checkpoints for resume capability
        max_parallel_workers: Maximum worker processes (0 = auto)
    """

    initial_batch_size: int = 25
    max_batch_size: int = 100
    ramp_up_enabled: bool = True
    memory_threshold_mb: int = 2000
    parallel_threshold: int = 100
    checkpoint_interval: int = 50
    enable_resume: bool = True
    max_parallel_workers: int = 0


@dataclass
class BatchResult:
    """Result of processing a single batch of files.

    Attributes:
        batch_index: Index of this batch (0-based)
        files_processed: Number of files successfully processed
        files_failed: Number of files that failed processing
        entities_created: Number of entities extracted
        relations_created: Number of relations extracted
        implementation_chunks: Number of implementation chunks created
        parse_time_ms: Time spent parsing files
        embed_time_ms: Time spent generating embeddings
        store_time_ms: Time spent storing vectors
        errors: List of error messages
        processed_files: List of successfully processed file paths
        failed_files: List of failed file paths
    """

    batch_index: int
    files_processed: int = 0
    files_failed: int = 0
    entities_created: int = 0
    relations_created: int = 0
    implementation_chunks: int = 0
    parse_time_ms: float = 0.0
    embed_time_ms: float = 0.0
    store_time_ms: float = 0.0
    errors: list[str] = field(default_factory=list)
    processed_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)

    @property
    def total_time_ms(self) -> float:
        """Total time for this batch in milliseconds."""
        return self.parse_time_ms + self.embed_time_ms + self.store_time_ms

    @property
    def success_rate(self) -> float:
        """Percentage of files successfully processed."""
        total = self.files_processed + self.files_failed
        if total == 0:
            return 0.0
        return self.files_processed / total


@dataclass
class PipelineResult:
    """Result of a complete pipeline execution.

    Attributes:
        success: Whether the pipeline completed successfully
        files_processed: Total files successfully indexed
        files_skipped: Files skipped (unchanged)
        files_failed: Files that failed processing
        entities_created: Total entities extracted
        relations_created: Total relations extracted
        implementation_chunks: Total implementation chunks
        total_time_seconds: Total execution time
        checkpoint_path: Path to checkpoint file (if created)
        errors: List of error messages
        warnings: List of warning messages
        batch_count: Number of batches processed
        cache_stats: File cache statistics
    """

    success: bool
    files_processed: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    entities_created: int = 0
    relations_created: int = 0
    implementation_chunks: int = 0
    total_time_seconds: float = 0.0
    checkpoint_path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    batch_count: int = 0
    cache_stats: dict[str, Any] = field(default_factory=dict)

    @property
    def total_files(self) -> int:
        """Total files considered."""
        return self.files_processed + self.files_skipped + self.files_failed

    @property
    def files_per_second(self) -> float:
        """Processing speed in files per second."""
        if self.total_time_seconds <= 0:
            return 0.0
        return self.files_processed / self.total_time_seconds


@dataclass
class ProgressState:
    """Current pipeline progress state.

    This dataclass captures the complete state of pipeline progress,
    suitable for display in progress bars and callbacks.

    Attributes:
        phase: Current pipeline phase
        total_files: Total files to process
        processed_files: Files processed so far
        current_batch: Current batch number (1-indexed)
        total_batches: Total number of batches
        files_per_second: Current processing speed
        eta_seconds: Estimated time remaining
        memory_mb: Current memory usage
        current_file: File currently being processed
        entities_created: Running total of entities
        relations_created: Running total of relations
        chunks_created: Running total of chunks
        cache_hits: Number of cache hits (unchanged files)
        cache_misses: Number of cache misses (changed files)
        parse_time_ms: Cumulative parse time
        embed_time_ms: Cumulative embedding time
        store_time_ms: Cumulative storage time
    """

    phase: str
    total_files: int
    processed_files: int
    current_batch: int
    total_batches: int
    files_per_second: float
    eta_seconds: float
    memory_mb: float
    current_file: str | None = None
    entities_created: int = 0
    relations_created: int = 0
    chunks_created: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    parse_time_ms: float = 0.0
    embed_time_ms: float = 0.0
    store_time_ms: float = 0.0

    @property
    def percent_complete(self) -> float:
        """Percentage of files processed."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def eta_formatted(self) -> str:
        """Human-readable ETA string."""
        if self.eta_seconds <= 0:
            return "calculating..."
        if self.eta_seconds < 60:
            return f"{int(self.eta_seconds)}s"
        minutes = int(self.eta_seconds // 60)
        seconds = int(self.eta_seconds % 60)
        if minutes < 60:
            return f"{minutes}m {seconds}s"
        hours = int(minutes // 60)
        mins = int(minutes % 60)
        return f"{hours}h {mins}m"


class ProgressCallback(Protocol):
    """Protocol for progress update callbacks.

    Implement this protocol to receive progress updates from the pipeline.
    """

    def __call__(self, state: ProgressState) -> None:
        """Called when progress is updated.

        Args:
            state: Current progress state
        """
        ...


@dataclass
class BatchMetrics:
    """Metrics from a completed batch for batch size optimization.

    Attributes:
        batch_size: Number of files in the batch
        processing_time_ms: Total time to process the batch
        memory_delta_mb: Memory change during batch processing
        error_count: Number of errors in the batch
        files_per_second: Processing speed for this batch
    """

    batch_size: int
    processing_time_ms: float
    memory_delta_mb: float
    error_count: int
    files_per_second: float = 0.0

    def __post_init__(self) -> None:
        """Calculate files_per_second if not provided."""
        if self.files_per_second == 0.0 and self.processing_time_ms > 0:
            self.files_per_second = self.batch_size / (self.processing_time_ms / 1000)


@dataclass
class ThresholdConfig:
    """Thresholds for batch size optimization.

    Attributes:
        min_batch_size: Minimum allowed batch size
        max_batch_size: Maximum allowed batch size
        memory_threshold_mb: Memory limit before reducing batch size
        error_rate_threshold: Error rate that triggers batch reduction
        ramp_up_factor: Factor to increase batch size after success
        ramp_down_factor: Factor to decrease batch size on error
        consecutive_successes_for_ramp: Successes needed before increasing
    """

    min_batch_size: int = 2
    max_batch_size: int = 100
    memory_threshold_mb: int = 2000
    error_rate_threshold: float = 0.1
    ramp_up_factor: float = 1.5
    ramp_down_factor: float = 0.5
    consecutive_successes_for_ramp: int = 3


@dataclass
class CheckpointState:
    """Serializable checkpoint state for resume capability.

    Attributes:
        collection_name: Target Qdrant collection
        project_path: Absolute path to project root
        total_files: Total files discovered
        processed_files: Relative paths of processed files
        pending_files: Relative paths of files not yet processed
        failed_files: Relative paths of failed files
        last_batch_index: Index of last completed batch
        entities_created: Running count of entities
        relations_created: Running count of relations
        chunks_created: Running count of chunks
        started_at: ISO timestamp of pipeline start
        updated_at: ISO timestamp of last checkpoint update
        config: Pipeline configuration used
    """

    collection_name: str
    project_path: str
    total_files: int
    processed_files: list[str]
    pending_files: list[str]
    failed_files: list[str]
    last_batch_index: int
    entities_created: int
    relations_created: int
    chunks_created: int
    started_at: str
    updated_at: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "collection_name": self.collection_name,
            "project_path": self.project_path,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "pending_files": self.pending_files,
            "failed_files": self.failed_files,
            "last_batch_index": self.last_batch_index,
            "entities_created": self.entities_created,
            "relations_created": self.relations_created,
            "chunks_created": self.chunks_created,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "config": self.config,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointState":
        """Create from dictionary."""
        return cls(
            collection_name=data["collection_name"],
            project_path=data["project_path"],
            total_files=data["total_files"],
            processed_files=data.get("processed_files", []),
            pending_files=data.get("pending_files", []),
            failed_files=data.get("failed_files", []),
            last_batch_index=data.get("last_batch_index", 0),
            entities_created=data.get("entities_created", 0),
            relations_created=data.get("relations_created", 0),
            chunks_created=data.get("chunks_created", 0),
            started_at=data.get("started_at", ""),
            updated_at=data.get("updated_at", ""),
            config=data.get("config", {}),
        )
