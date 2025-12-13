"""
Debug statements detection rule.

Detects debug statements like print(), console.log(), debugger,
and other debugging code that should not be committed to production.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger
from ..fix import AutoFix

if TYPE_CHECKING:
    pass


class DebugStatementsRule(BaseRule):
    """Detect debug statements that should not be in production code."""

    # Language-specific debug patterns
    PATTERNS = {
        "python": [
            (r"^\s*print\s*\(", "print() statement"),
            (r"^\s*pprint\s*\(", "pprint() statement"),
            (r"\bbreakpoint\s*\(\)", "breakpoint() call"),
            (r"\bpdb\.set_trace\s*\(\)", "pdb.set_trace() call"),
            (r"\bipdb\.set_trace\s*\(\)", "ipdb.set_trace() call"),
            (r"^\s*import\s+pdb\s*$", "pdb import"),
            (r"^\s*import\s+ipdb\s*$", "ipdb import"),
            (r"^\s*from\s+pdb\s+import", "pdb import"),
        ],
        "javascript": [
            (r"\bconsole\.(log|debug|info|warn|error)\s*\(", "console statement"),
            (r"\bdebugger\s*;?", "debugger statement"),
            (r"\balert\s*\(", "alert() call"),
        ],
        "typescript": [
            (r"\bconsole\.(log|debug|info|warn|error)\s*\(", "console statement"),
            (r"\bdebugger\s*;?", "debugger statement"),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.DEBUG_STATEMENTS"

    @property
    def name(self) -> str:
        return "Debug Statements Detection"

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
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects debug statements like print(), console.log(), debugger, "
            "and other debugging code that should be removed before committing."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def can_auto_fix(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for debug statements in the file.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected debug statements
        """
        findings = []
        language = context.language

        # Get patterns for this language
        patterns = self.PATTERNS.get(language, [])
        if not patterns:
            return findings

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, description in patterns:
                if re.search(pattern, line):
                    # Check if it looks like it's in a test file
                    file_path_str = str(context.file_path)
                    is_test_file = any(
                        marker in file_path_str.lower()
                        for marker in ["test_", "_test", "tests/", "spec/"]
                    )

                    # Lower severity for test files
                    severity = Severity.LOW if is_test_file else self.default_severity

                    findings.append(
                        Finding(
                            rule_id=self.rule_id,
                            severity=severity,
                            summary=f"Debug statement: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={"pattern": pattern, "language": language},
                                )
                            ],
                            remediation_hints=[
                                "Remove debug statement before committing",
                                "Use logging framework instead for production code",
                            ],
                            can_auto_fix=True,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def auto_fix(self, finding: Finding, context: RuleContext) -> AutoFix | None:
        """Generate auto-fix to remove debug statement.

        For simple cases, we can remove or comment out the line.
        For complex cases (multi-line), we return None.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix to remove the debug statement, or None
        """
        if finding.line_number is None:
            return None

        line = context.get_line_content(finding.line_number)
        if line is None:
            return None

        # Simple fix: comment out the line
        # More sophisticated fix would remove it entirely
        indent = len(line) - len(line.lstrip())
        indent_str = line[:indent]

        language = context.language
        if language == "python":
            new_line = f"{indent_str}# DEBUG REMOVED: {line.strip()}"
        else:
            new_line = f"{indent_str}// DEBUG REMOVED: {line.strip()}"

        return AutoFix(
            finding=finding,
            old_code=line,
            new_code=new_line,
            line_start=finding.line_number,
            line_end=finding.line_number,
            description=f"Commented out debug statement",
        )


class BreakpointRule(BaseRule):
    """Specialized rule for breakpoint() calls (higher severity)."""

    BREAKPOINT_PATTERNS = [
        (r"\bbreakpoint\s*\(\)", "breakpoint()"),
        (r"\bpdb\.set_trace\s*\(\)", "pdb.set_trace()"),
        (r"\bipdb\.set_trace\s*\(\)", "ipdb.set_trace()"),
        (r"\bdebugger\s*;?", "debugger"),
    ]

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.BREAKPOINTS"

    @property
    def name(self) -> str:
        return "Breakpoint Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def description(self) -> str:
        return (
            "Detects breakpoint() and debugger statements that will halt "
            "execution in production. These must be removed before committing."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for breakpoint statements.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for breakpoint statements
        """
        findings = []
        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, description in self.BREAKPOINT_PATTERNS:
                if re.search(pattern, line):
                    findings.append(
                        self._create_finding(
                            summary=f"Breakpoint found: {description}",
                            file_path=str(context.file_path),
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=f"{description} will halt execution",
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                )
                            ],
                            remediation_hints=[
                                "Remove breakpoint before committing",
                                "This will cause production code to halt",
                            ],
                        )
                    )
                    break

        return findings
