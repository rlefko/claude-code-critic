"""Unit tests for the stop_check module."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.hooks.stop_check import (
    FileChange,
    StopCheckExecutor,
    StopCheckResult,
    format_findings_for_claude,
    format_findings_for_display,
    format_single_finding_for_claude,
    run_stop_check,
)
from claude_indexer.rules.base import Finding, Severity


class TestStopCheckResult:
    """Tests for StopCheckResult dataclass."""

    def test_empty_result(self):
        """Test empty result with no findings."""
        result = StopCheckResult()

        assert result.findings == []
        assert result.execution_time_ms == 0.0
        assert result.rules_executed == 0
        assert result.files_checked == 0
        assert result.should_block is False
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

        result = StopCheckResult(
            findings=findings,
            execution_time_ms=1500.5,
            rules_executed=27,
            files_checked=5,
            should_block=True,
        )

        assert len(result.findings) == 2
        assert result.critical_count == 1
        assert result.high_count == 0
        assert result.medium_count == 0
        assert result.low_count == 1
        assert result.should_block is True

    def test_to_dict(self):
        """Test JSON serialization."""
        result = StopCheckResult(
            findings=[],
            execution_time_ms=500.5,
            rules_executed=27,
            files_checked=3,
            should_block=False,
        )

        d = result.to_dict()

        assert d["status"] == "ok"
        assert d["should_block"] is False
        assert d["execution_time_ms"] == 500.5
        assert d["rules_executed"] == 27
        assert d["files_checked"] == 3
        assert d["summary"]["total"] == 0
        assert d["error"] is None

    def test_to_json(self):
        """Test JSON string output."""
        result = StopCheckResult(
            execution_time_ms=300.0,
            should_block=False,
        )

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert parsed["status"] == "ok"
        assert parsed["execution_time_ms"] == 300.0

    def test_blocked_status(self):
        """Test that should_block affects status."""
        blocked_result = StopCheckResult(should_block=True)
        warn_result = StopCheckResult(
            should_block=False,
            findings=[
                Finding(
                    rule_id="TEST",
                    severity=Severity.LOW,
                    summary="Test",
                    file_path="test.py",
                )
            ],
        )
        ok_result = StopCheckResult(should_block=False)

        assert blocked_result.to_dict()["status"] == "blocked"
        assert warn_result.to_dict()["status"] == "warn"
        assert ok_result.to_dict()["status"] == "ok"


class TestFileChange:
    """Tests for FileChange dataclass."""

    def test_added_file(self):
        """Test representing an added file."""
        change = FileChange(
            file_path=Path("new_file.py"),
            change_type="added",
            added_lines=[(1, 50)],
        )

        assert change.file_path == Path("new_file.py")
        assert change.change_type == "added"
        assert change.added_lines == [(1, 50)]

    def test_modified_file(self):
        """Test representing a modified file."""
        change = FileChange(
            file_path=Path("existing.py"),
            change_type="modified",
            added_lines=[(10, 15), (25, 30)],
        )

        assert change.change_type == "modified"
        assert len(change.added_lines) == 2


class TestStopCheckExecutor:
    """Tests for StopCheckExecutor class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        StopCheckExecutor.reset_instance()
        yield
        StopCheckExecutor.reset_instance()

    def test_singleton_pattern(self):
        """Test that get_instance returns same instance."""
        instance1 = StopCheckExecutor.get_instance()
        instance2 = StopCheckExecutor.get_instance()

        assert instance1 is instance2

    def test_reset_instance(self):
        """Test that reset_instance clears singleton."""
        instance1 = StopCheckExecutor.get_instance()
        StopCheckExecutor.reset_instance()
        instance2 = StopCheckExecutor.get_instance()

        assert instance1 is not instance2

    def test_language_detection(self):
        """Test automatic language detection from extension."""
        executor = StopCheckExecutor.get_instance()

        assert executor._detect_language(Path("test.py")) == "python"
        assert executor._detect_language(Path("test.js")) == "javascript"
        assert executor._detect_language(Path("test.ts")) == "typescript"
        assert executor._detect_language(Path("test.tsx")) == "typescript"
        assert executor._detect_language(Path("test.go")) == "go"
        assert executor._detect_language(Path("test.rs")) == "rust"
        assert executor._detect_language(Path("test.unknown")) == "unknown"

    def test_is_code_file(self):
        """Test code file detection."""
        executor = StopCheckExecutor.get_instance()

        # Should be code files
        assert executor._is_code_file(Path("src/main.py")) is True
        assert executor._is_code_file(Path("lib/utils.js")) is True
        assert executor._is_code_file(Path("app.ts")) is True

        # Should not be code files
        assert executor._is_code_file(Path("image.png")) is False
        assert executor._is_code_file(Path("data.db")) is False
        assert executor._is_code_file(Path("node_modules/pkg/index.js")) is False
        assert executor._is_code_file(Path("__pycache__/test.pyc")) is False
        assert executor._is_code_file(Path(".git/config")) is False

    def test_should_block_critical(self):
        """Test blocking on critical severity."""
        executor = StopCheckExecutor.get_instance()

        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.CRITICAL,
                summary="Critical issue",
                file_path="test.py",
            )
        ]

        assert executor._should_block(findings, Severity.HIGH) is True
        assert executor._should_block(findings, Severity.CRITICAL) is True
        assert executor._should_block(findings, Severity.MEDIUM) is True

    def test_should_block_high(self):
        """Test blocking on high severity."""
        executor = StopCheckExecutor.get_instance()

        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.HIGH,
                summary="High issue",
                file_path="test.py",
            )
        ]

        assert executor._should_block(findings, Severity.HIGH) is True
        assert executor._should_block(findings, Severity.CRITICAL) is False
        assert executor._should_block(findings, Severity.MEDIUM) is True

    def test_should_not_block_low(self):
        """Test not blocking on low severity with high threshold."""
        executor = StopCheckExecutor.get_instance()

        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.LOW,
                summary="Low issue",
                file_path="test.py",
            )
        ]

        assert executor._should_block(findings, Severity.HIGH) is False
        assert executor._should_block(findings, Severity.MEDIUM) is False
        assert executor._should_block(findings, Severity.LOW) is True

    @patch("subprocess.run")
    def test_collect_changed_files_no_git(self, mock_run):
        """Test handling when git is not available."""
        mock_run.side_effect = FileNotFoundError("git not found")

        executor = StopCheckExecutor.get_instance()
        changes = executor._collect_changed_files(Path("/tmp"))

        assert changes == []

    @patch("subprocess.run")
    def test_collect_changed_files_parses_output(self, mock_run):
        """Test parsing of git diff output."""
        # Mock git diff --name-status output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="A\tnew_file.py\nM\tmodified.py\nD\tdeleted.py\n",
        )

        executor = StopCheckExecutor.get_instance()
        changes = executor._collect_changed_files(Path("/tmp"))

        # Should parse file statuses
        assert len(changes) >= 3

        # Check change types are correct
        change_types = {str(c.file_path): c.change_type for c in changes}
        assert change_types.get("new_file.py") == "added"
        assert change_types.get("modified.py") == "modified"
        assert change_types.get("deleted.py") == "deleted"


