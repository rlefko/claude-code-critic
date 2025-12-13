"""Tests for the diff filter module.

Tests the DiffFilter class that separates findings into new
and baseline categories based on git diff scope.
"""

from pathlib import Path

import pytest

from claude_indexer.ui.collectors.git_diff import DiffResult, FileChange
from claude_indexer.ui.models import (
    Finding,
    Severity,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.rules.diff_filter import (
    DiffFilter,
    FilterResult,
    create_diff_filter,
)


@pytest.fixture
def sample_diff_result():
    """Create a sample diff result for testing."""
    return DiffResult(
        changes=[
            FileChange(
                file_path=Path("src/components/Button.tsx"),
                change_type="modified",
                added_lines=[(10, 20), (30, 35)],
                deleted_lines=[(5, 8)],
            ),
            FileChange(
                file_path=Path("src/styles/new.css"),
                change_type="added",
                added_lines=[(1, 50)],
            ),
            FileChange(
                file_path=Path("src/old.css"),
                change_type="deleted",
            ),
        ],
        base_ref="HEAD",
        target_ref="staged",
    )


def create_finding(file_path: str, line: int, rule_id: str = "TEST.RULE") -> Finding:
    """Helper to create test findings."""
    return Finding(
        rule_id=rule_id,
        severity=Severity.WARN,
        confidence=0.9,
        summary=f"Test finding at {file_path}:{line}",
        source_ref=SymbolRef(
            file_path=file_path,
            start_line=line,
            end_line=line,
            kind=SymbolKind.CSS,
            visibility=Visibility.LOCAL,
        ),
    )


class TestDiffFilter:
    """Tests for DiffFilter class."""

    def test_filter_new_in_modified_file(self, sample_diff_result):
        """Test filtering finds new issues in modified files."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/components/Button.tsx", 15),  # In added range
        ]

        result = diff_filter.filter(findings, sample_diff_result)

        assert len(result.new_findings) == 1
        assert len(result.baseline_findings) == 0
        assert result.new_findings[0].is_new is True

    def test_filter_baseline_in_modified_file(self, sample_diff_result):
        """Test filtering identifies baseline issues in unmodified lines."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/components/Button.tsx", 25),  # Not in added range
        ]

        result = diff_filter.filter(findings, sample_diff_result)

        assert len(result.new_findings) == 0
        assert len(result.baseline_findings) == 1
        assert result.baseline_findings[0].is_new is False

    def test_filter_all_new_in_added_file(self, sample_diff_result):
        """Test that all issues in newly added files are new."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/styles/new.css", 5),
            create_finding("src/styles/new.css", 30),
            create_finding("src/styles/new.css", 49),
        ]

        result = diff_filter.filter(findings, sample_diff_result)

        assert len(result.new_findings) == 3
        assert len(result.baseline_findings) == 0

    def test_filter_baseline_in_unchanged_file(self, sample_diff_result):
        """Test that issues in unchanged files are baseline."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/other/unchanged.css", 10),
        ]

        result = diff_filter.filter(findings, sample_diff_result)

        assert len(result.new_findings) == 0
        assert len(result.baseline_findings) == 1

    def test_downgrade_baseline_severity(self, sample_diff_result):
        """Test that FAIL is downgraded to WARN for baseline."""
        diff_filter = DiffFilter(downgrade_baseline_severity=True)

        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="Baseline issue",
            source_ref=SymbolRef(
                file_path="src/unchanged.css",
                start_line=10,
                end_line=10,
                kind=SymbolKind.CSS,
                visibility=Visibility.LOCAL,
            ),
        )

        result = diff_filter.filter([finding], sample_diff_result)

        assert len(result.baseline_findings) == 1
        assert result.baseline_findings[0].severity == Severity.WARN

    def test_no_downgrade_when_disabled(self, sample_diff_result):
        """Test that severity is preserved when downgrade disabled."""
        diff_filter = DiffFilter(downgrade_baseline_severity=False)

        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="Baseline issue",
            source_ref=SymbolRef(
                file_path="src/unchanged.css",
                start_line=10,
                end_line=10,
                kind=SymbolKind.CSS,
                visibility=Visibility.LOCAL,
            ),
        )

        result = diff_filter.filter([finding], sample_diff_result)

        assert result.baseline_findings[0].severity == Severity.FAIL

    def test_no_diff_treats_all_as_new(self):
        """Test that findings are all new when no diff available."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/test.css", 10),
            create_finding("src/test.css", 20),
        ]

        result = diff_filter.filter(findings, diff_result=None)

        assert len(result.new_findings) == 2
        assert len(result.baseline_findings) == 0

    def test_finding_without_source_ref_is_new(self, sample_diff_result):
        """Test that findings without source ref are treated as new."""
        diff_filter = DiffFilter()

        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.WARN,
            confidence=0.9,
            summary="Finding without location",
            source_ref=None,
        )

        result = diff_filter.filter([finding], sample_diff_result)

        assert len(result.new_findings) == 1
        assert len(result.baseline_findings) == 0


class TestFilterResult:
    """Tests for FilterResult dataclass."""

    def test_counts(self):
        """Test count properties."""
        result = FilterResult(
            new_findings=[
                create_finding("a.css", 1),
                create_finding("b.css", 2),
            ],
            baseline_findings=[
                create_finding("c.css", 3),
            ],
        )

        assert result.total_count == 3
        assert result.new_count == 2
        assert result.baseline_count == 1

    def test_fail_count(self):
        """Test fail count calculation."""
        fail_finding = Finding(
            rule_id="TEST",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="Fail",
        )
        warn_finding = Finding(
            rule_id="TEST",
            severity=Severity.WARN,
            confidence=0.9,
            summary="Warn",
        )

        result = FilterResult(
            new_findings=[fail_finding, warn_finding],
        )

        assert result.fail_count == 1

    def test_should_block(self):
        """Test should_block based on FAIL findings."""
        # No fails = should not block
        result1 = FilterResult(
            new_findings=[
                Finding(
                    rule_id="T", severity=Severity.WARN, confidence=0.9, summary="W"
                ),
            ],
        )
        assert result1.should_block is False

        # Has fail = should block
        result2 = FilterResult(
            new_findings=[
                Finding(
                    rule_id="T", severity=Severity.FAIL, confidence=0.9, summary="F"
                ),
            ],
        )
        assert result2.should_block is True


class TestFilterToNewOnly:
    """Tests for filter_to_new_only convenience method."""

    def test_returns_only_new(self, sample_diff_result):
        """Test that only new findings are returned."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/components/Button.tsx", 15),  # New
            create_finding("src/unchanged.css", 10),  # Baseline
        ]

        new_only = diff_filter.filter_to_new_only(findings, sample_diff_result)

        assert len(new_only) == 1
        assert new_only[0].source_ref.file_path == "src/components/Button.tsx"


class TestClassifyFindings:
    """Tests for classify_findings method."""

    def test_returns_dict(self, sample_diff_result):
        """Test that classification returns dict with both keys."""
        diff_filter = DiffFilter()

        findings = [
            create_finding("src/components/Button.tsx", 15),
            create_finding("src/unchanged.css", 10),
        ]

        classified = diff_filter.classify_findings(findings, sample_diff_result)

        assert "new" in classified
        assert "baseline" in classified
        assert len(classified["new"]) == 1
        assert len(classified["baseline"]) == 1


class TestCreateDiffFilter:
    """Tests for create_diff_filter factory function."""

    def test_creates_filter_without_path(self):
        """Test creation without project path."""
        diff_filter = create_diff_filter()

        assert diff_filter is not None
        assert diff_filter.diff_collector is None

    def test_creates_filter_with_path(self, tmp_path):
        """Test creation with project path."""
        # Create a git repo in tmp_path
        (tmp_path / ".git").mkdir()

        diff_filter = create_diff_filter(str(tmp_path))

        assert diff_filter is not None
        assert diff_filter.diff_collector is not None
