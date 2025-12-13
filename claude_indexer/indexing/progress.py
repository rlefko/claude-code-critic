"""Pipeline progress reporter with ETA and terminal visualization.

This module provides unified progress tracking for the indexing pipeline,
integrating with the existing ModernProgressBar for terminal output.
"""

import time
from logging import Logger
from pathlib import Path
from typing import Any

import psutil

from ..indexer_logging import get_logger
from ..performance import PerformanceAggregator
from ..progress_bar import BatchProgressBar
from .types import ProgressCallback, ProgressState


class PipelineProgress:
    """Unified progress reporter for the indexing pipeline.

    Consolidates progress tracking logic into a dedicated component with
    callback support and terminal rendering via BatchProgressBar.

    Features:
        - Real-time progress updates with ETA
        - Memory monitoring
        - Performance aggregation
        - Callback support for external consumers
        - Beautiful terminal visualization

    Example:
        >>> progress = PipelineProgress()
        >>> progress.start(total_files=100, total_batches=4)
        >>> progress.update_batch(batch_index=0, files_in_batch=25, tier_stats={})
        >>> progress.complete_batch(batch_index=0, entities=50, relations=20, ...)
        >>> state = progress.finish(success=True)
    """

    def __init__(
        self,
        logger: Logger | None = None,
        enable_terminal: bool = True,
        description: str = "Indexing",
        quiet: bool = False,
        use_color: bool | None = None,
    ):
        """Initialize progress reporter.

        Args:
            logger: Optional logger instance
            enable_terminal: Whether to show terminal progress bar
            description: Description for progress bar
            quiet: Suppress progress output (for quiet mode)
            use_color: Use ANSI colors. None = auto-detect from env/TTY
        """
        self.logger = logger or get_logger()
        self.enable_terminal = enable_terminal and not quiet
        self.description = description
        self.quiet = quiet
        self.use_color = use_color

        # Progress state
        self._state = ProgressState(
            phase="init",
            total_files=0,
            processed_files=0,
            current_batch=0,
            total_batches=0,
            files_per_second=0.0,
            eta_seconds=0.0,
            memory_mb=0.0,
        )

        # Timing
        self._start_time: float = 0.0
        self._batch_start_time: float = 0.0

        # Callbacks
        self._callbacks: list[ProgressCallback] = []

        # Terminal progress bar
        self._progress_bar: BatchProgressBar | None = None

        # Performance tracking
        self._perf = PerformanceAggregator()

    def start(
        self,
        total_files: int,
        total_batches: int,
        callback: ProgressCallback | None = None,
    ) -> None:
        """Initialize progress tracking for a pipeline run.

        Args:
            total_files: Total number of files to process
            total_batches: Total number of batches planned
            callback: Optional callback for progress updates
        """
        self._start_time = time.time()
        self._state = ProgressState(
            phase="discovery",
            total_files=total_files,
            processed_files=0,
            current_batch=0,
            total_batches=total_batches,
            files_per_second=0.0,
            eta_seconds=0.0,
            memory_mb=self._get_memory_mb(),
        )

        if callback:
            self._callbacks.append(callback)

        # Initialize terminal progress bar
        if self.enable_terminal and total_files > 0:
            self._progress_bar = BatchProgressBar(
                total_files,
                self.description,
                quiet=self.quiet,
                use_color=self.use_color,
            )

        self._perf.reset()
        self._notify_callbacks()

        self.logger.info(
            f"Starting pipeline: {total_files} files in {total_batches} batches"
        )

    def set_phase(self, phase: str) -> None:
        """Update the current pipeline phase.

        Args:
            phase: New phase name (discovery, filtering, parsing, etc.)
        """
        self._state.phase = phase
        self._notify_callbacks()

    def update_discovery(self, files_found: int, files_filtered: int) -> None:
        """Update progress during file discovery.

        Args:
            files_found: Total files discovered
            files_filtered: Files filtered (unchanged)
        """
        self._state.phase = "filtering"
        self._state.cache_hits = files_filtered
        self._state.cache_misses = files_found - files_filtered
        self._notify_callbacks()

        self.logger.info(
            f"Discovery: {files_found} files found, "
            f"{files_filtered} unchanged (skipped)"
        )

    def update_batch(
        self,
        batch_index: int,
        files_in_batch: int,
        tier_stats: dict[str, int] | None = None,
    ) -> None:
        """Update progress when starting a new batch.

        Args:
            batch_index: Index of the batch (0-based)
            files_in_batch: Number of files in this batch
            tier_stats: Optional tier breakdown (light, standard, deep)
        """
        self._batch_start_time = time.time()
        self._state.phase = "parsing"
        self._state.current_batch = batch_index + 1  # 1-indexed for display
        self._state.memory_mb = self._get_memory_mb()

        # Format tier info for progress bar
        if tier_stats:
            parts = []
            if tier_stats.get("light", 0) > 0:
                parts.append(f"{tier_stats['light']} light")
            if tier_stats.get("deep", 0) > 0:
                parts.append(f"{tier_stats['deep']} deep")
            if parts:
                f"({', '.join(parts)})"

        # Update terminal progress bar
        if self._progress_bar:
            self._progress_bar.update_batch(
                batch_num=batch_index + 1,
                total_batches=self._state.total_batches,
                files_in_batch=files_in_batch,
                files_completed=self._state.processed_files,
                total_files=self._state.total_files,
                memory_mb=int(self._state.memory_mb),
                light_files=tier_stats.get("light", 0) if tier_stats else 0,
            )

        self._notify_callbacks()

    def update_file(self, file_path: Path, status: str = "processing") -> None:
        """Update progress for a single file.

        Args:
            file_path: Path to the file
            status: Status string (processing, complete, failed)
        """
        self._state.current_file = str(file_path.name)

        if status == "complete":
            self._state.processed_files += 1
            self._update_speed_eta()

            # Update terminal progress bar
            if self._progress_bar:
                self._progress_bar.update(current=self._state.processed_files)

        self._notify_callbacks()

    def complete_batch(
        self,
        batch_index: int,
        entities: int,
        relations: int,
        chunks: int,
        parse_time_ms: float,
        embed_time_ms: float,
        store_time_ms: float,
        files_processed: int = 0,
    ) -> None:
        """Record batch completion metrics.

        Args:
            batch_index: Index of completed batch
            entities: Entities created in this batch
            relations: Relations created in this batch
            chunks: Implementation chunks created
            parse_time_ms: Time spent parsing
            embed_time_ms: Time spent embedding
            store_time_ms: Time spent storing
            files_processed: Files processed in this batch
        """
        # Update cumulative metrics
        self._state.entities_created += entities
        self._state.relations_created += relations
        self._state.chunks_created += chunks
        self._state.parse_time_ms += parse_time_ms
        self._state.embed_time_ms += embed_time_ms
        self._state.store_time_ms += store_time_ms

        if files_processed > 0:
            self._state.processed_files = min(
                self._state.processed_files + files_processed,
                self._state.total_files,
            )

        # Track performance
        batch_total_ms = parse_time_ms + embed_time_ms + store_time_ms
        self._perf.record("batch", batch_total_ms)
        self._perf.record("parse", parse_time_ms)
        self._perf.record("embed", embed_time_ms)
        self._perf.record("store", store_time_ms)

        self._update_speed_eta()
        self._notify_callbacks()

        self.logger.debug(
            f"Batch {batch_index + 1} complete: "
            f"{entities} entities, {relations} relations, {chunks} chunks, "
            f"total time {batch_total_ms:.0f}ms"
        )

    def increment_files(self, count: int = 1, failed: bool = False) -> None:
        """Increment file counter.

        Args:
            count: Number of files to add
            failed: Whether files failed (don't count as processed)
        """
        if not failed:
            self._state.processed_files += count
            self._update_speed_eta()

            if self._progress_bar:
                self._progress_bar.update(current=self._state.processed_files)

        self._notify_callbacks()

    def finish(self, success: bool = True) -> ProgressState:
        """Finalize progress tracking and return final state.

        Args:
            success: Whether the pipeline completed successfully

        Returns:
            Final progress state
        """
        self._state.phase = "complete"
        elapsed = time.time() - self._start_time
        self._state.eta_seconds = 0.0

        # Final update
        if self._progress_bar:
            self._progress_bar.finish(success=success)
            self._progress_bar = None

        self._notify_callbacks()

        # Log summary
        self.logger.info(
            f"Pipeline {'completed' if success else 'failed'}: "
            f"{self._state.processed_files}/{self._state.total_files} files "
            f"in {elapsed:.1f}s ({self._state.files_per_second:.1f} files/s)"
        )

        return self._state

    def get_state(self) -> ProgressState:
        """Get current progress state snapshot.

        Returns:
            Copy of current progress state
        """
        return ProgressState(
            phase=self._state.phase,
            total_files=self._state.total_files,
            processed_files=self._state.processed_files,
            current_batch=self._state.current_batch,
            total_batches=self._state.total_batches,
            files_per_second=self._state.files_per_second,
            eta_seconds=self._state.eta_seconds,
            memory_mb=self._state.memory_mb,
            current_file=self._state.current_file,
            entities_created=self._state.entities_created,
            relations_created=self._state.relations_created,
            chunks_created=self._state.chunks_created,
            cache_hits=self._state.cache_hits,
            cache_misses=self._state.cache_misses,
            parse_time_ms=self._state.parse_time_ms,
            embed_time_ms=self._state.embed_time_ms,
            store_time_ms=self._state.store_time_ms,
        )

    def get_performance_report(self) -> dict[str, Any]:
        """Get aggregated performance statistics.

        Returns:
            Dictionary with performance metrics
        """
        elapsed = time.time() - self._start_time if self._start_time > 0 else 0

        return {
            "total_time_seconds": elapsed,
            "files_processed": self._state.processed_files,
            "files_per_second": self._state.files_per_second,
            "entities_created": self._state.entities_created,
            "relations_created": self._state.relations_created,
            "chunks_created": self._state.chunks_created,
            "cache_hits": self._state.cache_hits,
            "cache_misses": self._state.cache_misses,
            "timing": {
                "parse_ms": self._state.parse_time_ms,
                "embed_ms": self._state.embed_time_ms,
                "store_ms": self._state.store_time_ms,
            },
            "perf_aggregates": self._perf.report(),
        }

    def add_callback(self, callback: ProgressCallback) -> None:
        """Add a progress callback.

        Args:
            callback: Callback function to receive updates
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback: ProgressCallback) -> None:
        """Remove a progress callback.

        Args:
            callback: Callback to remove
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _update_speed_eta(self) -> None:
        """Update files_per_second and ETA calculations."""
        elapsed = time.time() - self._start_time
        if elapsed > 0 and self._state.processed_files > 0:
            self._state.files_per_second = self._state.processed_files / elapsed

            remaining = self._state.total_files - self._state.processed_files
            if self._state.files_per_second > 0:
                self._state.eta_seconds = remaining / self._state.files_per_second
            else:
                self._state.eta_seconds = 0.0

    def _get_memory_mb(self) -> float:
        """Get current process memory usage in MB."""
        try:
            process = psutil.Process()
            return process.memory_info().rss / (1024 * 1024)
        except Exception:
            return 0.0

    def _notify_callbacks(self) -> None:
        """Notify all registered callbacks of progress update."""
        state = self.get_state()
        for callback in self._callbacks:
            try:
                callback(state)
            except Exception as e:
                self.logger.warning(f"Progress callback error: {e}")