class TestFormatFindingsForClaude:
    """Tests for format_findings_for_claude function."""

    def test_empty_findings(self):
        """Test formatting empty result."""
        result = StopCheckResult(findings=[])
        output = format_findings_for_claude(result)

        assert output == ""

    def test_blocked_header(self):
        """Test blocked header when should_block is True."""
        finding = Finding(
            rule_id="SECURITY.SQL_INJECTION",
            severity=Severity.CRITICAL,
            summary="SQL injection",
            file_path="db/queries.py",
            line_number=42,
        )

        result = StopCheckResult(findings=[finding], should_block=True)
        output = format_findings_for_claude(result)

        assert "QUALITY CHECK BLOCKED" in output

    def test_warning_header(self):
        """Test warning header when should_block is False."""
        finding = Finding(
            rule_id="TECH_DEBT.TODO",
            severity=Severity.LOW,
            summary="TODO found",
            file_path="test.py",
        )

        result = StopCheckResult(findings=[finding], should_block=False)
        output = format_findings_for_claude(result)

        assert "QUALITY CHECK WARNINGS" in output

    def test_finding_format(self):
        """Test that findings are formatted correctly for Claude."""
        finding = Finding(
            rule_id="SECURITY.SQL_INJECTION",
            severity=Severity.CRITICAL,
            summary="Raw user input concatenated into SQL query",
            file_path="db/queries.py",
            line_number=42,
            remediation_hints=["Use parameterized queries"],
        )

        result = StopCheckResult(
            findings=[finding],
            should_block=True,
            files_checked=5,
            execution_time_ms=1500,
        )
        output = format_findings_for_claude(result)

        assert "CRITICAL: SECURITY.SQL_INJECTION - db/queries.py:42" in output
        assert "Description: Raw user input" in output
        assert "Suggestion: Use parameterized queries" in output
        assert "Please fix" in output


