"""Unit tests for UI guard."""

import json
from io import StringIO
from pathlib import Path

import pytest

from claude_indexer.ui.cli.guard import UIGuard, is_ui_file, run_guard
from claude_indexer.ui.config import UIQualityConfig


class TestIsUIFile:
    """Tests for is_ui_file function."""

    def test_css_files(self):
        """CSS files should be recognized as UI files."""
        assert is_ui_file("styles.css") is True
        assert is_ui_file("src/components/Button.css") is True
        assert is_ui_file("theme.scss") is True
        assert is_ui_file("variables.sass") is True
        assert is_ui_file("mixins.less") is True

    def test_jsx_tsx_files(self):
        """JSX and TSX files should be recognized as UI files."""
        assert is_ui_file("Button.jsx") is True
        assert is_ui_file("src/components/Card.tsx") is True

    def test_vue_svelte_files(self):
        """Vue and Svelte files should be recognized as UI files."""
        assert is_ui_file("App.vue") is True
        assert is_ui_file("Counter.svelte") is True

    def test_html_files(self):
        """HTML files should be recognized as UI files."""
        assert is_ui_file("index.html") is True
        assert is_ui_file("template.htm") is True

    def test_non_ui_files(self):
        """Non-UI files should not be recognized as UI files."""
        assert is_ui_file("app.py") is False
        assert is_ui_file("server.js") is False
        assert is_ui_file("config.json") is False
        assert is_ui_file("README.md") is False
        assert is_ui_file("Makefile") is False

    def test_path_objects(self):
        """Path objects should work the same as strings."""
        assert is_ui_file(Path("Button.tsx")) is True
        assert is_ui_file(Path("app.py")) is False


class TestUIGuard:
    """Tests for UIGuard class."""

    @pytest.fixture
    def guard(self, tmp_path):
        """Create a UIGuard instance with default config."""
        config = UIQualityConfig()
        return UIGuard(config=config, project_path=tmp_path)

    def test_check_empty_css(self, guard):
        """Empty CSS should produce no findings."""
        result = guard.check_file(Path("test.css"), "", fast_mode=True)

        assert len(result.findings) == 0
        assert result.analysis_time_ms >= 0

    def test_check_simple_css(self, guard):
        """Simple CSS with token values should produce no findings."""
        content = """
        .button {
            padding: 8px;
            margin: 16px;
        }
        """
        result = guard.check_file(Path("test.css"), content, fast_mode=True)

        # No hardcoded colors or off-scale values
        assert result.fail_count == 0

    def test_check_file_includes_path_in_result(self, guard):
        """Result should include the analyzed file path."""
        content = ".test { color: red; }"
        result = guard.check_file(Path("test.css"), content)

        assert "test.css" in result.files_analyzed

    def test_fast_mode_is_default(self, guard):
        """Fast mode should be enabled by default."""
        content = ".button { padding: 8px; }"
        result = guard.check_file(Path("test.css"), content)

        # Fast mode runs tier 0
        assert result.tier == 0


class TestUIGuardHookInput:
    """Tests for UIGuard.check_from_hook_input."""

    @pytest.fixture
    def guard(self, tmp_path):
        """Create a UIGuard instance."""
        config = UIQualityConfig()
        return UIGuard(config=config, project_path=tmp_path)

    def test_write_tool_input(self, guard):
        """Should handle Write tool input."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/styles.css",
                "content": ".button { padding: 8px; }",
            },
            "hook_event_name": "PreToolUse",
        }

        result = guard.check_from_hook_input(hook_input)

        assert "src/styles.css" in result.files_analyzed

    def test_edit_tool_input(self, guard):
        """Should handle Edit tool input."""
        hook_input = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "src/Button.tsx",
                "new_string": 'className="btn-primary"',
            },
            "hook_event_name": "PreToolUse",
        }

        result = guard.check_from_hook_input(hook_input)

        assert "src/Button.tsx" in result.files_analyzed

    def test_skip_non_ui_files(self, guard):
        """Should skip non-UI files."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/server.py",
                "content": "print('hello')",
            },
            "hook_event_name": "PreToolUse",
        }

        result = guard.check_from_hook_input(hook_input)

        # Should return empty result for non-UI files
        assert len(result.findings) == 0
        assert result.analysis_time_ms == 0.0

    def test_skip_unsupported_tools(self, guard):
        """Should skip unsupported tool types."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "ls -la",
            },
            "hook_event_name": "PreToolUse",
        }

        result = guard.check_from_hook_input(hook_input)

        assert len(result.findings) == 0

    def test_empty_content(self, guard):
        """Should handle empty content gracefully."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "src/styles.css",
                "content": "",
            },
            "hook_event_name": "PreToolUse",
        }

        result = guard.check_from_hook_input(hook_input)

        assert result.analysis_time_ms == 0.0


class TestRunGuard:
    """Tests for run_guard function."""

    def test_empty_input(self):
        """Empty input should allow operation."""
        input_stream = StringIO("")
        output_stream = StringIO()
        error_stream = StringIO()

        exit_code = run_guard(
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
        )

        assert exit_code == 0

    def test_invalid_json(self):
        """Invalid JSON should allow operation (fail open)."""
        input_stream = StringIO("not valid json")
        output_stream = StringIO()
        error_stream = StringIO()

        exit_code = run_guard(
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
        )

        assert exit_code == 0

    def test_valid_input_json_output(self, tmp_path):
        """Valid input should produce JSON output."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "test.css",
                "content": ".button { padding: 8px; }",
            },
        }
        input_stream = StringIO(json.dumps(hook_input))
        output_stream = StringIO()
        error_stream = StringIO()

        run_guard(
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
            json_output=True,
            project_path=tmp_path,
        )

        # Should produce valid JSON output
        output = output_stream.getvalue()
        if output:
            result = json.loads(output)
            assert "decision" in result
            assert result["decision"] in ("approve", "block")

    def test_non_ui_file_allows(self, tmp_path):
        """Non-UI files should be allowed."""
        hook_input = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "server.py",
                "content": "print('hello')",
            },
        }
        input_stream = StringIO(json.dumps(hook_input))
        output_stream = StringIO()
        error_stream = StringIO()

        exit_code = run_guard(
            input_stream=input_stream,
            output_stream=output_stream,
            error_stream=error_stream,
            project_path=tmp_path,
        )

        assert exit_code == 0


class TestUIGuardPerformance:
    """Performance tests for UIGuard."""

    @pytest.fixture
    def guard(self, tmp_path):
        """Create a UIGuard instance."""
        config = UIQualityConfig()
        return UIGuard(config=config, project_path=tmp_path)

    def test_fast_mode_timing(self, guard):
        """Fast mode should complete quickly."""
        # Generate some CSS content
        content = "\n".join(
            [
                f".class-{i} {{ padding: {i * 4}px; color: #{i:02x}{i:02x}{i:02x}; }}"
                for i in range(100)
            ]
        )

        result = guard.check_file(Path("test.css"), content, fast_mode=True)

        # Should complete in reasonable time (relaxed for CI)
        assert result.analysis_time_ms < 5000  # 5 seconds max
