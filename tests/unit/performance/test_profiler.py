"""Tests for the EndToEndProfiler and related classes."""

import time

import pytest

from claude_indexer.performance.profiler import (
    EndToEndProfiler,
    ProfileResult,
    ProfilerStack,
    profile,
)


class TestProfileResult:
    """Tests for ProfileResult dataclass."""

    def test_basic_creation(self):
        """Test basic ProfileResult creation."""
        result = ProfileResult(
            operation="test_op",
            total_ms=100.5,
            sections={"parse": 30.0, "embed": 70.5},
            metadata={"file_count": 10},
        )

        assert result.operation == "test_op"
        assert result.total_ms == 100.5
        assert result.sections == {"parse": 30.0, "embed": 70.5}
        assert result.metadata == {"file_count": 10}

    def test_to_dict(self):
        """Test ProfileResult to_dict serialization."""
        result = ProfileResult(
            operation="test_op",
            total_ms=100.5,
            sections={"parse": 30.123456},
        )

        d = result.to_dict()
        assert d["operation"] == "test_op"
        assert d["total_ms"] == 100.5
        assert d["sections"]["parse"] == 30.12  # Rounded

    def test_str_representation(self):
        """Test string representation."""
        result = ProfileResult(
            operation="test_op",
            total_ms=100.0,
            sections={"a": 50.0, "b": 50.0},
        )

        s = str(result)
        assert "test_op" in s
        assert "100.00ms" in s


class TestEndToEndProfiler:
    """Tests for EndToEndProfiler."""

    def test_disabled_by_default(self):
        """Test profiler disabled by default (env var not set)."""
        profiler = EndToEndProfiler("test", enabled=False)

        with profiler:
            time.sleep(0.001)

        result = profiler.result()
        assert result.total_ms == 0  # No timing when disabled

    def test_enabled_profiling(self):
        """Test profiler when enabled."""
        profiler = EndToEndProfiler("test", enabled=True)

        with profiler:
            time.sleep(0.01)  # 10ms

        result = profiler.result()
        assert result.operation == "test"
        assert result.total_ms >= 10  # At least 10ms

    def test_sections(self):
        """Test section profiling."""
        profiler = EndToEndProfiler("test", enabled=True)

        with profiler:
            with profiler.section("step1"):
                time.sleep(0.005)
            with profiler.section("step2"):
                time.sleep(0.005)

        result = profiler.result()
        assert "step1" in result.sections
        assert "step2" in result.sections
        assert result.sections["step1"] >= 5
        assert result.sections["step2"] >= 5

    def test_section_accumulation(self):
        """Test that same section name accumulates time."""
        profiler = EndToEndProfiler("test", enabled=True)

        with profiler:
            with profiler.section("repeat"):
                time.sleep(0.005)
            with profiler.section("repeat"):
                time.sleep(0.005)

        result = profiler.result()
        assert result.sections["repeat"] >= 10  # At least 10ms total

    def test_metadata(self):
        """Test adding metadata."""
        profiler = EndToEndProfiler("test", enabled=True)

        with profiler:
            profiler.add_metadata("files", 100)
            profiler.add_metadata("errors", 0)

        result = profiler.result()
        assert result.metadata["files"] == 100
        assert result.metadata["errors"] == 0
        assert result.metadata["success"] is True

    def test_error_tracking(self):
        """Test error tracking in metadata."""
        profiler = EndToEndProfiler("test", enabled=True)

        with pytest.raises(ValueError), profiler:
            raise ValueError("test error")

        result = profiler.result()
        assert result.metadata["success"] is False
        assert result.metadata["error_type"] == "ValueError"

    def test_elapsed_ms(self):
        """Test elapsed_ms property during profiling."""
        profiler = EndToEndProfiler("test", enabled=True)

        with profiler:
            time.sleep(0.01)
            elapsed = profiler.elapsed_ms
            assert elapsed >= 10


class TestProfilerStack:
    """Tests for ProfilerStack."""

    def test_single_profiler(self):
        """Test stack with single profiler."""
        stack = ProfilerStack()

        with stack.push("operation1", enabled=True) as p:
            time.sleep(0.005)
            p.add_metadata("test", True)

        results = stack.all_results()
        assert len(results) == 1
        assert results[0].operation == "operation1"
        assert results[0].metadata["test"] is True

    def test_nested_profilers(self):
        """Test nested profilers in stack."""
        stack = ProfilerStack()

        with stack.push("outer", enabled=True):
            with stack.push("inner", enabled=True):
                time.sleep(0.005)

        results = stack.all_results()
        assert len(results) == 2
        assert any(r.operation == "outer" for r in results)
        assert any(r.operation == "inner" for r in results)

    def test_clear(self):
        """Test clearing results."""
        stack = ProfilerStack()

        with stack.push("op1", enabled=True):
            pass

        assert len(stack.all_results()) == 1

        stack.clear()
        assert len(stack.all_results()) == 0


class TestProfileConvenienceFunction:
    """Tests for profile() convenience function."""

    def test_profile_function(self):
        """Test profile() convenience function."""
        with profile("test", enabled=True) as p:
            time.sleep(0.005)
            p.add_metadata("count", 10)

        result = p.result()
        assert result.operation == "test"
        assert result.metadata["count"] == 10
        assert result.total_ms >= 5
