"""Unit tests for enhanced logging infrastructure (Milestone 0.3)."""

import json
import logging
import time
from pathlib import Path

import pytest

from claude_indexer.indexer_logging import (
    JSONFormatter,
    LogCategory,
    clear_log_file,
    debug_context,
    get_category_logger,
    get_default_log_file,
    get_global_log_dir,
    get_logger,
    setup_logging,
    setup_multi_component_logging,
)
from claude_indexer.performance import (
    PerformanceAggregator,
    PerformanceTimer,
    timed,
)


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_default_setup(self, tmp_path: Path) -> None:
        """Test basic logging setup with defaults."""
        log_file = tmp_path / "test.log"
        logger = setup_logging(log_file=log_file)

        assert logger is not None
        logger.info("Test message")

        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    def test_rotation_count_parameter(self, tmp_path: Path) -> None:
        """Test that rotation_count parameter is accepted."""
        log_file = tmp_path / "rotate.log"
        logger = setup_logging(
            log_file=log_file,
            rotation_count=3,
            max_bytes=1024,  # Small for testing
        )

        assert logger is not None
        # Write enough logs to potentially trigger rotation
        for i in range(50):
            logger.info(f"Log entry {i} " + "x" * 50)

    def test_json_format(self, tmp_path: Path) -> None:
        """Test JSON log format."""
        log_file = tmp_path / "json.log"
        setup_logging(log_file=log_file, log_format="json")

        logger = get_logger()
        logger.info("JSON test message")

        content = log_file.read_text().strip()
        # Get the last line (most recent log entry)
        lines = content.split("\n")
        log_entry = json.loads(lines[-1])

        assert "timestamp" in log_entry
        assert log_entry["message"] == "JSON test message"
        assert log_entry["level"] == "INFO"
        assert "logger" in log_entry
        assert "module" in log_entry

    def test_text_format_default(self, tmp_path: Path) -> None:
        """Test that text format is the default."""
        log_file = tmp_path / "text.log"
        setup_logging(log_file=log_file)

        logger = get_logger()
        logger.info("Text test message")

        content = log_file.read_text()
        # Text format should contain the separator "|"
        assert "|" in content
        assert "Text test message" in content
        # Should not be JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(content.strip().split("\n")[-1])

    def test_debug_mode(self, tmp_path: Path) -> None:
        """Test verbose mode enables debug output."""
        log_file = tmp_path / "debug.log"
        setup_logging(log_file=log_file, verbose=True)

        logger = get_logger()
        logger.debug("Debug message should appear")

        content = log_file.read_text()
        assert "Debug message should appear" in content

    def test_quiet_mode(self, tmp_path: Path) -> None:
        """Test quiet mode suppresses info/warning."""
        log_file = tmp_path / "quiet.log"
        # quiet mode only affects console, file still logs at DEBUG
        setup_logging(log_file=log_file, quiet=True)

        logger = get_logger()
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        # File should still have all messages (file handler is at DEBUG)
        content = log_file.read_text()
        assert "Info message" in content
        assert "Error message" in content

    def test_backward_compatible_signature(self, tmp_path: Path) -> None:
        """Test that existing setup_logging calls still work."""
        log_file = tmp_path / "compat.log"

        # Old-style call (without new parameters)
        logger = setup_logging(
            level="INFO",
            quiet=False,
            verbose=True,
            log_file=log_file,
            enable_file_logging=True,
            collection_name="test-collection",
            project_path=tmp_path,
        )

        assert logger is not None
        assert logger.name == "claude_indexer"


class TestJSONFormatter:
    """Tests for JSON log formatter."""

    def test_basic_format(self) -> None:
        """Test basic JSON formatting."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert data["message"] == "Test message"
        assert data["level"] == "INFO"
        assert "timestamp" in data
        assert data["logger"] == "test.logger"
        assert data["line"] == 10

    def test_extra_fields(self) -> None:
        """Test that extra fields are included in JSON output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Timed operation",
            args=(),
            exc_info=None,
        )
        record.duration_ms = 123.45
        record.operation = "embed"
        record.file_path = "/path/to/file.py"

        output = formatter.format(record)
        data = json.loads(output)

        assert data["duration_ms"] == 123.45
        assert data["operation"] == "embed"
        assert data["file_path"] == "/path/to/file.py"

    def test_exception_formatting(self) -> None:
        """Test exception info is included in JSON."""
        formatter = JSONFormatter()

        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        output = formatter.format(record)
        data = json.loads(output)

        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "Test error" in data["exception"]


