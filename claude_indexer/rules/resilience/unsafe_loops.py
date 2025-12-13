"""
Unsafe loop detection rule.

Detects loops that may lack clear termination conditions,
risking infinite execution.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class UnsafeLoopRule(BaseRule):
    """Detect potentially infinite loops.

    Identifies loops that may lack proper termination conditions,
    such as `while True` without break/return, or for loops without
    clear iteration bounds.
    """

    # Infinite loop patterns by language
    LOOP_PATTERNS = {
        "python": [
            (r"^\s*while\s+True\s*:", "while True", 0.70),
            (r"^\s*while\s+1\s*:", "while 1", 0.75),
            (
                r'^\s*while\s+["\'][^"\']+["\']\s*:',
                "while with constant truthy string",
                0.85,
            ),
        ],
        "javascript": [
            (r"\bwhile\s*\(\s*true\s*\)", "while(true)", 0.70),
            (r"\bwhile\s*\(\s*1\s*\)", "while(1)", 0.75),
            (r"\bfor\s*\(\s*;\s*;\s*\)", "for(;;)", 0.75),
        ],
        "typescript": [
            (r"\bwhile\s*\(\s*true\s*\)", "while(true)", 0.70),
            (r"\bwhile\s*\(\s*1\s*\)", "while(1)", 0.75),
            (r"\bfor\s*\(\s*;\s*;\s*\)", "for(;;)", 0.75),
        ],
    }

    # Patterns indicating loop termination
    TERMINATION_PATTERNS = {
        "python": [
            r"\breturn\b",
            r"\bbreak\b",
            r"\braise\b",
            r"\bsys\.exit\b",
            r"\bexit\s*\(",
            r"\bquit\s*\(",
        ],
        "javascript": [
            r"\breturn\b",
            r"\bbreak\b",
            r"\bthrow\b",
            r"\bprocess\.exit\b",
        ],
        "typescript": [
            r"\breturn\b",
            r"\bbreak\b",
            r"\bthrow\b",
            r"\bprocess\.exit\b",
        ],
    }

    @property
    def rule_id(self) -> str:
        return "RESILIENCE.UNSAFE_LOOP"

    @property
    def name(self) -> str:
        return "Infinite Loop Risk Detection"

    @property
    def category(self) -> str:
        return "resilience"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects loops that may lack clear termination conditions, "
            "risking infinite execution. Checks for while True, for(;;), "
            "and other potentially unbounded loops."
        )

    @property
    def is_fast(self) -> bool:
        return True  # Pattern matching with simple scope analysis

    def _find_python_loop_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a Python loop based on indentation."""
        if start_line >= len(lines):
            return start_line

        loop_line = lines[start_line]
        base_indent = len(loop_line) - len(loop_line.lstrip())

        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            current_indent = len(line) - len(line.lstrip())

            if current_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _find_js_loop_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a JS/TS loop by counting braces."""
        brace_count = 0
        found_first_brace = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    found_first_brace = True
                elif char == "}":
                    brace_count -= 1

            if found_first_brace and brace_count == 0:
                return i

        return len(lines) - 1

    def _has_termination(
        self, lines: list[str], start: int, end: int, language: str
    ) -> bool:
        """Check if loop body contains termination mechanisms."""
        patterns = self.TERMINATION_PATTERNS.get(language, [])

        for i in range(start, min(end + 1, len(lines))):
            line = lines[i]
            for pattern in patterns:
                if re.search(pattern, line):
                    return True

        return False

    def _is_conditional_termination(
        self, lines: list[str], start: int, end: int, language: str
    ) -> bool:
        """Check if termination is conditional (only under if)."""
        patterns = self.TERMINATION_PATTERNS.get(language, [])

        # Find all termination statements
        for i in range(start, min(end + 1, len(lines))):
            line = lines[i]
            for pattern in patterns:
                if re.search(pattern, line):
                    # Check if it's inside an if block (indented more)
                    if language == "python":
                        base_indent = len(lines[start]) - len(lines[start].lstrip())
                        term_indent = len(line) - len(line.lstrip())
                        if term_indent > base_indent + 4:
                            continue  # Inside nested block, still conditional
                    return True

        return False

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for potentially infinite loops.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for unsafe loops
        """
        findings = []
        language = context.language
        lines = context.lines

        patterns = self.LOOP_PATTERNS.get(language, [])
        if not patterns:
            return findings

        for line_num, line in enumerate(lines):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num + 1):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, loop_type, base_confidence in patterns:
                match = re.search(pattern, line)
                if match:
                    # Find loop body bounds
                    if language == "python":
                        end_line = self._find_python_loop_end(lines, line_num)
                    else:
                        end_line = self._find_js_loop_end(lines, line_num)

                    # Check for termination
                    has_termination = self._has_termination(
                        lines, line_num, end_line, language
                    )

                    if has_termination:
                        # Has termination - check if it's always reachable
                        if self._is_conditional_termination(
                            lines, line_num, end_line, language
                        ):
                            continue  # Termination is unconditional, skip
                        continue  # Has unconditional termination

                    # Get loop snippet
                    loop_lines = lines[line_num : min(end_line + 1, line_num + 5)]
                    snippet = "\n".join(line.strip() for line in loop_lines)
                    if end_line - line_num > 4:
                        snippet += "\n..."

                    findings.append(
                        self._create_finding(
                            summary=f"{loop_type} loop without visible break/return",
                            file_path=str(context.file_path),
                            line_number=line_num + 1,
                            end_line=end_line + 1,
                            evidence=[
                                Evidence(
                                    description=f"Loop at line {line_num + 1} appears to lack termination",
                                    line_number=line_num + 1,
                                    code_snippet=snippet,
                                    data={
                                        "loop_type": loop_type,
                                        "start_line": line_num + 1,
                                        "end_line": end_line + 1,
                                    },
                                )
                            ],
                            remediation_hints=[
                                f"Add explicit break condition inside {loop_type} loop",
                                "Ensure there's a reachable return, break, or raise statement",
                                "Consider adding a maximum iteration counter as safeguard",
                            ],
                            confidence=base_confidence,
                        )
                    )

        return findings
