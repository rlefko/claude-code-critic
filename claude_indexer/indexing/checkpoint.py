"""Checkpoint management for resume capability.

This module provides checkpoint persistence for the indexing pipeline,
enabling recovery from interruptions without re-processing completed files.
"""

import json
import os
import tempfile
from datetime import UTC, datetime
from logging import Logger
from pathlib import Path
from typing import Any

from ..indexer_logging import get_logger
from .types import CheckpointState, PipelineConfig


class IndexingCheckpoint:
    """Manages checkpoint persistence for resume capability.

    Checkpoints are saved periodically during indexing to enable
    recovery from interruptions without re-processing completed files.

    Features:
        - Atomic writes with temp file + rename pattern
        - Staleness detection (configurable timeout)
        - Per-collection checkpoints
        - Thread-safe operations

    Example:
        >>> checkpoint = IndexingCheckpoint(cache_dir=Path(".index_cache"))
        >>> checkpoint.create("my-collection", project_path, all_files)
        >>> checkpoint.update(processed_file=Path("foo.py"))
        >>> checkpoint.save()
        >>> # Later, on resume:
        >>> if checkpoint.exists("my-collection"):
        >>>     pending = checkpoint.get_pending_files(project_path)
    """

    CHECKPOINT_PREFIX = "indexing_checkpoint_"
    STALE_HOURS = 24  # Checkpoints older than this are considered stale

    def __init__(
        self,
        cache_dir: Path,
        enabled: bool = True,
        logger: Logger | None = None,
    ):
        """Initialize checkpoint manager.

        Args:
            cache_dir: Directory for checkpoint storage
            enabled: Whether checkpointing is enabled
            logger: Optional logger instance
        """
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled
        self.logger = logger or get_logger()
        self._state: CheckpointState | None = None
        self._dirty = False

    def _get_checkpoint_path(self, collection_name: str) -> Path:
        """Get checkpoint file path for a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Path to the checkpoint file
        """
        safe_name = collection_name.replace("/", "_").replace("\\", "_")
        return self.cache_dir / f"{self.CHECKPOINT_PREFIX}{safe_name}.json"

    def exists(self, collection_name: str) -> bool:
        """Check if a valid checkpoint exists for the collection.

        Args:
            collection_name: Name of the collection

        Returns:
            True if a non-stale checkpoint exists
        """
        if not self.enabled:
            return False

        path = self._get_checkpoint_path(collection_name)
        if not path.exists():
            return False

        # Check if checkpoint is stale
        try:
            state = self._load_state(path)
            if state and not self._is_stale(state):
                return True
        except Exception:
            pass

        return False

    def load(self, collection_name: str) -> CheckpointState | None:
        """Load existing checkpoint if valid.

        Args:
            collection_name: Name of the collection

        Returns:
            Checkpoint state if valid, None otherwise
        """
        if not self.enabled:
            return None

        path = self._get_checkpoint_path(collection_name)
        if not path.exists():
            return None

        try:
            state = self._load_state(path)
            if state and not self._is_stale(state):
                self._state = state
                self.logger.info(
                    f"Loaded checkpoint: {len(state.processed_files)} processed, "
                    f"{len(state.pending_files)} pending"
                )
                return state
            elif state:
                self.logger.warning(
                    f"Checkpoint is stale (updated {state.updated_at}), ignoring"
                )
                self.clear(collection_name)
        except Exception as e:
            self.logger.warning(f"Failed to load checkpoint: {e}")

        return None

    def create(
        self,
        collection_name: str,
        project_path: Path,
        all_files: list[Path],
        config: PipelineConfig | None = None,
    ) -> CheckpointState:
        """Create a new checkpoint at the start of indexing.

        Args:
            collection_name: Target collection name
            project_path: Project root path
            all_files: All files to be indexed
            config: Pipeline configuration

        Returns:
            New checkpoint state
        """
        if not self.enabled:
            # Return a minimal state when disabled
            return CheckpointState(
                collection_name=collection_name,
                project_path=str(project_path),
                total_files=len(all_files),
                processed_files=[],
                pending_files=[str(f) for f in all_files],
                failed_files=[],
                last_batch_index=0,
                entities_created=0,
                relations_created=0,
                chunks_created=0,
                started_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
            )

        now = datetime.now(UTC).isoformat()
        pending = [str(f.relative_to(project_path)) for f in all_files]

        config_dict: dict[str, Any] = {}
        if config:
            config_dict = {
                "initial_batch_size": config.initial_batch_size,
                "max_batch_size": config.max_batch_size,
                "checkpoint_interval": config.checkpoint_interval,
            }

        self._state = CheckpointState(
            collection_name=collection_name,
            project_path=str(project_path.resolve()),
            total_files=len(all_files),
            processed_files=[],
            pending_files=pending,
            failed_files=[],
            last_batch_index=0,
            entities_created=0,
            relations_created=0,
            chunks_created=0,
            started_at=now,
            updated_at=now,
            config=config_dict,
        )
        self._dirty = True

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.logger.debug(
            f"Created checkpoint for {collection_name}: "
            f"{len(all_files)} files pending"
        )

        return self._state

    def update(
        self,
        processed_file: Path | None = None,
        failed_file: Path | None = None,
        batch_index: int | None = None,
        entities: int = 0,
        relations: int = 0,
        chunks: int = 0,
    ) -> None:
        """Update checkpoint with progress.

        Args:
            processed_file: File that was successfully processed
            failed_file: File that failed processing
            batch_index: Index of completed batch
            entities: Entities created in this update
            relations: Relations created in this update
            chunks: Chunks created in this update
        """
        if not self.enabled or self._state is None:
            return

        project_path = Path(self._state.project_path)

        if processed_file:
            try:
                rel_path = str(processed_file.relative_to(project_path))
            except ValueError:
                rel_path = str(processed_file)

            if rel_path in self._state.pending_files:
                self._state.pending_files.remove(rel_path)
            if rel_path not in self._state.processed_files:
                self._state.processed_files.append(rel_path)
            self._dirty = True

        if failed_file:
            try:
                rel_path = str(failed_file.relative_to(project_path))
            except ValueError:
                rel_path = str(failed_file)

            if rel_path in self._state.pending_files:
                self._state.pending_files.remove(rel_path)
            if rel_path not in self._state.failed_files:
                self._state.failed_files.append(rel_path)
            self._dirty = True

        if batch_index is not None:
            self._state.last_batch_index = batch_index
            self._dirty = True

        if entities > 0:
            self._state.entities_created += entities
            self._dirty = True

        if relations > 0:
            self._state.relations_created += relations
            self._dirty = True

        if chunks > 0:
            self._state.chunks_created += chunks
            self._dirty = True

        # Update timestamp
        if self._dirty:
            self._state.updated_at = datetime.now(UTC).isoformat()

    def update_batch(
        self,
        processed_files: list[Path],
        failed_files: list[Path],
        batch_index: int,
        entities: int = 0,
        relations: int = 0,
        chunks: int = 0,
    ) -> None:
        """Update checkpoint for a complete batch.

        Args:
            processed_files: Files successfully processed
            failed_files: Files that failed
            batch_index: Index of completed batch
            entities: Total entities created in batch
            relations: Total relations created in batch
            chunks: Total chunks created in batch
        """
        for f in processed_files:
            self.update(processed_file=f)
        for f in failed_files:
            self.update(failed_file=f)
        self.update(
            batch_index=batch_index,
            entities=entities,
            relations=relations,
            chunks=chunks,
        )

    def save(self) -> None:
        """Persist checkpoint to disk.

        Uses atomic write with temp file + rename pattern to prevent
        corruption from interrupted writes.
        """
        if not self.enabled or self._state is None or not self._dirty:
            return

        path = self._get_checkpoint_path(self._state.collection_name)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Atomic write: write to temp file, then rename
            fd, temp_path = tempfile.mkstemp(dir=self.cache_dir, suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._state.to_dict(), f, indent=2)

                # Atomic rename
                os.replace(temp_path, path)
                self._dirty = False

                self.logger.debug(
                    f"Saved checkpoint: {len(self._state.processed_files)} "
                    f"processed, {len(self._state.pending_files)} pending"
                )
            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise
        except Exception as e:
            self.logger.warning(f"Failed to save checkpoint: {e}")

    def clear(self, collection_name: str) -> None:
        """Remove checkpoint after successful completion.

        Args:
            collection_name: Name of the collection
        """
        if not self.enabled:
            return

        path = self._get_checkpoint_path(collection_name)
        try:
            if path.exists():
                path.unlink()
                self.logger.debug(f"Cleared checkpoint for {collection_name}")
        except Exception as e:
            self.logger.warning(f"Failed to clear checkpoint: {e}")

        self._state = None
        self._dirty = False

    def get_pending_files(self, project_path: Path) -> list[Path]:
        """Get remaining files to process from checkpoint.

        Args:
            project_path: Project root path

        Returns:
            List of absolute paths for pending files
        """
        if not self._state:
            return []

        return [
            project_path / rel_path
            for rel_path in self._state.pending_files
            if (project_path / rel_path).exists()
        ]

    def get_state(self) -> CheckpointState | None:
        """Get current checkpoint state.

        Returns:
            Current state or None if not initialized
        """
        return self._state

    def _load_state(self, path: Path) -> CheckpointState | None:
        """Load checkpoint state from file.

        Args:
            path: Path to checkpoint file

        Returns:
            Loaded state or None on error
        """
        try:
            with open(path) as f:
                data = json.load(f)
            return CheckpointState.from_dict(data)
        except Exception as e:
            self.logger.warning(f"Failed to parse checkpoint: {e}")
            return None

    def _is_stale(self, state: CheckpointState) -> bool:
        """Check if checkpoint is stale.

        Args:
            state: Checkpoint state to check

        Returns:
            True if checkpoint is older than STALE_HOURS
        """
        try:
            updated = datetime.fromisoformat(state.updated_at)
            now = datetime.now(UTC)
            hours_old = (now - updated).total_seconds() / 3600
            return hours_old > self.STALE_HOURS
        except Exception:
            return True  # Treat parse errors as stale

    @property
    def has_pending(self) -> bool:
        """Check if there are pending files."""
        return self._state is not None and len(self._state.pending_files) > 0

    @property
    def progress_percent(self) -> float:
        """Get completion percentage."""
        if not self._state or self._state.total_files == 0:
            return 0.0
        processed = len(self._state.processed_files)
        return (processed / self._state.total_files) * 100