class TestPerformanceDecorators:
    """Tests for performance timing utilities."""

    def test_timed_decorator(self, tmp_path: Path) -> None:
        """Test @timed decorator logs timing."""
        log_file = tmp_path / "perf.log"
        setup_logging(log_file=log_file, verbose=True)

        @timed("test_operation")
        def slow_function() -> str:
            time.sleep(0.01)
            return "done"

        result = slow_function()

        assert result == "done"
        content = log_file.read_text()
        assert "[PERF]" in content
        assert "test_operation" in content
        assert "completed" in content

    def test_timed_decorator_uses_function_name(self, tmp_path: Path) -> None:
        """Test @timed uses function name if no operation_name given."""
        log_file = tmp_path / "perf2.log"
        setup_logging(log_file=log_file, verbose=True)

        @timed()
        def my_special_function() -> str:
            return "done"

        my_special_function()

        content = log_file.read_text()
        assert "my_special_function" in content

    def test_timed_decorator_on_exception(self, tmp_path: Path) -> None:
        """Test @timed logs error on exception."""
        log_file = tmp_path / "perf3.log"
        setup_logging(log_file=log_file, verbose=True)

        @timed("failing_op")
        def failing_function() -> None:
            raise ValueError("Intentional error")

        with pytest.raises(ValueError):
            failing_function()

        content = log_file.read_text()
        assert "[PERF]" in content
        assert "failing_op" in content
        assert "failed" in content

    def test_performance_timer_context(self) -> None:
        """Test PerformanceTimer context manager."""
        with PerformanceTimer("test_op", auto_log=False) as timer:
            time.sleep(0.01)

        assert timer.duration_ms >= 10  # At least 10ms
        assert timer.start_time > 0
        assert timer.end_time > timer.start_time

    def test_performance_timer_auto_log(self, tmp_path: Path) -> None:
        """Test PerformanceTimer auto-logging."""
        log_file = tmp_path / "timer.log"
        setup_logging(log_file=log_file, verbose=True)

        with PerformanceTimer("timed_block"):
            time.sleep(0.01)

        content = log_file.read_text()
        assert "[PERF]" in content
        assert "timed_block" in content

    def test_performance_aggregator(self) -> None:
        """Test PerformanceAggregator tracks multiple operations."""
        perf = PerformanceAggregator()

        for _ in range(5):
            with perf.track("operation_a"):
                pass
            with perf.track("operation_b"):
                time.sleep(0.001)

        report = perf.report()

        assert "operation_a" in report
        assert "operation_b" in report
        assert report["operation_a"]["count"] == 5
        assert report["operation_b"]["count"] == 5
        assert "avg_ms" in report["operation_a"]
        assert "min_ms" in report["operation_a"]
        assert "max_ms" in report["operation_a"]
        assert "total_ms" in report["operation_a"]

    def test_performance_aggregator_record(self) -> None:
        """Test manual recording of timing."""
        perf = PerformanceAggregator()
        perf.record("manual_op", 100.0)
        perf.record("manual_op", 200.0)
        perf.record("manual_op", 150.0)

        report = perf.report()
        assert report["manual_op"]["count"] == 3
        assert report["manual_op"]["avg_ms"] == 150.0
        assert report["manual_op"]["min_ms"] == 100.0
        assert report["manual_op"]["max_ms"] == 200.0

    def test_performance_aggregator_reset(self) -> None:
        """Test resetting aggregator data."""
        perf = PerformanceAggregator()
        with perf.track("test"):
            pass

        assert len(perf.timings) > 0
        perf.reset()
        assert len(perf.timings) == 0


class TestDebugContext:
    """Tests for debug_context context manager."""

    def test_temporary_debug_level(self, tmp_path: Path) -> None:
        """Test that debug_context temporarily enables debug logging."""
        log_file = tmp_path / "debug_ctx.log"
        setup_logging(log_file=log_file, level="WARNING")

        logger = get_logger()

        with debug_context():
            logger.debug("Inside context - should appear")

        content = log_file.read_text()
        # File handler is always at DEBUG, so message should appear
        assert "Inside context" in content

    def test_debug_context_restores_level(self, tmp_path: Path) -> None:
        """Test that original level is restored after context."""
        setup_logging(level="INFO", enable_file_logging=False)
        logger = get_logger()

        original_level = logger.level

        with debug_context():
            assert logger.level == logging.DEBUG

        # Level should be restored
        assert logger.level == original_level


