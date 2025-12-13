"""
TODO markers detection rule.

Detects TODO, FIXME, HACK, and other marker comments that indicate
technical debt or incomplete work.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class TodoMarkersRule(BaseRule):
    """Detect TODO, FIXME, HACK, and other marker comments."""

    # Marker patterns with their severities
    MARKERS = {
        "TODO": Severity.LOW,
        "FIXME": Severity.HIGH,
        "HACK": Severity.MEDIUM,
        "XXX": Severity.MEDIUM,
        "BUG": Severity.HIGH,
        "DEPRECATED": Severity.MEDIUM,
    }

    # Pattern to match markers with optional ticket reference
    MARKER_PATTERN = re.compile(
        r"(?:#|//|/\*|\*)\s*\b(TODO|FIXME|HACK|XXX|BUG|DEPRECATED)\b"
        r"(?:\s*\(([^)]+)\))?(?:\s*:\s*(.*))?",
        re.IGNORECASE,
    )

    # Pattern for ticket references (e.g., ABC-123, #123)
    TICKET_PATTERN = re.compile(r"[A-Z]+-\d+|#\d+", re.IGNORECASE)

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.TODO_MARKERS"

    @property
    def name(self) -> str:
        return "TODO Markers Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        # Supports all languages (comment-based detection)
        return None

    @property
    def description(self) -> str:
        return (
            "Detects TODO, FIXME, HACK, and other marker comments that "
            "indicate technical debt or incomplete work. FIXME and BUG "
            "markers are treated as high severity."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for TODO markers in the file.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected markers
        """
        findings = []
        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff (when diff info available)
            if not context.is_line_in_diff(line_num):
                continue

            match = self.MARKER_PATTERN.search(line)
            if match:
                marker = match.group(1).upper()
                assignee = match.group(2)  # Optional (username)
                description = match.group(3)  # Optional text after marker

                # Determine severity based on marker type
                severity = self.MARKERS.get(marker, Severity.LOW)

                # Check for ticket reference
                has_ticket = bool(self.TICKET_PATTERN.search(line))

                # Build summary
                summary = f"{marker} marker found"
                if assignee:
                    summary += f" (assigned to {assignee})"
                if not has_ticket and marker in ("TODO", "FIXME", "BUG"):
                    summary += " - no ticket reference"

                # Build evidence
                evidence = [
                    Evidence(
                        description=f"Marker: {marker}",
                        line_number=line_num,
                        code_snippet=line.strip(),
                        data={
                            "marker": marker,
                            "assignee": assignee,
                            "description": description,
                            "has_ticket": has_ticket,
                        },
                    )
                ]

                # Build remediation hints
                hints = []
                if marker == "TODO":
                    hints.append("Complete the TODO or create a ticket to track it")
                elif marker == "FIXME":
                    hints.append("Fix the issue or create a high-priority ticket")
                elif marker == "HACK":
                    hints.append(
                        "Refactor to remove the hack or document why it's needed"
                    )
                elif marker == "DEPRECATED":
                    hints.append("Update to use the recommended replacement")

                if not has_ticket:
                    hints.append("Consider adding a ticket reference (e.g., ABC-123)")

                findings.append(
                    self._create_finding(
                        summary=summary,
                        file_path=str(context.file_path),
                        line_number=line_num,
                        evidence=evidence,
                        remediation_hints=hints,
                        config=(
                            context.config.get_rule_config(self.rule_id)
                            if context.config
                            else None
                        ),
                    )
                )

                # Override severity for specific markers
                findings[-1].severity = severity

        return findings


class FixmeMarkersRule(BaseRule):
    """Specialized rule for FIXME markers only (higher severity)."""

    FIXME_PATTERN = re.compile(
        r"(?:#|//|/\*|\*)\s*\bFIXME\b(?:\s*\(([^)]+)\))?(?:\s*:\s*(.*))?",
        re.IGNORECASE,
    )

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.FIXME_MARKERS"

    @property
    def name(self) -> str:
        return "FIXME Markers Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def description(self) -> str:
        return (
            "Detects FIXME markers which indicate known bugs or critical "
            "issues that require attention before committing."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for FIXME markers specifically.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for FIXME markers
        """
        findings = []
        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            if not context.is_line_in_diff(line_num):
                continue

            match = self.FIXME_PATTERN.search(line)
            if match:
                match.group(1)
                description = match.group(2) or "No description"

                findings.append(
                    self._create_finding(
                        summary=f"FIXME marker: {description[:50]}...",
                        file_path=str(context.file_path),
                        line_number=line_num,
                        evidence=[
                            Evidence(
                                description="FIXME marker indicates a known issue",
                                line_number=line_num,
                                code_snippet=line.strip(),
                            )
                        ],
                        remediation_hints=[
                            "Fix the issue before committing",
                            "If not fixable now, create a ticket and add reference",
                        ],
                    )
                )

        return findings
