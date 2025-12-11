"""
Dead code detection rule.

Detects unreachable code that will never execute, such as code
after return, raise, break, or continue statements.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger
from ..fix import AutoFix

if TYPE_CHECKING:
    from ..base import Finding


class DeadCodeRule(BaseRule):
    """Detect dead/unreachable code."""

    # Patterns that terminate execution in their block
    TERMINATING_STATEMENTS = {
        "python": [
            (r"^\s*(return\b)", "return"),
            (r"^\s*(raise\b)", "raise"),
            (r"^\s*(break\b)", "break"),
            (r"^\s*(continue\b)", "continue"),
            (r"^\s*(exit\s*\()", "exit()"),
            (r"^\s*(sys\.exit\s*\()", "sys.exit()"),
            (r"^\s*(os\._exit\s*\()", "os._exit()"),
        ],
        "javascript": [
            (r"^\s*(return\b)", "return"),
            (r"^\s*(throw\b)", "throw"),
            (r"^\s*(break\b)", "break"),
            (r"^\s*(continue\b)", "continue"),
            (r"^\s*(process\.exit\s*\()", "process.exit()"),
        ],
        "typescript": [
            (r"^\s*(return\b)", "return"),
            (r"^\s*(throw\b)", "throw"),
            (r"^\s*(break\b)", "break"),
            (r"^\s*(continue\b)", "continue"),
            (r"^\s*(process\.exit\s*\()", "process.exit()"),
        ],
    }

    # Patterns that always evaluate to True
    ALWAYS_TRUE_PATTERNS = {
        "python": [
            r"\bif\s+True\s*:",
            r"\bwhile\s+True\s*:",
            r'\bif\s+["\'][^"\']+["\']\s*:',  # if "string":
            r"\bif\s+\d+\s*:",  # if 1:
        ],
        "javascript": [
            r"\bif\s*\(\s*true\s*\)",
            r"\bwhile\s*\(\s*true\s*\)",
            r'\bif\s*\(\s*["\'][^"\']+["\']\s*\)',
            r"\bif\s*\(\s*\d+\s*\)",
        ],
        "typescript": [
            r"\bif\s*\(\s*true\s*\)",
            r"\bwhile\s*\(\s*true\s*\)",
            r'\bif\s*\(\s*["\'][^"\']+["\']\s*\)',
            r"\bif\s*\(\s*\d+\s*\)",
        ],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.DEAD_CODE"

    @property
    def name(self) -> str:
        return "Dead Code Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects unreachable code that will never execute. "
            "Dead code clutters the codebase and should be removed."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def can_auto_fix(self) -> bool:
        return True

    def _get_indentation(self, line: str) -> int:
        """Get the indentation level of a line."""
        return len(line) - len(line.lstrip())

    def _is_empty_or_comment(self, line: str, language: str) -> bool:
        """Check if line is empty or a comment."""
        stripped = line.strip()
        if not stripped:
            return True
        if language == "python" and stripped.startswith("#"):
            return True
        if language in ("javascript", "typescript") and stripped.startswith("//"):
            return True
        return False

    def _is_block_end(self, line: str, language: str) -> bool:
        """Check if line ends a block."""
        stripped = line.strip()
        if language == "python":
            # Check for dedent (handled by indentation comparison)
            return False
        else:
            return stripped == "}" or stripped.startswith("}")

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for dead/unreachable code.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for dead code
        """
        findings = []
        language = context.language

        # Get terminating patterns for this language
        terminating_patterns = self.TERMINATING_STATEMENTS.get(language, [])
        if not terminating_patterns:
            return findings

        lines = context.lines
        i = 0

        while i < len(lines):
            line = lines[i]
            line_num = i + 1  # 1-indexed

            # Check if this line contains a terminating statement
            terminating_match = None
            for pattern, statement_type in terminating_patterns:
                if re.search(pattern, line):
                    terminating_match = statement_type
                    break

            if terminating_match:
                # Found a terminating statement
                # Check if there's code after it at the same or deeper indentation
                current_indent = self._get_indentation(line)
                dead_code_start = None
                dead_code_lines = []

                j = i + 1
                while j < len(lines):
                    next_line = lines[j]

                    # Skip empty lines and comments
                    if self._is_empty_or_comment(next_line, language):
                        j += 1
                        continue

                    next_indent = self._get_indentation(next_line)

                    # In Python, code at lower indentation is a new scope
                    # Code at same or deeper indentation after terminating statement is dead
                    if language == "python":
                        if next_indent < current_indent:
                            # Different scope (dedent), stop checking
                            break
                        # Code at same or deeper indentation = dead code
                        if dead_code_start is None:
                            dead_code_start = j + 1  # 1-indexed
                        dead_code_lines.append(next_line)
                        j += 1
                    else:
                        # For JS/TS, check for closing brace
                        if self._is_block_end(next_line, language):
                            break
                        # Same indentation in same block = dead code
                        if next_indent >= current_indent:
                            if dead_code_start is None:
                                dead_code_start = j + 1
                            dead_code_lines.append(next_line)
                        j += 1

                # Report dead code if found
                if dead_code_start and dead_code_lines:
                    # Check if any dead code line is in diff
                    dead_code_end = dead_code_start + len(dead_code_lines) - 1
                    in_diff = any(
                        context.is_line_in_diff(line_no)
                        for line_no in range(dead_code_start, dead_code_end + 1)
                    )

                    if in_diff:
                        snippet_lines = dead_code_lines[:3]
                        if len(dead_code_lines) > 3:
                            snippet_lines.append("...")
                        snippet = "\n".join(ln.strip() for ln in snippet_lines)

                        findings.append(
                            self._create_finding(
                                summary=f"Unreachable code after '{terminating_match}' ({len(dead_code_lines)} lines)",
                                file_path=str(context.file_path),
                                line_number=dead_code_start,
                                end_line=dead_code_end,
                                evidence=[
                                    Evidence(
                                        description=f"Code after '{terminating_match}' statement on line {line_num} will never execute",
                                        line_number=dead_code_start,
                                        code_snippet=snippet,
                                        data={
                                            "terminating_statement": terminating_match,
                                            "terminating_line": line_num,
                                            "dead_code_start": dead_code_start,
                                            "dead_code_end": dead_code_end,
                                            "dead_code_count": len(dead_code_lines),
                                        },
                                    )
                                ],
                                remediation_hints=[
                                    f"Remove unreachable code after the '{terminating_match}' statement",
                                    "If this code is needed, move it before the terminating statement",
                                    "Consider if the terminating statement is in the correct location",
                                ],
                            )
                        )

                    # Skip past the dead code
                    i = j
                    continue

            i += 1

        # Also check for else after if True:
        findings.extend(self._check_unreachable_else(context))

        return findings

    def _check_unreachable_else(self, context: RuleContext) -> list["Finding"]:
        """Check for else blocks that can never execute."""
        findings = []
        language = context.language

        always_true_patterns = self.ALWAYS_TRUE_PATTERNS.get(language, [])
        if not always_true_patterns:
            return findings

        lines = context.lines

        for i, line in enumerate(lines):
            line_num = i + 1

            # Check if line is always-true condition
            for pattern in always_true_patterns:
                if re.search(pattern, line):
                    # Look for corresponding else
                    current_indent = self._get_indentation(line)

                    for j in range(i + 1, len(lines)):
                        check_line = lines[j]
                        if self._is_empty_or_comment(check_line, language):
                            continue

                        check_indent = self._get_indentation(check_line)

                        # If we're at a lower or same indentation with 'else'
                        if check_indent == current_indent:
                            if re.search(r"^\s*else\s*:", check_line) or re.search(
                                r"^\s*else\s*\{", check_line
                            ):
                                if context.is_line_in_diff(j + 1):
                                    findings.append(
                                        self._create_finding(
                                            summary="Unreachable 'else' block (condition always True)",
                                            file_path=str(context.file_path),
                                            line_number=j + 1,
                                            evidence=[
                                                Evidence(
                                                    description=f"This 'else' block is unreachable because the condition on line {line_num} is always True",
                                                    line_number=j + 1,
                                                    code_snippet=check_line.strip(),
                                                    data={
                                                        "condition_line": line_num,
                                                        "else_line": j + 1,
                                                    },
                                                )
                                            ],
                                            remediation_hints=[
                                                "Remove the unreachable else block",
                                                "Fix the condition if the else block should be reachable",
                                            ],
                                        )
                                    )
                            break
                        elif check_indent < current_indent:
                            break
                    break

        return findings

    def auto_fix(
        self, finding: "Finding", context: RuleContext
    ) -> AutoFix | None:
        """Generate auto-fix to remove dead code.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix to comment out dead code, or None
        """
        if finding.line_number is None:
            return None

        if not finding.evidence or not finding.evidence[0].data:
            return None

        data = finding.evidence[0].data
        start_line = data.get("dead_code_start")
        end_line = data.get("dead_code_end")

        if start_line is None or end_line is None:
            return None

        # Collect the lines to remove
        old_lines = []
        for i in range(start_line, end_line + 1):
            line = context.get_line_content(i)
            if line is not None:
                old_lines.append(line)

        if not old_lines:
            return None

        old_code = "\n".join(old_lines)

        # Get the comment prefix for this language
        language = context.language
        if language == "python":
            comment = "# "
        else:
            comment = "// "

        # Generate replacement: single comment indicating removal
        indent = len(old_lines[0]) - len(old_lines[0].lstrip())
        indent_str = " " * indent
        new_code = f"{indent_str}{comment}DEAD CODE REMOVED ({end_line - start_line + 1} lines)"

        return AutoFix(
            finding=finding,
            old_code=old_code,
            new_code=new_code,
            line_start=start_line,
            line_end=end_line,
            description=f"Removed {end_line - start_line + 1} lines of unreachable code",
        )
