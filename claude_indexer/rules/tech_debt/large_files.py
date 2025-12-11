"""
Large files detection rule.

Detects files that exceed a configurable line count threshold,
which may indicate the need for refactoring or splitting.
"""

from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class LargeFilesRule(BaseRule):
    """Detect files that are too large and may need splitting."""

    # Default threshold for maximum lines
    DEFAULT_MAX_LINES = 500

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.LARGE_FILES"

    @property
    def name(self) -> str:
        return "Large File Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        # All languages
        return None

    @property
    def description(self) -> str:
        return (
            "Detects files that exceed a configurable line count threshold. "
            "Large files are harder to maintain and may indicate the need for "
            "refactoring or splitting into smaller modules."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check if file exceeds maximum line threshold.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings if file is too large
        """
        findings = []

        # Get configuration
        max_lines = self.DEFAULT_MAX_LINES
        if context.config:
            max_lines = context.config.get_rule_parameter(
                self.rule_id, "max_lines", self.DEFAULT_MAX_LINES
            )

        line_count = len(context.lines)

        if line_count > max_lines:
            # Calculate how much over the limit
            excess = line_count - max_lines
            percentage_over = (excess / max_lines) * 100

            # Adjust severity based on how much over
            severity = self.default_severity
            if percentage_over > 100:  # More than 2x the limit
                severity = Severity.MEDIUM
            elif percentage_over > 200:  # More than 3x the limit
                severity = Severity.HIGH

            findings.append(
                self._create_finding(
                    summary=f"File has {line_count} lines (exceeds {max_lines} limit)",
                    file_path=str(context.file_path),
                    line_number=1,
                    evidence=[
                        Evidence(
                            description=f"File contains {line_count} lines, {excess} over the {max_lines} line limit",
                            line_number=1,
                            code_snippet=None,
                            data={
                                "line_count": line_count,
                                "max_lines": max_lines,
                                "excess": excess,
                                "percentage_over": round(percentage_over, 1),
                            },
                        )
                    ],
                    remediation_hints=[
                        f"Consider splitting this file into smaller modules (currently {line_count} lines)",
                        "Extract related functions/classes into separate files",
                        "Look for logical groupings that could become separate modules",
                        "Consider using a package structure with __init__.py",
                    ],
                    config=context.config.get_rule_config(self.rule_id)
                    if context.config
                    else None,
                )
            )

        return findings