class TestCategoryLoggers:
    """Tests for category-specific loggers."""

    def test_get_category_logger(self) -> None:
        """Test getting category-specific logger."""
        guard_logger = get_category_logger(LogCategory.GUARD)
        indexer_logger = get_category_logger(LogCategory.INDEXER)
        mcp_logger = get_category_logger(LogCategory.MCP)

        assert guard_logger.name == "claude_indexer.guard"
        assert indexer_logger.name == "claude_indexer.indexer"
        assert mcp_logger.name == "claude_indexer.mcp"

    def test_all_categories_exist(self) -> None:
        """Test that all expected categories are defined."""
        expected = {"indexer", "guard", "mcp", "performance", "watcher", "storage"}
        actual = {cat.value for cat in LogCategory}
        assert actual == expected


class TestLogFileManagement:
    """Tests for log file path and clearing functions."""

    def test_get_default_log_file_with_collection(self, tmp_path: Path) -> None:
        """Test get_default_log_file with collection name."""
        log_path = get_default_log_file(
            collection_name="test-coll", project_path=tmp_path
        )

        assert log_path == tmp_path / "logs" / "test-coll.log"

    def test_get_default_log_file_without_collection(self, tmp_path: Path) -> None:
        """Test get_default_log_file without collection name."""
        log_path = get_default_log_file(project_path=tmp_path)

        assert log_path == tmp_path / "logs" / "claude-indexer.log"

    def test_clear_log_file(self, tmp_path: Path) -> None:
        """Test clear_log_file removes the file."""
        log_path = tmp_path / "logs" / "test.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("test content")

        result = clear_log_file(collection_name="test", project_path=tmp_path)

        assert result is True
        assert not log_path.exists()

    def test_clear_log_file_nonexistent(self, tmp_path: Path) -> None:
        """Test clear_log_file with non-existent file."""
        result = clear_log_file(collection_name="nonexistent", project_path=tmp_path)

        # Should return True (file doesn't exist = already cleared)
        assert result is True

    def test_get_global_log_dir_creates_directory(self) -> None:
        """Test that get_global_log_dir creates the directory."""
        log_dir = get_global_log_dir()

        assert log_dir.exists()
        assert log_dir.is_dir()
        assert log_dir == Path.home() / ".claude-indexer" / "logs"


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with existing code."""

    def test_get_logger_returns_consistent_instance(self) -> None:
        """Test that get_logger returns consistent instance."""
        logger1 = get_logger()
        logger2 = get_logger()

        assert logger1 is logger2
        assert logger1.name == "claude_indexer"

    def test_imports_work(self) -> None:
        """Test that all expected imports work."""
        # These are the imports that existing code uses
        from claude_indexer.indexer_logging import (
            clear_log_file,
            get_default_log_file,
            get_logger,
            setup_logging,
        )

        assert callable(setup_logging)
        assert callable(get_logger)
        assert callable(get_default_log_file)
        assert callable(clear_log_file)

    def test_new_imports_available(self) -> None:
        """Test that new Milestone 0.3 imports work."""
        from claude_indexer.indexer_logging import (
            JSONFormatter,
            LogCategory,
            debug_context,
            get_category_logger,
            get_global_log_dir,
        )

        assert JSONFormatter is not None
        assert LogCategory is not None
        assert callable(debug_context)
        assert callable(get_category_logger)
        assert callable(get_global_log_dir)
        assert callable(setup_multi_component_logging)

    def test_performance_imports(self) -> None:
        """Test that performance module imports work."""
        from claude_indexer.performance import (
            PerformanceAggregator,
            PerformanceTimer,
            timed,
        )

        assert callable(timed)
        assert PerformanceTimer is not None
        assert PerformanceAggregator is not None


class TestLoggingConfig:
    """Tests for LoggingConfig model updates."""

    def test_logging_config_new_fields(self) -> None:
        """Test that LoggingConfig has new Milestone 0.3 fields."""
        from claude_indexer.config.unified_config import LoggingConfig

        config = LoggingConfig()

        # Original fields
        assert config.level == "INFO"
        assert config.verbose is True
        assert config.debug is False
        assert config.log_file is None

        # New Milestone 0.3 fields
        assert config.format == "text"
        assert config.rotation_count == 3
        assert config.max_bytes == 10485760
        assert config.enable_performance_logging is False
        assert config.enable_multi_component is False

    def test_logging_config_custom_values(self) -> None:
        """Test LoggingConfig with custom values."""
        from claude_indexer.config.unified_config import LoggingConfig

        config = LoggingConfig(
            level="DEBUG",
            format="json",
            rotation_count=5,
            max_bytes=5242880,
            enable_performance_logging=True,
        )

        assert config.level == "DEBUG"
        assert config.format == "json"
        assert config.rotation_count == 5
        assert config.max_bytes == 5242880
        assert config.enable_performance_logging is True
