"""Tests for CLI output module."""

from __future__ import annotations

import os
from io import StringIO
from unittest.mock import patch

from claude_indexer.cli.output import (
    OutputConfig,
    OutputManager,
    should_use_color,
)


class TestShouldUseColor:
    """Tests for should_use_color function."""

    def test_explicit_flag_true(self):
        """Explicit flag True should force colors."""
        assert should_use_color(explicit_flag=True) is True

    def test_explicit_flag_false(self):
        """Explicit flag False should disable colors."""
        assert should_use_color(explicit_flag=False) is False

    def test_no_color_env_var(self):
        """NO_COLOR env var should disable colors."""
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert should_use_color() is False

    def test_no_color_env_empty(self):
        """Empty NO_COLOR env var should also disable colors."""
        with patch.dict(os.environ, {"NO_COLOR": ""}):
            assert should_use_color() is False

    def test_force_color_env(self):
        """FORCE_COLOR env var should enable colors."""
        with patch.dict(os.environ, {"FORCE_COLOR": "1"}, clear=True):
            assert should_use_color() is True

    def test_non_tty_stream(self):
        """Non-TTY stream should disable colors."""
        stream = StringIO()
        assert should_use_color(stream=stream) is False

    def test_tty_stream(self):
        """TTY stream should enable colors."""
        stream = StringIO()
        stream.isatty = lambda: True
        # Clear env vars that would affect result
        with patch.dict(os.environ, {}, clear=True):
            if "NO_COLOR" in os.environ:
                del os.environ["NO_COLOR"]
            assert should_use_color(stream=stream) is True