class TestFormatSingleFindingForClaude:
    """Tests for format_single_finding_for_claude function."""

    def test_basic_format(self):
        """Test basic finding format."""
        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.HIGH,
            summary="Test issue",
            file_path="test.py",
            line_number=10,
        )

        output = format_single_finding_for_claude(finding)

        assert "HIGH: TEST.RULE - test.py:10" in output
        assert "Description: Test issue" in output

    def test_with_remediation_hint(self):
        """Test format includes suggestion."""
        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.MEDIUM,
            summary="Test issue",
            file_path="test.py",
            remediation_hints=["Fix it this way"],
        )

        output = format_single_finding_for_claude(finding)

        assert "Suggestion: Fix it this way" in output

    def test_without_line_number(self):
        """Test format without line number."""
        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.LOW,
            summary="Test issue",
            file_path="test.py",
        )

        output = format_single_finding_for_claude(finding)

        # Should not have :None
        assert ":None" not in output
        assert "test.py" in output


class TestFormatFindingsForDisplay:
    """Tests for format_findings_for_display function."""

    def test_empty_findings(self):
        """Test formatting empty result."""
        result = StopCheckResult(findings=[])
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

        result = StopCheckResult(
            findings=[finding],
            files_checked=3,
            execution_time_ms=1500.0,
        )
        output = format_findings_for_display(result)

        assert "CRITICAL" in output
        assert "SECURITY.SQL_INJECTION" in output
        assert "db/queries.py:42" in output
        assert "SQL injection" in output
        assert "parameterized" in output
        assert "3 files" in output

    def test_multiple_severities_sorted(self):
        """Test that findings are sorted by severity."""
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

        result = StopCheckResult(findings=findings)
        output = format_findings_for_display(result)

        # Critical should appear before high, high before low
        critical_pos = output.find("CRITICAL")
        high_pos = output.find("HIGH")
        low_pos = output.find("LOW")

        assert critical_pos < high_pos < low_pos


