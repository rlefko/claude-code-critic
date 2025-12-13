"""
Commented code detection rule.

Detects blocks of commented-out code that should be removed
rather than left in the codebase.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger
from ..fix import AutoFix

if TYPE_CHECKING:
    from ..base import Finding


class CommentedCodeRule(BaseRule):
    """Detect commented-out code blocks that should be removed."""

    # Default minimum consecutive comment lines to flag
    DEFAULT_MIN_CONSECUTIVE_LINES = 3

    # Patterns that indicate code (not just regular comments)
    # These suggest the comment contains actual code
    CODE_PATTERNS = {
        "python": [
            r"^\s*#\s*(def|class|import|from|if|elif|else|for|while|try|except|finally|with|return|raise|yield|async|await)\b",
            r"^\s*#\s*\w+\s*=\s*",  # variable assignment
            r"^\s*#\s*\w+\.\w+\s*\(",  # method call
            r"^\s*#\s*\w+\s*\(",  # function call
            r"^\s*#\s*@\w+",  # decorator
            r"^\s*#\s*\[",  # list/array start
            r"^\s*#\s*\{",  # dict/object start
        ],
        "javascript": [
            r"^\s*//\s*(function|class|const|let|var|if|else|for|while|try|catch|finally|return|throw|async|await|import|export)\b",
            r"^\s*//\s*\w+\s*=\s*",  # variable assignment
            r"^\s*//\s*\w+\.\w+\s*\(",  # method call
            r"^\s*//\s*\w+\s*\(",  # function call
            r"^\s*//\s*@\w+",  # decorator
            r"^\s*/\*\s*(function|class|const|let|var|if|else|for|while|try|catch|finally|return|throw)\b",
        ],
        "typescript": [
            r"^\s*//\s*(function|class|const|let|var|if|else|for|while|try|catch|finally|return|throw|async|await|import|export|interface|type|enum)\b",
            r"^\s*//\s*\w+\s*:\s*\w+",  # type annotation
            r"^\s*//\s*\w+\s*=\s*",  # variable assignment
            r"^\s*//\s*\w+\.\w+\s*\(",  # method call
            r"^\s*//\s*\w+\s*\(",  # function call
            r"^\s*//\s*@\w+",  # decorator
        ],
    }

    # Comment prefixes by language
    COMMENT_PREFIXES = {
        "python": [r"^\s*#"],
        "javascript": [r"^\s*//", r"^\s*/\*", r"^\s*\*"],
        "typescript": [r"^\s*//", r"^\s*/\*", r"^\s*\*"],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.COMMENTED_CODE"

    @property
    def name(self) -> str:
        return "Commented Code Detection"

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
            "Detects blocks of commented-out code that should be removed. "
            "Commented code clutters the codebase and can be retrieved from "
            "version control if needed."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def can_auto_fix(self) -> bool:
        return True

    def _is_comment_line(self, line: str, language: str) -> bool:
        """Check if a line is a comment."""
        prefixes = self.COMMENT_PREFIXES.get(language, [])
        return any(re.match(prefix, line) for prefix in prefixes)

    def _looks_like_code(self, line: str, language: str) -> bool:
        """Check if a comment line looks like it contains code."""
        patterns = self.CODE_PATTERNS.get(language, [])
        return any(re.search(pattern, line) for pattern in patterns)

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for commented-out code blocks.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected commented code blocks
        """
        findings = []
        language = context.language

        # Get configuration
        min_lines = self.DEFAULT_MIN_CONSECUTIVE_LINES
        if context.config:
            min_lines = context.config.get_rule_parameter(
                self.rule_id,
                "min_consecutive_lines",
                self.DEFAULT_MIN_CONSECUTIVE_LINES,
            )

        # Skip unsupported languages
        if language not in self.CODE_PATTERNS:
            return findings

        lines = context.lines
        i = 0

        while i < len(lines):
            i + 1  # 1-indexed

            # Check if this line is a comment with code
            if self._is_comment_line(lines[i], language) and self._looks_like_code(
                lines[i], language
            ):
                # Found potential start of commented code block
                block_start = i
                block_lines = []
                code_like_count = 0

                # Collect consecutive comment lines
                while i < len(lines) and self._is_comment_line(lines[i], language):
                    block_lines.append(lines[i])
                    if self._looks_like_code(lines[i], language):
                        code_like_count += 1
                    i += 1

                block_end = i  # Exclusive

                # Check if block meets criteria
                block_length = block_end - block_start
                if block_length >= min_lines and code_like_count >= min_lines // 2:
                    # Check if any line in this block is in the diff
                    in_diff = any(
                        context.is_line_in_diff(block_start + j + 1)
                        for j in range(block_length)
                    )

                    if in_diff:
                        # Build code snippet (first few lines)
                        snippet_lines = block_lines[:5]
                        if len(block_lines) > 5:
                            snippet_lines.append("...")
                        snippet = "\n".join(line.strip() for line in snippet_lines)

                        findings.append(
                            self._create_finding(
                                summary=f"Commented code block ({block_length} lines)",
                                file_path=str(context.file_path),
                                line_number=block_start + 1,
                                end_line=block_end,
                                evidence=[
                                    Evidence(
                                        description=f"Found {block_length} consecutive comment lines containing code-like patterns",
                                        line_number=block_start + 1,
                                        code_snippet=snippet,
                                        data={
                                            "block_length": block_length,
                                            "code_like_lines": code_like_count,
                                            "start_line": block_start + 1,
                                            "end_line": block_end,
                                        },
                                    )
                                ],
                                remediation_hints=[
                                    "Remove commented-out code - it can be recovered from version control if needed",
                                    "If the code is intentionally disabled, add a clear explanation comment",
                                    "Consider using feature flags instead of commenting out code",
                                ],
                            )
                        )
            else:
                i += 1

        return findings

    def auto_fix(self, finding: "Finding", context: RuleContext) -> AutoFix | None:
        """Generate auto-fix to remove commented code block.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix to remove the commented code block, or None
        """
        if finding.line_number is None:
            return None

        # Get block boundaries from evidence
        if not finding.evidence or not finding.evidence[0].data:
            return None

        data = finding.evidence[0].data
        start_line = data.get("start_line")
        end_line = data.get("end_line")

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
        comment = "# " if language == "python" else "// "

        # Generate replacement: single comment indicating removal
        indent = len(old_lines[0]) - len(old_lines[0].lstrip())
        indent_str = " " * indent
        new_code = f"{indent_str}{comment}COMMENTED CODE REMOVED ({end_line - start_line + 1} lines)"

        return AutoFix(
            finding=finding,
            old_code=old_code,
            new_code=new_code,
            line_start=start_line,
            line_end=end_line,
            description=f"Removed {end_line - start_line + 1} lines of commented code",
        )