class TestOutputConfig:
    """Tests for OutputConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = OutputConfig()
        assert config.use_color is True
        assert config.quiet is False
        assert config.verbose is False

    def test_from_flags_default(self):
        """Test creating config from default flags."""
        config = OutputConfig.from_flags()
        assert config.quiet is False
        assert config.verbose is False

    def test_from_flags_quiet(self):
        """Test creating config with quiet mode."""
        config = OutputConfig.from_flags(quiet=True)
        assert config.quiet is True

    def test_from_flags_verbose(self):
        """Test creating config with verbose mode."""
        config = OutputConfig.from_flags(verbose=True)
        assert config.verbose is True

    def test_from_flags_no_color(self):
        """Test creating config with no_color flag."""
        config = OutputConfig.from_flags(no_color=True)
        assert config.use_color is False


class TestOutputManager:
    """Tests for OutputManager class."""

    def test_init_default(self):
        """Test default initialization."""
        manager = OutputManager()
        assert manager.config is not None

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = OutputConfig(use_color=False, quiet=True)
        manager = OutputManager(config)
        assert manager.config.use_color is False
        assert manager.config.quiet is True

    def test_get_symbol_with_color(self):
        """Test symbol retrieval with colors enabled."""
        config = OutputConfig(use_color=True)
        manager = OutputManager(config)
        symbol = manager._get_symbol("success")
        assert "\033[92m" in symbol  # Green color code

    def test_get_symbol_without_color(self):
        """Test symbol retrieval without colors."""
        config = OutputConfig(use_color=False)
        manager = OutputManager(config)
        symbol = manager._get_symbol("success")
        assert symbol == "[OK]"

    def test_get_symbol_error(self):
        """Test error symbol."""
        config = OutputConfig(use_color=False)
        manager = OutputManager(config)
        assert manager._get_symbol("error") == "[FAIL]"

    def test_get_symbol_warning(self):
        """Test warning symbol."""
        config = OutputConfig(use_color=False)
        manager = OutputManager(config)
        assert manager._get_symbol("warning") == "[WARN]"

    def test_colorize_enabled(self):
        """Test colorize with colors enabled."""
        config = OutputConfig(use_color=True)
        manager = OutputManager(config)
        result = manager._colorize("test", "green")
        assert "\033[92m" in result
        assert "test" in result

    def test_colorize_disabled(self):
        """Test colorize with colors disabled."""
        config = OutputConfig(use_color=False)
        manager = OutputManager(config)
        result = manager._colorize("test", "green")
        assert result == "test"

    def test_success_output(self):
        """Test success output."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.success("Operation completed")
        assert "[OK] Operation completed" in stream.getvalue()

    def test_error_output(self):
        """Test error output."""
        err_stream = StringIO()
        config = OutputConfig(use_color=False, err_stream=err_stream)
        manager = OutputManager(config)
        manager.error("Something failed")
        assert "[FAIL] Something failed" in err_stream.getvalue()

    def test_warning_output(self):
        """Test warning output."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.warning("Watch out")
        assert "[WARN] Watch out" in stream.getvalue()

    def test_info_output(self):
        """Test info output."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.info("FYI")
        assert "[INFO] FYI" in stream.getvalue()

    def test_quiet_mode_suppresses_info(self):
        """Test that quiet mode suppresses info output."""
        stream = StringIO()
        config = OutputConfig(use_color=False, quiet=True, stream=stream)
        manager = OutputManager(config)
        manager.info("Should not appear")
        assert stream.getvalue() == ""

    def test_quiet_mode_shows_errors(self):
        """Test that quiet mode still shows errors."""
        err_stream = StringIO()
        config = OutputConfig(use_color=False, quiet=True, err_stream=err_stream)
        manager = OutputManager(config)
        manager.error("Should appear")
        assert "[FAIL] Should appear" in err_stream.getvalue()

    def test_debug_only_in_verbose(self):
        """Test that debug only outputs in verbose mode."""
        stream = StringIO()
        config = OutputConfig(use_color=False, verbose=False, stream=stream)
        manager = OutputManager(config)
        manager.debug("Debug info")
        assert stream.getvalue() == ""

    def test_debug_in_verbose_mode(self):
        """Test debug output in verbose mode."""
        stream = StringIO()
        config = OutputConfig(use_color=False, verbose=True, stream=stream)
        manager = OutputManager(config)
        manager.debug("Debug info")
        assert "DEBUG:" in stream.getvalue()
        assert "Debug info" in stream.getvalue()

    def test_status_line(self):
        """Test status line formatting."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.status_line("Qdrant", "Connected", "success")
        output = stream.getvalue()
        assert "Qdrant:" in output
        assert "[OK]" in output
        assert "Connected" in output

    def test_header(self):
        """Test header formatting."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.header("Test Header")
        output = stream.getvalue()
        assert "Test Header" in output
        assert "=" in output

    def test_newline(self):
        """Test newline output."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.newline()
        assert stream.getvalue() == "\n"

    def test_newline_suppressed_in_quiet(self):
        """Test newline suppressed in quiet mode."""
        stream = StringIO()
        config = OutputConfig(use_color=False, quiet=True, stream=stream)
        manager = OutputManager(config)
        manager.newline()
        assert stream.getvalue() == ""

    def test_plain_output(self):
        """Test plain output without symbol."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.plain("Plain text")
        assert "Plain text" in stream.getvalue()
        assert "[" not in stream.getvalue()

    def test_summary_success(self):
        """Test summary with success."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.summary(total=10, success=10)
        output = stream.getvalue()
        assert "10 total" in output
        assert "10 successful" in output
        assert "[OK]" in output

    def test_summary_with_failures(self):
        """Test summary with failures."""
        stream = StringIO()
        err_stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream, err_stream=err_stream)
        manager = OutputManager(config)
        manager.summary(total=10, success=8, failed=2)
        # With failures, output may go to either stream
        output = stream.getvalue() + err_stream.getvalue()
        assert "10 total" in output
        assert "2 failed" in output

    def test_summary_with_duration(self):
        """Test summary with duration."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.summary(total=10, success=10, duration_ms=500)
        output = stream.getvalue()
        assert "500ms" in output

    def test_summary_with_long_duration(self):
        """Test summary with long duration."""
        stream = StringIO()
        config = OutputConfig(use_color=False, stream=stream)
        manager = OutputManager(config)
        manager.summary(total=10, success=10, duration_ms=5000)
        output = stream.getvalue()
        assert "5.0s" in output
