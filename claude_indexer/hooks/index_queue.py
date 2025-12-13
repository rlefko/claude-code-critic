"""
Async queue for non-blocking file indexing.

Files are queued and processed in a background thread.
Uses debouncing to coalesce rapid changes to the same file.

The queue is file-based for persistence across process restarts:
~/.claude-code-memory/queue/{collection}.queue

Queue entries are JSON lines with file path, project, and timestamp.
A background timer processes entries after a debounce delay.
"""

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class IndexQueue:
    """Singleton queue for async file indexing.

    Files are queued and processed in a background thread with debouncing
    to coalesce rapid changes. This allows the post-write hook to return
    immediately without waiting for indexing to complete.

    Example usage:
        queue = IndexQueue.get_instance()
        queue.enqueue(
            file_path=Path("src/main.py"),
            project_path=Path("/project"),
            collection="my-project"
        )
        # Returns immediately, indexing happens in background
    """

    _instance: ClassVar["IndexQueue | None"] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    # Default queue directory
    DEFAULT_QUEUE_DIR = Path.home() / ".claude-code-memory" / "queue"

    # Debounce delay in seconds
    DEBOUNCE_DELAY = 2.0

    @classmethod
    def get_instance(cls, queue_dir: Path | None = None) -> "IndexQueue":
        """Get or create singleton instance.

        Args:
            queue_dir: Optional custom queue directory

        Returns:
            IndexQueue singleton instance
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(queue_dir=queue_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.stop()
                cls._instance = None

    def __init__(self, queue_dir: Path | None = None) -> None:
        """Initialize queue with background processing.

        Args:
            queue_dir: Directory for queue files (default: ~/.claude-code-memory/queue)
        """
        self.queue_dir = queue_dir or self.DEFAULT_QUEUE_DIR
        self.queue_dir.mkdir(parents=True, exist_ok=True)

        # Pending files per collection: collection -> {file_path: timestamp}
        self._pending: dict[str, dict[str, dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()

        # Background timer thread
        self._stop_event = threading.Event()
        self._timer_thread: threading.Thread | None = None
        self._start_timer()

    def _start_timer(self) -> None:
        """Start background timer thread."""
        if self._timer_thread is None or not self._timer_thread.is_alive():
            self._timer_thread = threading.Thread(
                target=self._timer_loop,
                daemon=True,
                name="IndexQueue-Timer",
            )
            self._timer_thread.start()

    def _timer_loop(self) -> None:
        """Background timer that processes ready files."""
        while not self._stop_event.is_set():
            try:
                time.sleep(self.DEBOUNCE_DELAY)
                self._process_ready_files()
            except Exception as e:
                logger.error(f"IndexQueue timer error: {e}")

    def _process_ready_files(self) -> None:
        """Process files that have been stable for debounce period."""
        current_time = time.time()
        files_to_process: list[dict[str, Any]] = []

        with self._pending_lock:
            for collection, files in list(self._pending.items()):
                ready_files = []
                for file_path, entry in list(files.items()):
                    if current_time - entry["timestamp"] >= self.DEBOUNCE_DELAY:
                        ready_files.append(entry)
                        del files[file_path]

                files_to_process.extend(ready_files)

                # Clean up empty collections
                if not files:
                    del self._pending[collection]

        # Process ready files outside the lock
        if files_to_process:
            self._index_files(files_to_process)

    def _index_files(self, entries: list[dict[str, Any]]) -> None:
        """Index a batch of files using claude-indexer.

        Args:
            entries: List of queue entries to index
        """
        # Group by collection for batch processing
        by_collection: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            collection = entry["collection"]
            if collection not in by_collection:
                by_collection[collection] = []
            by_collection[collection].append(entry)

        for collection, collection_entries in by_collection.items():
            if not collection_entries:
                continue

            # Get project path from first entry
            project_path = collection_entries[0]["project_path"]
            file_paths = [e["file_path"] for e in collection_entries]

            try:
                # Use batch indexing via stdin for efficiency
                file_list = "\n".join(file_paths)
                cmd = [
                    "claude-indexer",
                    "index",
                    "-p",
                    project_path,
                    "-c",
                    collection,
                    "--files-from-stdin",
                    "--quiet",
                ]

                result = subprocess.run(
                    cmd,
                    input=file_list,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    logger.warning(
                        f"Indexing failed for {len(file_paths)} files: {result.stderr}"
                    )
                else:
                    logger.debug(f"Indexed {len(file_paths)} files in {collection}")

            except subprocess.TimeoutExpired:
                logger.warning(f"Indexing timed out for {len(file_paths)} files")
            except FileNotFoundError:
                logger.debug("claude-indexer not available, skipping indexing")
            except Exception as e:
                logger.warning(f"Indexing error: {e}")

    def enqueue(
        self,
        file_path: Path,
        project_path: Path,
        collection: str,
    ) -> None:
        """Add file to indexing queue (non-blocking).

        The file will be indexed after the debounce delay.
        Multiple changes to the same file are coalesced.

        Args:
            file_path: Path to the file to index
            project_path: Project root directory
            collection: Qdrant collection name
        """
        entry = {
            "file_path": str(file_path.resolve()),
            "project_path": str(project_path.resolve()),
            "collection": collection,
            "timestamp": time.time(),
        }

        with self._pending_lock:
            if collection not in self._pending:
                self._pending[collection] = {}
            # Update timestamp for this file (coalesces multiple changes)
            self._pending[collection][str(file_path.resolve())] = entry

        # Also write to queue file for persistence
        self._write_to_queue_file(entry)

    def _write_to_queue_file(self, entry: dict[str, Any]) -> None:
        """Write entry to persistent queue file.

        Args:
            entry: Queue entry to persist
        """
        try:
            queue_file = self.queue_dir / f"{entry['collection']}.queue"
            with open(queue_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write queue file: {e}")

    def get_pending_count(self, collection: str | None = None) -> int:
        """Get count of pending files.

        Args:
            collection: Optional collection to filter by

        Returns:
            Number of files pending indexing
        """
        with self._pending_lock:
            if collection:
                return len(self._pending.get(collection, {}))
            return sum(len(files) for files in self._pending.values())

    def force_process(self) -> int:
        """Force immediate processing of all pending files.

        Returns:
            Number of files processed
        """
        entries: list[dict[str, Any]] = []

        with self._pending_lock:
            for files in self._pending.values():
                entries.extend(files.values())
            self._pending.clear()

        if entries:
            self._index_files(entries)

        return len(entries)

    def stop(self) -> None:
        """Stop the background timer thread."""
        self._stop_event.set()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=2.0)

    def cleanup_queue_files(self, max_age_hours: float = 24.0) -> int:
        """Remove old queue files.

        Args:
            max_age_hours: Maximum age of queue files to keep

        Returns:
            Number of files cleaned up
        """
        cleaned = 0
        cutoff = time.time() - (max_age_hours * 3600)

        try:
            for queue_file in self.queue_dir.glob("*.queue"):
                if queue_file.stat().st_mtime < cutoff:
                    queue_file.unlink()
                    cleaned += 1
        except Exception as e:
            logger.warning(f"Queue cleanup error: {e}")

        return cleaned


def enqueue_for_indexing(
    file_path: str,
    project_path: str,
    collection: str,
) -> None:
    """Convenience function to enqueue a file for indexing.

    This is a simple wrapper for use from shell scripts.

    Args:
        file_path: Path to file to index
        project_path: Project root directory
        collection: Qdrant collection name
    """
    queue = IndexQueue.get_instance()
    queue.enqueue(
        file_path=Path(file_path),
        project_path=Path(project_path),
        collection=collection,
    )