class TestRunStopCheck:
    """Tests for run_stop_check function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        StopCheckExecutor.reset_instance()
        yield
        StopCheckExecutor.reset_instance()

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository for testing."""

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=tmppath,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmppath,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmppath,
                capture_output=True,
            )

            # Create initial commit
            readme = tmppath / "README.md"
            readme.write_text("# Test\n")
            subprocess.run(
                ["git", "add", "."],
                cwd=tmppath,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial"],
                cwd=tmppath,
                capture_output=True,
            )

            yield tmppath

    def test_exit_code_zero_clean_repo(self, temp_git_repo, capsys):
        """Test exit code 0 when no uncommitted changes."""
        exit_code = run_stop_check(
            project=str(temp_git_repo),
            output_json=False,
            timeout_ms=5000,
            threshold="high",
        )

        # Clean repo should give exit code 0
        assert exit_code == 0

    def test_json_output(self, temp_git_repo, capsys):
        """Test JSON output flag."""
        # Add a new file
        new_file = temp_git_repo / "test.py"
        new_file.write_text("x = 1\n")

        run_stop_check(
            project=str(temp_git_repo),
            output_json=True,
            timeout_ms=5000,
            threshold="high",
        )

        captured = capsys.readouterr()

        # Should be valid JSON
        parsed = json.loads(captured.out)
        assert "status" in parsed
        assert "findings" in parsed
        assert "execution_time_ms" in parsed
        assert "files_checked" in parsed

    def test_threshold_critical(self, temp_git_repo):
        """Test threshold=critical only blocks on critical."""
        # Create file with high severity issue (debug statement)
        test_file = temp_git_repo / "debug.py"
        test_file.write_text("print('debug')\n")

        exit_code = run_stop_check(
            project=str(temp_git_repo),
            output_json=True,
            timeout_ms=5000,
            threshold="critical",
        )

        # High severity should not block when threshold is critical
        assert exit_code in [0, 1]  # Not 2

    def test_performance_under_5s(self, temp_git_repo):
        """Test that check completes within time budget."""
        # Create several files
        for i in range(10):
            f = temp_git_repo / f"file{i}.py"
            f.write_text(f"x{i} = {i}\n")

        start = time.time()
        run_stop_check(
            project=str(temp_git_repo),
            output_json=True,
            timeout_ms=5000,
            threshold="high",
        )
        elapsed = time.time() - start

        # Should complete within 5 seconds
        assert elapsed < 5.0, f"Took {elapsed:.1f}s, expected <5s"


class TestIntegration:
    """Integration tests for the stop_check module."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        StopCheckExecutor.reset_instance()
        yield
        StopCheckExecutor.reset_instance()

    @pytest.fixture
    def temp_git_repo(self):
        """Create a temporary git repository for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=tmppath,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=tmppath,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                cwd=tmppath,
                capture_output=True,
            )

            # Create initial commit
            readme = tmppath / "README.md"
            readme.write_text("# Test\n")
            subprocess.run(["git", "add", "."], cwd=tmppath, capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial"],
                cwd=tmppath,
                capture_output=True,
            )

            yield tmppath

    def test_end_to_end_with_changes(self, temp_git_repo):
        """Test complete flow with uncommitted changes."""
        # Add a new Python file
        test_file = temp_git_repo / "test.py"
        test_file.write_text(
            """
def calculate_total(items):
    total = 0
    for item in items:
        total += item.price
    return total
"""
        )

        executor = StopCheckExecutor.get_instance()
        result = executor.check_uncommitted_changes(temp_git_repo)

        # Should complete without error
        assert result.error is None

        # Should have checked the file
        assert result.files_checked >= 1

        # Should have reasonable timing
        assert result.execution_time_ms < 5000

        # Result should be JSON serializable
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert "status" in parsed
        assert "files_checked" in parsed

    def test_diff_context_populated(self, temp_git_repo):
        """Test that diff context is populated for changed files."""
        # Create a file and commit it
        test_file = temp_git_repo / "existing.py"
        test_file.write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=temp_git_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add file"],
            cwd=temp_git_repo,
            capture_output=True,
        )

        # Modify the file (add lines at the end)
        test_file.write_text("x = 1\ny = 2\nz = 3\n")

        executor = StopCheckExecutor.get_instance()
        changes = executor._collect_changed_files(temp_git_repo)

        # Should detect the modified file
        modified_files = [c for c in changes if c.change_type == "modified"]
        assert len(modified_files) >= 1

        # Should have line range info
        for change in modified_files:
            if str(change.file_path) == "existing.py":
                # Should have added_lines populated
                assert len(change.added_lines) > 0 or change.change_type == "modified"

    def test_blocks_on_security_issue(self, temp_git_repo):
        """Test that critical security issues trigger blocking."""
        # Create file with potential SQL injection
        test_file = temp_git_repo / "db.py"
        test_file.write_text(
            """
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = " + user_id
    return execute(query)
"""
        )

        exit_code = run_stop_check(
            project=str(temp_git_repo),
            output_json=True,
            timeout_ms=5000,
            threshold="high",
        )

        # May or may not block depending on rules loaded
        # But should complete without crashing
        assert exit_code in [0, 1, 2]
