"""Diff-aware filtering for UI consistency findings.

This module provides functionality to filter findings based on git diff,
separating new issues from baseline issues for progressive adoption.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..models import Finding, Severity

if TYPE_CHECKING:
    from ..collectors.git_diff import DiffResult, GitDiffCollector


@dataclass
class FilterResult:
    """Result of diff-aware filtering.

    Separates findings into new and baseline categories.
    """

    new_findings: list[Finding] = field(default_factory=list)
    baseline_findings: list[Finding] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """Total number of findings."""
        return len(self.new_findings) + len(self.baseline_findings)

    @property
    def new_count(self) -> int:
        """Number of new findings."""
        return len(self.new_findings)

    @property
    def baseline_count(self) -> int:
        """Number of baseline findings."""
        return len(self.baseline_findings)

    @property
    def fail_count(self) -> int:
        """Number of FAIL severity findings (new only)."""
        return sum(1 for f in self.new_findings if f.severity == Severity.FAIL)

    @property
    def should_block(self) -> bool:
        """Whether findings should block the operation."""
        return self.fail_count > 0


class DiffFilter:
    """Filters findings based on git diff scope.

    Separates findings into new issues (from changed code) and
    baseline issues (pre-existing). This enables progressive
    adoption by only failing on new issues.
    """

    def __init__(
        self,
        diff_collector: "GitDiffCollector | None" = None,
        fail_only_on_new: bool = True,
        downgrade_baseline_severity: bool = True,
    ):
        """Initialize the diff filter.

        Args:
            diff_collector: Optional GitDiffCollector for fetching diffs.
            fail_only_on_new: If True, only FAIL on new issues.
            downgrade_baseline_severity: If True, downgrade FAIL to WARN for baseline.
        """
        self.diff_collector = diff_collector
        self.fail_only_on_new = fail_only_on_new
        self.downgrade_baseline_severity = downgrade_baseline_severity

    def filter(
        self,
        findings: list[Finding],
        diff_result: "DiffResult | None" = None,
        diff_mode: str = "staged",
    ) -> FilterResult:
        """Separate findings into new and baseline.

        Args:
            findings: List of findings to filter.
            diff_result: Optional pre-computed diff result.
            diff_mode: Diff mode if computing diff ('staged', 'pr', 'all').

        Returns:
            FilterResult with separated new and baseline findings.
        """
        # Get diff result
        if diff_result is None:
            diff_result = self._get_diff(diff_mode)

        # If no diff available, treat all findings as new
        if diff_result is None:
            for finding in findings:
                finding.is_new = True
            return FilterResult(new_findings=findings, baseline_findings=[])

        # Classify each finding
        new_findings = []
        baseline_findings = []

        for finding in findings:
            if self._is_in_diff_scope(finding, diff_result):
                finding.is_new = True
                new_findings.append(finding)
            else:
                finding.is_new = False

                # Optionally downgrade severity for baseline issues
                if self.downgrade_baseline_severity:
                    if finding.severity == Severity.FAIL:
                        finding.severity = Severity.WARN

                baseline_findings.append(finding)

        return FilterResult(
            new_findings=new_findings,
            baseline_findings=baseline_findings,
        )

    def filter_to_new_only(
        self,
        findings: list[Finding],
        diff_result: "DiffResult | None" = None,
        diff_mode: str = "staged",
    ) -> list[Finding]:
        """Filter to only new findings.

        Convenience method for pre-commit tier where we only
        care about new issues.

        Args:
            findings: List of findings to filter.
            diff_result: Optional pre-computed diff result.
            diff_mode: Diff mode if computing diff.

        Returns:
            List of findings that are new (in diff scope).
        """
        result = self.filter(findings, diff_result, diff_mode)
        return result.new_findings

    def _get_diff(self, diff_mode: str) -> "DiffResult | None":
        """Get diff result based on mode.

        Args:
            diff_mode: One of 'staged', 'pr', 'unstaged', 'all'.

        Returns:
            DiffResult or None if no diff collector.
        """
        if self.diff_collector is None:
            return None

        if diff_mode == "staged":
            return self.diff_collector.collect_staged()
        elif diff_mode == "pr":
            return self.diff_collector.collect_pr_diff()
        elif diff_mode == "unstaged":
            return self.diff_collector.collect_unstaged()
        elif diff_mode == "all":
            return self.diff_collector.collect_all_uncommitted()
        else:
            return self.diff_collector.collect_staged()

    def _is_in_diff_scope(
        self,
        finding: Finding,
        diff_result: "DiffResult",
    ) -> bool:
        """Check if finding's source location is in diff scope.

        Args:
            finding: Finding to check.
            diff_result: Diff result to check against.

        Returns:
            True if finding is in a changed region.
        """
        # No source ref = assume new (conservative)
        if finding.source_ref is None:
            return True

        file_path = finding.source_ref.file_path
        line_number = finding.source_ref.start_line

        # Check if file is in the diff
        for change in diff_result.changes:
            if str(change.file_path) == file_path:
                # For added files, all lines are new
                if change.change_type == "added":
                    return True

                # For modified files, check line ranges
                return change.contains_line(line_number)

        # File not in diff = baseline issue
        return False

    def classify_findings(
        self,
        findings: list[Finding],
        diff_result: "DiffResult | None" = None,
    ) -> dict[str, list[Finding]]:
        """Classify findings by new/baseline status.

        Returns a dict for easy access to both categories.

        Args:
            findings: List of findings to classify.
            diff_result: Optional pre-computed diff result.

        Returns:
            Dict with 'new' and 'baseline' keys.
        """
        result = self.filter(findings, diff_result)
        return {
            "new": result.new_findings,
            "baseline": result.baseline_findings,
        }


def create_diff_filter(
    project_path: str | None = None,
    fail_only_on_new: bool = True,
) -> DiffFilter:
    """Create a diff filter with a git collector.

    Args:
        project_path: Path to git repository.
        fail_only_on_new: Whether to only fail on new issues.

    Returns:
        Configured DiffFilter instance.
    """
    diff_collector = None

    if project_path:
        from pathlib import Path

        from ..collectors.git_diff import GitDiffCollector

        diff_collector = GitDiffCollector(Path(project_path))

    return DiffFilter(
        diff_collector=diff_collector,
        fail_only_on_new=fail_only_on_new,
    )


__all__ = [
    "DiffFilter",
    "FilterResult",
    "create_diff_filter",
]
