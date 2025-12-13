"""End-to-end latency profiling with minimal overhead.

This module provides tools for profiling complete operations with
nested section support. Profiling can be disabled via environment
variable for production use.

Example usage:
    with EndToEndProfiler("index_repository") as profiler:
        with profiler.section("discover_files"):
            files = discover_files(path)
        profiler.add_metadata("file_count", len(files))

        with profiler.section("parse_files"):
            entities = parse_files(files)

        with profiler.section("embed"):
            vectors = embed(entities)

    result = profiler.result()
    print(f"Total: {result.total_ms}ms, Sections: {result.sections}")
"""

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import local
from typing import Any

# Environment variable to enable profiling (disabled by default for production)
PROFILING_ENABLED = os.environ.get("CLAUDE_INDEXER_PROFILE", "0") == "1"


@dataclass
class ProfileResult:
    """Result of a profiling session.

    Contains timing information for the overall operation and
    individual sections, along with optional metadata.

    Attributes:
        operation: Name of the profiled operation.
        total_ms: Total execution time in milliseconds.
        sections: Dictionary mapping section names to cumulative time in ms.
        metadata: Optional metadata added during profiling.
    """

    operation: str
    total_ms: float
    sections: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the profile result.
        """
        return {
            "operation": self.operation,
            "total_ms": round(self.total_ms, 2),
            "sections": {k: round(v, 2) for k, v in self.sections.items()},
            "metadata": self.metadata,
        }

    def __str__(self) -> str:
        """Return human-readable string representation."""
        parts = [f"{self.operation}: {self.total_ms:.2f}ms total"]
        if self.sections:
            section_strs = [f"{k}={v:.2f}ms" for k, v in self.sections.items()]
            parts.append(f"[{', '.join(section_strs)}]")
        return " ".join(parts)


class EndToEndProfiler:
    """Profiler for end-to-end operation latency with nested section support.

    Provides a context manager for profiling complete operations with
    the ability to track individual sections within the operation.
    Can be disabled via CLAUDE_INDEXER_PROFILE environment variable.

    Thread-safe: Uses thread-local storage for section stack.

    Attributes:
        operation: Name of the operation being profiled.
        enabled: Whether profiling is enabled.

    Example:
        with EndToEndProfiler("search") as profiler:
            with profiler.section("embed_query"):
                vector = embed(query)

            with profiler.section("search_qdrant"):
                results = search(vector)

            profiler.add_metadata("result_count", len(results))

        print(profiler.result())
    """

    _thread_local = local()

    def __init__(self, operation: str, enabled: bool | None = None):
        """Initialize the profiler.

        Args:
            operation: Name of the operation being profiled.
            enabled: Override for profiling enabled state.
                    If None, uses CLAUDE_INDEXER_PROFILE env var.
        """
        self.operation = operation
        self.enabled = enabled if enabled is not None else PROFILING_ENABLED
        self._start_time: float = 0
        self._total_ms: float = 0
        self._sections: dict[str, float] = {}
        self._section_stack: list[tuple[str, float]] = []
        self._metadata: dict[str, Any] = {}

    def __enter__(self) -> "EndToEndProfiler":
        """Start profiling the operation.

        Returns:
            Self for use in with statement.
        """
        if self.enabled:
            self._start_time = time.perf_counter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Stop profiling and calculate total time.

        Records whether the operation completed successfully or with error.
        """
        if self.enabled:
            self._total_ms = (time.perf_counter() - self._start_time) * 1000
            self._metadata["success"] = exc_type is None
            if exc_type is not None:
                self._metadata["error_type"] = exc_type.__name__

    @contextmanager
    def section(self, name: str) -> Generator[None, None, None]:
        """Profile a section within the operation.

        Sections can be nested. Time is accumulated for each section name,
        allowing the same section to be called multiple times.

        Args:
            name: Name of the section to profile.

        Yields:
            None - timing is recorded when context exits.

        Example:
            with profiler.section("parse"):
                for file in files:
                    with profiler.section("parse_file"):  # Nested
                        parse(file)
        """
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        self._section_stack.append((name, start))
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self._sections[name] = self._sections.get(name, 0) + duration_ms
            self._section_stack.pop()

    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the profile result.

        Metadata is included in the final ProfileResult and can be
        used to track additional context about the profiled operation.

        Args:
            key: Metadata key.
            value: Metadata value (must be JSON-serializable).
        """
        self._metadata[key] = value

    def result(self) -> ProfileResult:
        """Get the profiling result.

        Returns:
            ProfileResult with timing and metadata information.
        """
        return ProfileResult(
            operation=self.operation,
            total_ms=self._total_ms,
            sections=self._sections.copy(),
            metadata=self._metadata.copy(),
        )

    @property
    def elapsed_ms(self) -> float:
        """Get elapsed time since profiling started.

        Useful for checking progress during long operations.

        Returns:
            Elapsed time in milliseconds, or 0 if profiling disabled.
        """
        if not self.enabled or self._start_time == 0:
            return 0
        return (time.perf_counter() - self._start_time) * 1000


class ProfilerStack:
    """Stack of profilers for hierarchical operation tracking.

    Allows creating nested profilers that automatically become
    children of the current profiler on the stack.

    Thread-safe: Uses thread-local storage.

    Example:
        stack = ProfilerStack()

        with stack.push("outer_operation") as outer:
            with stack.push("inner_operation") as inner:
                do_work()
            # inner profiler automatically popped

        results = stack.all_results()
    """

    _thread_local = local()

    def __init__(self) -> None:
        """Initialize an empty profiler stack."""
        self._results: list[ProfileResult] = []

    @contextmanager
    def push(
        self, operation: str, enabled: bool | None = None
    ) -> Generator[EndToEndProfiler, None, None]:
        """Push a new profiler onto the stack.

        Args:
            operation: Name of the operation to profile.
            enabled: Override for profiling enabled state.

        Yields:
            The new profiler.
        """
        profiler = EndToEndProfiler(operation, enabled)
        with profiler:
            yield profiler

        if profiler.enabled:
            self._results.append(profiler.result())

    def all_results(self) -> list[ProfileResult]:
        """Get all collected profile results.

        Returns:
            List of ProfileResult objects.
        """
        return self._results.copy()

    def clear(self) -> None:
        """Clear all collected results."""
        self._results.clear()


# Module-level convenience functions
_global_stack = ProfilerStack()


def profile(operation: str, enabled: bool | None = None) -> EndToEndProfiler:
    """Create a standalone profiler.

    Args:
        operation: Name of the operation to profile.
        enabled: Override for profiling enabled state.

    Returns:
        EndToEndProfiler instance.

    Example:
        with profile("my_operation") as p:
            with p.section("step1"):
                step1()
    """
    return EndToEndProfiler(operation, enabled)


__all__ = [
    "PROFILING_ENABLED",
    "ProfileResult",
    "EndToEndProfiler",
    "ProfilerStack",
    "profile",
]
