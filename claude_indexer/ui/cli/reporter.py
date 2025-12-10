"""Output reporters for UI Guard results.

This module provides formatters for outputting UI consistency check results
in different formats suitable for CLI display and Claude Code hook responses.
"""

import json
import sys
from typing import TYPE_CHECKING, Any, TextIO

from ..models import Finding, Severity, UIAnalysisResult

if TYPE_CHECKING:
    from ..ci.audit_runner import CIAuditResult


class CLIReporter:
    """CLI reporter with color-coded output.

    Format: file:line rule_id suggestion
    Colors: red=FAIL, yellow=WARN, blue=INFO

    Example output:
        src/Button.tsx:42 COLOR.NON_TOKEN Hardcoded color #ff6b6b
          -> Use token: --color-error-500 (#ef4444)
        src/Button.tsx:55 SPACING.OFF_SCALE padding: 13px off-scale
          -> Nearest: 12px (scale-12) or 16px (scale-16)

        2 issue(s) in 89ms (1 blocking)
    """

    COLORS = {
        Severity.FAIL: "\033[0;31m",  # Red
        Severity.WARN: "\033[1;33m",  # Yellow
        Severity.INFO: "\033[0;34m",  # Blue
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def __init__(self, stream: TextIO = sys.stderr, use_color: bool | None = None):
        """Initialize the CLI reporter.

        Args:
            stream: Output stream (default: stderr).
            use_color: Whether to use ANSI colors. Auto-detects if None.
        """
        self.stream = stream
        if use_color is None:
            self.use_color = hasattr(stream, "isatty") and stream.isatty()
        else:
            self.use_color = use_color

    def report(self, result: UIAnalysisResult) -> None:
        """Output findings in CLI format.

        Args:
            result: UI analysis result to report.
        """
        if not result.findings:
            self._print_summary(result)
            return

        for finding in result.findings:
            self._report_finding(finding)

        self._print_summary(result)

    def _report_finding(self, finding: Finding) -> None:
        """Output a single finding.

        Args:
            finding: Finding to output.
        """
        location = self._format_location(finding)
        color = self.COLORS.get(finding.severity, "")
        reset = self.RESET if self.use_color else ""
        dim = self.DIM if self.use_color else ""

        if self.use_color:
            line = f"{color}{location} {finding.rule_id}{reset} {finding.summary}"
        else:
            line = f"{location} {finding.rule_id} {finding.summary}"

        print(line, file=self.stream)

        # Add remediation hints
        for hint in finding.remediation_hints:
            if self.use_color:
                print(f"  {dim}-> {hint}{reset}", file=self.stream)
            else:
                print(f"  -> {hint}", file=self.stream)

    def _format_location(self, finding: Finding) -> str:
        """Format file:line location.

        Args:
            finding: Finding to get location from.

        Returns:
            Formatted location string.
        """
        if finding.source_ref:
            return f"{finding.source_ref.file_path}:{finding.source_ref.start_line}"
        return "unknown"

    def _print_summary(self, result: UIAnalysisResult) -> None:
        """Output summary line.

        Args:
            result: UI analysis result to summarize.
        """
        total = len(result.findings)
        time_ms = result.analysis_time_ms

        if total == 0:
            summary = f"\nNo issues found ({time_ms:.0f}ms)"
        else:
            summary = f"\n{total} issue(s) in {time_ms:.0f}ms"
            if result.fail_count > 0:
                summary += f" ({result.fail_count} blocking)"

        print(summary, file=self.stream)

    def report_ci_result(self, result: "CIAuditResult") -> None:
        """Output CI audit findings with baseline separation.

        Args:
            result: CI audit result to report.
        """
        reset = self.RESET if self.use_color else ""
        dim = self.DIM if self.use_color else ""

        # Header
        print(f"\n{'='*60}", file=self.stream)
        print("UI Quality Gate Results", file=self.stream)
        print(f"{'='*60}", file=self.stream)

        # Stats
        print(f"\nAnalysis time: {result.analysis_time_ms:.0f}ms", file=self.stream)
        print(f"Files analyzed: {result.files_analyzed}", file=self.stream)
        print(f"Cache hit rate: {result.cache_hit_rate:.1%}", file=self.stream)

        # New findings (blocking)
        if result.new_findings:
            print(f"\n{'='*40}", file=self.stream)
            print(f"NEW FINDINGS ({len(result.new_findings)})", file=self.stream)
            print(f"{'='*40}", file=self.stream)
            for finding in result.new_findings:
                self._report_finding(finding)

        # Baseline findings (informational)
        if result.baseline_findings:
            print(f"\n{dim}{'='*40}{reset}", file=self.stream)
            print(
                f"{dim}BASELINE FINDINGS ({len(result.baseline_findings)}) - not blocking{reset}",
                file=self.stream,
            )
            print(f"{dim}{'='*40}{reset}", file=self.stream)

            # Group by rule for brevity
            rules: dict[str, int] = {}
            for finding in result.baseline_findings:
                rules[finding.rule_id] = rules.get(finding.rule_id, 0) + 1

            for rule_id, count in sorted(rules.items(), key=lambda x: -x[1]):
                print(f"{dim}  {rule_id}: {count} issue(s){reset}", file=self.stream)

        # Cross-file duplicates
        if result.cross_file_clusters and result.cross_file_clusters.cross_file_duplicates:
            dups = result.cross_file_clusters.cross_file_duplicates
            print(f"\n{'='*40}", file=self.stream)
            print(f"CROSS-FILE DUPLICATES ({len(dups)})", file=self.stream)
            print(f"{'='*40}", file=self.stream)

            for dup in dups[:10]:  # Show top 10
                files_str = ", ".join(dup.details.get("unique_files", [])[:3])
                if len(dup.details.get("unique_files", [])) > 3:
                    files_str += "..."
                print(
                    f"  [{dup.duplicate_type}] {dup.recommended_action}: "
                    f"{dup.details.get('cluster_size', 0)} items across {files_str}",
                    file=self.stream,
                )

        # Cleanup map
        if result.cleanup_map and result.cleanup_map.items:
            cmap = result.cleanup_map
            print(f"\n{'='*40}", file=self.stream)
            print(f"CLEANUP MAP ({cmap.total_baseline_issues} total issues)", file=self.stream)
            print(f"Estimated effort: {cmap.estimated_total_effort}", file=self.stream)
            print(f"{'='*40}", file=self.stream)

            for item in cmap.items[:5]:  # Top 5
                print(
                    f"  P{item.priority}: [{item.rule_id}] {item.count} issues "
                    f"({item.estimated_effort} effort)",
                    file=self.stream,
                )
                if item.suggested_approach:
                    print(f"       -> {item.suggested_approach}", file=self.stream)

        # Final verdict
        print(f"\n{'='*60}", file=self.stream)
        if result.should_fail:
            color = self.COLORS.get(Severity.FAIL, "")
            print(f"{color}FAILED{reset} - {len(result.new_findings)} new blocking issues", file=self.stream)
        else:
            print(f"\033[0;32mPASSED{reset}", file=self.stream)
        print(f"{'='*60}\n", file=self.stream)


class JSONReporter:
    """JSON reporter for Claude Code agent consumption.

    Output format compatible with Claude Code hook response schema:
    {
        "decision": "approve" | "block",
        "reason": "summary",
        "findings": [...],  # Full Finding objects
        "analysis_time_ms": float,
        "files_analyzed": [...],
        "tier": int,
        "counts": {
            "fail": int,
            "warn": int,
            "info": int
        }
    }
    """

    def __init__(self, stream: TextIO = sys.stdout):
        """Initialize the JSON reporter.

        Args:
            stream: Output stream (default: stdout).
        """
        self.stream = stream

    def report(self, result: UIAnalysisResult) -> dict[str, Any]:
        """Output findings as JSON.

        Args:
            result: UI analysis result to report.

        Returns:
            The output dictionary (also written to stream).
        """
        output = {
            "decision": "block" if result.should_block() else "approve",
            "reason": self._build_reason(result),
            "findings": [f.to_dict() for f in result.findings],
            "analysis_time_ms": result.analysis_time_ms,
            "files_analyzed": result.files_analyzed,
            "tier": result.tier,
            "counts": {
                "fail": result.fail_count,
                "warn": result.warn_count,
                "info": result.info_count,
            },
        }

        json.dump(output, self.stream)
        return output

    def _build_reason(self, result: UIAnalysisResult) -> str:
        """Build human-readable reason summary.

        Args:
            result: UI analysis result to summarize.

        Returns:
            Human-readable summary string.
        """
        if result.fail_count == 0:
            if result.warn_count == 0 and result.info_count == 0:
                return "UI checks passed"
            return f"UI checks passed ({result.warn_count} warnings, {result.info_count} info)"

        # Summarize blocking issues
        fail_rules = [f.rule_id for f in result.findings if f.severity == Severity.FAIL]
        unique_rules = list(dict.fromkeys(fail_rules))  # Preserve order, remove dupes

        if len(unique_rules) == 1:
            return f"Blocked: {unique_rules[0]} violation"
        elif len(unique_rules) <= 3:
            return f"Blocked: {len(unique_rules)} rule violations ({', '.join(unique_rules)})"
        else:
            return f"Blocked: {len(unique_rules)} rule violations ({', '.join(unique_rules[:3])}...)"

    def report_ci_result(self, result: "CIAuditResult") -> dict[str, Any]:
        """Output CI audit findings as JSON with baseline separation.

        Args:
            result: CI audit result to report.

        Returns:
            The output dictionary (also written to stream).
        """
        # Count by severity for new findings
        new_fail = sum(1 for f in result.new_findings if f.severity == Severity.FAIL)
        new_warn = sum(1 for f in result.new_findings if f.severity == Severity.WARN)
        new_info = sum(1 for f in result.new_findings if f.severity == Severity.INFO)

        # Build output structure
        output: dict[str, Any] = {
            "decision": "block" if result.should_fail else "approve",
            "reason": self._build_ci_reason(result),
            "tier": result.tier,
            "analysis_time_ms": result.analysis_time_ms,
            "files_analyzed": result.files_analyzed,
            "cache_hit_rate": result.cache_hit_rate,
            "new_findings": [f.to_dict() for f in result.new_findings],
            "baseline_findings": [f.to_dict() for f in result.baseline_findings],
            "counts": {
                "new": {
                    "total": len(result.new_findings),
                    "fail": new_fail,
                    "warn": new_warn,
                    "info": new_info,
                },
                "baseline": {
                    "total": len(result.baseline_findings),
                },
            },
        }

        # Add cross-file clusters if available
        if result.cross_file_clusters:
            output["cross_file_clusters"] = result.cross_file_clusters.to_dict()

        # Add cleanup map if available
        if result.cleanup_map:
            output["cleanup_map"] = result.cleanup_map.to_dict()

        json.dump(output, self.stream, indent=2)
        return output

    def _build_ci_reason(self, result: "CIAuditResult") -> str:
        """Build reason summary for CI audit result.

        Args:
            result: CI audit result to summarize.

        Returns:
            Human-readable summary string.
        """
        if not result.should_fail:
            if len(result.new_findings) == 0:
                if len(result.baseline_findings) > 0:
                    return f"UI checks passed ({len(result.baseline_findings)} baseline issues)"
                return "UI checks passed"
            return f"UI checks passed ({len(result.new_findings)} non-blocking issues)"

        # Count fail severity
        fail_count = sum(1 for f in result.new_findings if f.severity == Severity.FAIL)
        fail_rules = list(set(
            f.rule_id for f in result.new_findings if f.severity == Severity.FAIL
        ))

        if len(fail_rules) == 1:
            return f"Blocked: {fail_count} {fail_rules[0]} violation(s)"
        elif len(fail_rules) <= 3:
            return f"Blocked: {fail_count} violation(s) ({', '.join(fail_rules)})"
        else:
            return f"Blocked: {fail_count} violation(s) across {len(fail_rules)} rules"
