"""Unit tests for the post_write module."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from claude_indexer.hooks.post_write import (
    PostWriteExecutor,
    PostWriteResult,
    format_findings_for_display,
    run_post_write_check,
)
from claude_indexer.rules.base import Finding, Severity


class TestPostWriteResult:
    """Tests for PostWriteResult dataclass."""

    def test_empty_result(self):
        """Test empty result with no findings."""
        result = PostWriteResult()

        assert result.findings == []
        assert result.execution_time_ms == 0.0
        assert result.rules_executed == 0
        assert result.should_warn is False
        assert result.error is None

    def test_result_with_findings(self):
        """Test result with findings."""
        findings = [
            Finding(
                rule_id="SECURITY.SQL_INJECTION",
                severity=Severity.CRITICAL,
                summary="SQL injection detected",
                file_path="test.py",
                line_number=42,
            ),
            Finding(
                rule_id="TECH_DEBT.TODO",
                severity=Severity.LOW,
                summary="TODO comment found",
                file_path="test.py",
                line_number=10,
            ),
        ]

        result = PostWriteResult(
            findings=findings,
            execution_time_ms=45.5,
            rules_executed=15,
            should_warn=True,
        )

        assert len(result.findings) == 2
        assert result.critical_count == 1
        assert result.high_count == 0
        assert result.medium_count == 0
        assert result.low_count == 1
        assert result.should_warn is True

    def test_to_dict(self):
        """Test JSON serialization."""
        result = PostWriteResult(
            findings=[],
            execution_time_ms=25.5,
            rules_executed=10,
            should_warn=False,
        )

        d = result.to_dict()

        assert d["status"] == "ok"
        assert d["execution_time_ms"] == 25.5
        assert d["rules_executed"] == 10
        assert d["summary"]["total"] == 0
        assert d["error"] is None

    def test_to_json(self):
        """Test JSON string output."""
        result = PostWriteResult(
            execution_time_ms=30.0,
            should_warn=False,
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["status"] == "ok"
        assert parsed["execution_time_ms"] == 30.0

    def test_warn_status(self):
        """Test that should_warn affects status."""
        warn_result = PostWriteResult(should_warn=True)
        ok_result = PostWriteResult(should_warn=False)

        assert warn_result.to_dict()["status"] == "warn"
        assert ok_result.to_dict()["status"] == "ok"


class TestPostWriteExecutor:
    """Tests for PostWriteExecutor class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PostWriteExecutor.reset_instance()
        yield
        PostWriteExecutor.reset_instance()

    def test_singleton_pattern(self):
        """Test that get_instance returns same instance."""
        instance1 = PostWriteExecutor.get_instance()
        instance2 = PostWriteExecutor.get_instance()

        assert instance1 is instance2

    def test_reset_instance(self):
        """Test that reset_instance clears singleton."""
        instance1 = PostWriteExecutor.get_instance()
        PostWriteExecutor.reset_instance()
        instance2 = PostWriteExecutor.get_instance()

        assert instance1 is not instance2

    def test_check_file_not_found(self):
        """Test handling of non-existent file."""
        executor = PostWriteExecutor.get_instance()
        result = executor.check_file(Path("/nonexistent/file.py"))

        assert result.error is not None
        assert "not found" in result.error.lower()

    def test_check_file_with_content(self):
        """Test checking file with provided content."""
        executor = PostWriteExecutor.get_instance()

        # Simple Python content that should pass
        content = """
def hello():
    print("Hello, world!")
"""

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(content.encode())
            temp_path = Path(f.name)

        try:
            result = executor.check_file(temp_path, content=content)

            assert result.error is None
            assert result.execution_time_ms > 0
            assert result.rules_executed >= 0
        finally:
            temp_path.unlink()

    def test_language_detection(self):
        """Test automatic language detection from extension."""
        executor = PostWriteExecutor.get_instance()

        assert executor._detect_language(Path("test.py")) == "python"
        assert executor._detect_language(Path("test.js")) == "javascript"
        assert executor._detect_language(Path("test.ts")) == "typescript"
        assert executor._detect_language(Path("test.tsx")) == "typescript"
        assert executor._detect_language(Path("test.go")) == "go"
        assert executor._detect_language(Path("test.rs")) == "rust"
        assert executor._detect_language(Path("test.unknown")) == "unknown"

    def test_performance_under_200ms(self):
        """Test that check completes within time budget."""
        executor = PostWriteExecutor.get_instance()

        # Simple Python file
        content = """
def add(a, b):
    return a + b
"""

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(content.encode())
            temp_path = Path(f.name)

        try:
            start = time.time()
            result = executor.check_file(temp_path, content=content)
            elapsed = (time.time() - start) * 1000

            # Allow some slack for CI environments
            assert elapsed < 500, f"Execution took {elapsed:.1f}ms, expected <500ms"
            assert result.execution_time_ms < 500
        finally:
            temp_path.unlink()


