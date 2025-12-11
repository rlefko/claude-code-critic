"""Bulk indexing pipeline for Claude Code Memory.

This package provides a high-performance indexing pipeline with:
- Parallel file processing
- Intelligent batch sizing with memory awareness
- Progress tracking with ETA
- Resume capability for interrupted indexing
- File hash caching to skip unchanged files

Example usage:
    >>> from claude_indexer.indexing import IndexingPipeline, PipelineConfig
    >>> from claude_indexer.config import IndexerConfig
    >>>
    >>> pipeline = IndexingPipeline(
    ...     config=PipelineConfig(),
    ...     indexer_config=IndexerConfig.from_env(),
    ...     embedder=embedder,
    ...     vector_store=vector_store,
    ...     project_path=Path("/path/to/project"),
    ... )
    >>> result = pipeline.run("my-collection")
    >>> print(f"Indexed {result.files_processed} files in {result.total_time_seconds:.1f}s")
"""

from .batch_optimizer import BatchOptimizer
from .checkpoint import IndexingCheckpoint
from .pipeline import IndexingPipeline
from .progress import PipelineProgress
from .types import (
    BatchMetrics,
    BatchResult,
    CheckpointState,
    IndexingPhase,
    PipelineConfig,
    PipelineResult,
    ProgressCallback,
    ProgressState,
    ThresholdConfig,
)

__all__ = [
    # Main pipeline
    "IndexingPipeline",
    # Configuration
    "PipelineConfig",
    "ThresholdConfig",
    # Results
    "PipelineResult",
    "BatchResult",
    "BatchMetrics",
    # Progress
    "PipelineProgress",
    "ProgressState",
    "ProgressCallback",
    "IndexingPhase",
    # Checkpoint
    "IndexingCheckpoint",
    "CheckpointState",
    # Batch optimization
    "BatchOptimizer",
]
