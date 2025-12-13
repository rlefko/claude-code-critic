"""
Repair check result for Claude self-repair loop.

This module provides the RepairCheckResult class which extends StopCheckResult
with repair context information including session tracking, fix suggestions,
and escalation state.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from .fix_generator import FixSuggestion
from .repair_session import RepairSession
from .stop_check import StopCheckResult


@dataclass
class RepairCheckResult:
    """Stop check result with repair loop context.

    Extends the base StopCheckResult with repair-specific information
    including session tracking, fix suggestions, and escalation state.

    Attributes:
        base_result: The underlying StopCheckResult
        session: RepairSession tracking retry attempts
        fix_suggestions: List of fix suggestions for findings
        is_same_issue: True if findings match previous check
    """

    base_result: StopCheckResult
    session: RepairSession
    fix_suggestions: list[FixSuggestion] = field(default_factory=list)
    is_same_issue: bool = False

    @property
    def should_escalate(self) -> bool:
        """Check if should escalate to user due to max retries."""
        return self.session.should_escalate and self.is_same_issue

    @property
    def remaining_attempts(self) -> int:
        """Get number of remaining retry attempts."""
        return self.session.remaining_attempts

    @property
    def attempt_number(self) -> int:
        """Get current attempt number (1-indexed)."""
        return self.session.attempt_count

    @property
    def should_block(self) -> bool:
        """Check if should block Claude."""
        return self.base_result.should_block

    @property
    def findings(self):
        """Get findings from base result."""
        return self.base_result.findings

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Start with base result
        result = self.base_result.to_dict()

        # Determine status
        if self.should_escalate:
            result["status"] = "escalated"
        elif self.should_block:
            result["status"] = "blocked"

        # Add repair context
        result["repair_context"] = {
            "session_id": self.session.session_id,
            "attempt_number": self.attempt_number,
            "max_attempts": self.session.max_attempts,
            "remaining_attempts": self.remaining_attempts,
            "is_same_issue": self.is_same_issue,
            "should_escalate": self.should_escalate,
        }

        # Add fix suggestions
        result["fix_suggestions"] = [s.to_dict() for s in self.fix_suggestions]

        # Add escalation info if needed
        if self.should_escalate:
            result["escalation"] = {
                "reason": "max_retries_exceeded",
                "attempts_made": self.attempt_number,
                "message_for_user": self._get_escalation_message_for_user(),
                "message_for_claude": self._get_escalation_message_for_claude(),
            }
        else:
            result["escalation"] = None

        # Add instructions based on state
        result["instructions"] = self._get_instructions()

        return result

    def to_json(self, indent: int | None = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def _get_instructions(self) -> str:
        """Get instructions based on current state."""
        if not self.should_block:
            return "No blocking issues found."

        if self.should_escalate:
            return (
                "Maximum repair attempts reached. "
                "These issues require manual intervention."
            )

        remaining = self.remaining_attempts
        if remaining == 1:
            return (
                "Fix the issues above. This is your LAST attempt before "
                "escalation to the user."
            )

        return f"Fix the issues above. {remaining} attempts remaining."

    def _get_escalation_message_for_user(self) -> str:
        """Get message for user when escalating."""
        finding_count = len(self.findings)

        lines = [
            f"Claude attempted to fix {finding_count} issue(s) "
            f"{self.attempt_number} times but was unsuccessful.",
            "",
            "The following issues require manual attention:",
            "",
        ]

        # Add findings summary
        for finding in self.findings:
            severity = finding.severity.name.upper()
            location = f"{finding.file_path}:{finding.line_number or '?'}"
            lines.append(f"  [{severity}] {finding.rule_id}")
            lines.append(f"    Location: {location}")
            lines.append(f"    Issue: {finding.summary}")
            if finding.remediation_hints:
                lines.append(f"    Fix: {finding.remediation_hints[0]}")
            lines.append("")

        lines.append(
            "Please review and fix these issues manually, "
            "then continue with your task."
        )

        return "\n".join(lines)

    def _get_escalation_message_for_claude(self) -> str:
        """Get message for Claude when escalating."""
        return (
            "I was unable to fix these issues after multiple attempts. "
            "I'm presenting them to the user for manual review. "
            "Please wait for the user to address these before continuing."
        )

    def format_for_claude(self) -> str:
        """Format structured message for Claude consumption.

        Returns a formatted string suitable for Claude to parse
        and understand what fixes are needed.
        """
        lines = []

        if self.should_escalate:
            lines.append("=== REPAIR ESCALATED TO USER ===")
            lines.append("")
            lines.append(self._get_escalation_message_for_claude())
            lines.append("")
            return "\n".join(lines)

        lines.append("=== QUALITY CHECK BLOCKED ===")
        lines.append("")

        # Add repair context
        lines.append(
            f"Repair attempt {self.attempt_number} of {self.session.max_attempts}"
        )
        lines.append(f"Remaining attempts: {self.remaining_attempts}")
        lines.append("")

        # Add findings with fix suggestions
        for finding in self.findings:
            severity = finding.severity.name.upper()
            location = f"{finding.file_path}:{finding.line_number or '?'}"
            lines.append(f"{severity}: {finding.rule_id} - {location}")
            lines.append(f"Description: {finding.summary}")

            # Add fix suggestion if available
            suggestion = self._get_suggestion_for_finding(finding)
            if suggestion and suggestion.action == "auto_available":
                lines.append(f"Fix available (confidence: {suggestion.confidence:.0%})")
                lines.append(f"Suggested fix: {suggestion.description}")
                if suggestion.code_preview:
                    lines.append("Preview:")
                    for preview_line in suggestion.code_preview.split("\n")[:10]:
                        lines.append(f"  {preview_line}")
            elif finding.remediation_hints:
                lines.append(f"Suggestion: {finding.remediation_hints[0]}")
            else:
                lines.append("Suggestion: Review and fix the issue")

            lines.append("---")

        # Summary
        lines.append("")
        lines.append(
            f"Found {len(self.findings)} blocking issue(s): "
            f"{self.base_result.critical_count} critical, "
            f"{self.base_result.high_count} high"
        )
        lines.append(
            f"Checked {self.base_result.files_checked} files "
            f"in {self.base_result.execution_time_ms:.0f}ms"
        )
        lines.append("")
        lines.append(self._get_instructions())
        lines.append("")

        return "\n".join(lines)

    def format_escalation_message(self) -> str:
        """Format escalation message for user presentation."""
        return self._get_escalation_message_for_user()

    def _get_suggestion_for_finding(self, finding) -> FixSuggestion | None:
        """Get fix suggestion for a finding."""
        for suggestion in self.fix_suggestions:
            if (
                suggestion.finding.rule_id == finding.rule_id
                and suggestion.finding.file_path == finding.file_path
                and suggestion.finding.line_number == finding.line_number
            ):
                return suggestion
        return None