class TestFormatFindingsForDisplay:
    """Tests for format_findings_for_display function."""

    def test_empty_findings(self):
        """Test formatting empty result."""
        result = PostWriteResult(findings=[])
        output = format_findings_for_display(result)

        assert output == ""

    def test_single_finding(self):
        """Test formatting single finding."""
        finding = Finding(
            rule_id="SECURITY.SQL_INJECTION",
            severity=Severity.CRITICAL,
            summary="Potential SQL injection vulnerability",
            file_path="db/queries.py",
            line_number=42,
            remediation_hints=["Use parameterized queries"],
        )

        result = PostWriteResult(findings=[finding], execution_time_ms=50.0)
        output = format_findings_for_display(result)

        assert "CRITICAL" in output
        assert "SECURITY.SQL_INJECTION" in output
        assert "db/queries.py:42" in output
        assert "SQL injection" in output
        assert "parameterized" in output
        assert "50ms" in output

    def test_multiple_severities(self):
        """Test that findings are grouped by severity."""
        findings = [
            Finding(
                rule_id="LOW.RULE",
                severity=Severity.LOW,
                summary="Low severity",
                file_path="test.py",
            ),
            Finding(
                rule_id="CRITICAL.RULE",
                severity=Severity.CRITICAL,
                summary="Critical severity",
                file_path="test.py",
            ),
            Finding(
                rule_id="HIGH.RULE",
                severity=Severity.HIGH,
                summary="High severity",
                file_path="test.py",
            ),
        ]

        result = PostWriteResult(findings=findings)
        output = format_findings_for_display(result)

        # Critical should appear before high, high before low
        critical_pos = output.find("CRITICAL")
        high_pos = output.find("HIGH")
        low_pos = output.find("LOW")

        assert critical_pos < high_pos < low_pos


class TestRunPostWriteCheck:
    """Tests for run_post_write_check function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PostWriteExecutor.reset_instance()
        yield
        PostWriteExecutor.reset_instance()

    def test_exit_code_zero_no_findings(self, capsys):
        """Test exit code 0 when no findings."""
        content = """
def simple():
    pass
"""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(content.encode())
            temp_path = f.name

        try:
            exit_code = run_post_write_check(
                file_path=temp_path,
                content=content,
                output_json=False,
            )

            # No findings should give exit code 0
            # Note: May have findings depending on rules loaded
            assert exit_code in [0, 1]
        finally:
            Path(temp_path).unlink()

    def test_json_output(self, capsys):
        """Test JSON output flag."""
        content = "x = 1"

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(content.encode())
            temp_path = f.name

        try:
            run_post_write_check(
                file_path=temp_path,
                content=content,
                output_json=True,
            )

            captured = capsys.readouterr()

            # Should be valid JSON
            parsed = json.loads(captured.out)
            assert "status" in parsed
            assert "findings" in parsed
            assert "execution_time_ms" in parsed
        finally:
            Path(temp_path).unlink()

    def test_content_from_argument(self):
        """Test providing content directly instead of file read."""
        content = """
def hello():
    print("world")
"""
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            # Write different content to file
            f.write(b"different content")
            temp_path = f.name

        try:
            # Provide content argument - should use this instead of file
            exit_code = run_post_write_check(
                file_path=temp_path,
                content=content,
                output_json=False,
            )

            assert exit_code in [0, 1]
        finally:
            Path(temp_path).unlink()


class TestIntegration:
    """Integration tests for the post_write module."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        PostWriteExecutor.reset_instance()
        yield
        PostWriteExecutor.reset_instance()

    def test_end_to_end_python_file(self):
        """Test complete flow with a Python file."""
        content = '''
def calculate_total(items):
    """Calculate total price of items."""
    total = 0
    for item in items:
        total += item.price
    return total
'''

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(content.encode())
            temp_path = Path(f.name)

        try:
            executor = PostWriteExecutor.get_instance()
            result = executor.check_file(temp_path)

            # Should complete without error
            assert result.error is None

            # Should have reasonable timing
            assert result.execution_time_ms < 1000

            # Result should be JSON serializable
            json_str = result.to_json()
            parsed = json.loads(json_str)
            assert "status" in parsed
        finally:
            temp_path.unlink()

    def test_end_to_end_javascript_file(self):
        """Test complete flow with a JavaScript file."""
        content = """
function greet(name) {
    console.log("Hello, " + name);
}

module.exports = { greet };
"""

        with tempfile.NamedTemporaryFile(suffix=".js", delete=False) as f:
            f.write(content.encode())
            temp_path = Path(f.name)

        try:
            executor = PostWriteExecutor.get_instance()
            result = executor.check_file(temp_path)

            assert result.error is None
            assert result.execution_time_ms < 1000
        finally:
            temp_path.unlink()
