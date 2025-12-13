"""
Cyclomatic complexity detection rule.

Detects functions with high cyclomatic complexity that should
be refactored into smaller, more manageable functions.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


@dataclass
class FunctionInfo:
    """Information about a detected function."""

    name: str
    start_line: int
    end_line: int
    complexity: int


class ComplexityRule(BaseRule):
    """Detect functions with excessive cyclomatic complexity."""

    # Default maximum complexity threshold
    DEFAULT_MAX_COMPLEXITY = 10

    # Function detection patterns
    FUNCTION_PATTERNS = {
        "python": r"^\s*(?:async\s+)?def\s+(\w+)\s*\(",
        "javascript": r"(?:^|\s)(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)",
        "typescript": r"(?:^|\s)(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*:\s*\w+\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)|(?:public|private|protected)?\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{",
    }

    # Decision point patterns (each adds 1 to complexity)
    DECISION_PATTERNS = {
        "python": [
            (r"\bif\b", "if"),
            (r"\belif\b", "elif"),
            (r"\bfor\b", "for"),
            (r"\bwhile\b", "while"),
            (r"\band\b", "and"),
            (r"\bor\b", "or"),
            (r"\bexcept\b", "except"),
            (r"\bwith\b", "with"),
            (r"\bcase\b", "case"),  # Python 3.10+ match/case
        ],
        "javascript": [
            (r"\bif\b", "if"),
            (r"\belse\s+if\b", "else if"),
            (r"\bfor\b", "for"),
            (r"\bwhile\b", "while"),
            (r"&&", "&&"),
            (r"\|\|", "||"),
            (r"\bcatch\b", "catch"),
            (r"\bcase\b", "case"),
            (r"\?\s*[^:]+\s*:", "ternary"),
        ],
        "typescript": [
            (r"\bif\b", "if"),
            (r"\belse\s+if\b", "else if"),
            (r"\bfor\b", "for"),
            (r"\bwhile\b", "while"),
            (r"&&", "&&"),
            (r"\|\|", "||"),
            (r"\bcatch\b", "catch"),
            (r"\bcase\b", "case"),
            (r"\?\s*[^:]+\s*:", "ternary"),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.COMPLEXITY"

    @property
    def name(self) -> str:
        return "Cyclomatic Complexity Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects functions with high cyclomatic complexity. "
            "Complex functions are harder to understand, test, and maintain. "
            "Consider breaking them down into smaller functions."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _find_python_function_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a Python function based on indentation."""
        if start_line >= len(lines):
            return start_line

        # Get the indentation of the def line
        def_line = lines[start_line]
        base_indent = len(def_line) - len(def_line.lstrip())

        # Look for lines at the same or lower indentation level
        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            current_indent = len(line) - len(line.lstrip())

            # If we find a line at same or lower indentation, function ends before it
            if current_indent <= base_indent:
                return i - 1

        # Function extends to end of file
        return len(lines) - 1

    def _find_js_function_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a JS/TS function by counting braces."""
        brace_count = 0
        found_first_brace = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            # Simple brace counting (doesn't handle strings/comments perfectly)
            for char in line:
                if char == "{":
                    brace_count += 1
                    found_first_brace = True
                elif char == "}":
                    brace_count -= 1

            if found_first_brace and brace_count == 0:
                return i

        return len(lines) - 1

    def _calculate_complexity(
        self, lines: list[str], start_line: int, end_line: int, language: str
    ) -> int:
        """Calculate cyclomatic complexity for a function."""
        # Base complexity is 1
        complexity = 1

        patterns = self.DECISION_PATTERNS.get(language, [])

        for i in range(start_line, min(end_line + 1, len(lines))):
            line = lines[i]
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, _ in patterns:
                matches = re.findall(pattern, line)
                complexity += len(matches)

        return complexity

    def _find_functions(self, context: RuleContext) -> list[FunctionInfo]:
        """Find all functions in the file with their complexity."""
        functions = []
        language = context.language
        lines = context.lines

        pattern = self.FUNCTION_PATTERNS.get(language)
        if not pattern:
            return functions

        for line_num, line in enumerate(lines):
            match = re.search(pattern, line)
            if match:
                # Extract function name from first non-None group
                func_name = None
                for group in match.groups():
                    if group:
                        func_name = group
                        break

                if not func_name:
                    continue

                # Find function end
                if language == "python":
                    end_line = self._find_python_function_end(lines, line_num)
                else:
                    end_line = self._find_js_function_end(lines, line_num)

                # Calculate complexity
                complexity = self._calculate_complexity(
                    lines, line_num, end_line, language
                )

                functions.append(
                    FunctionInfo(
                        name=func_name,
                        start_line=line_num + 1,  # 1-indexed
                        end_line=end_line + 1,  # 1-indexed
                        complexity=complexity,
                    )
                )

        return functions

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for functions with excessive complexity.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for overly complex functions
        """
        findings = []
        language = context.language

        # Skip unsupported languages
        if language not in self.FUNCTION_PATTERNS:
            return findings

        # Get configuration
        max_complexity = self.DEFAULT_MAX_COMPLEXITY
        if context.config:
            max_complexity = context.config.get_rule_parameter(
                self.rule_id, "max_complexity", self.DEFAULT_MAX_COMPLEXITY
            )

        # Find all functions
        functions = self._find_functions(context)

        for func in functions:
            # Skip if function not in diff
            in_diff = any(
                context.is_line_in_diff(line)
                for line in range(func.start_line, func.end_line + 1)
            )
            if not in_diff:
                continue

            if func.complexity > max_complexity:
                # Adjust severity based on how complex
                if (
                    func.complexity > max_complexity * 2
                    or func.complexity > max_complexity * 3
                ):
                    pass

                # Get function snippet (first few lines)
                snippet_lines = context.lines[func.start_line - 1 : func.start_line + 2]
                snippet = "\n".join(line.strip() for line in snippet_lines)
                if len(snippet_lines) < (func.end_line - func.start_line + 1):
                    snippet += "\n..."

                findings.append(
                    self._create_finding(
                        summary=f"Function '{func.name}' has complexity {func.complexity} (max: {max_complexity})",
                        file_path=str(context.file_path),
                        line_number=func.start_line,
                        end_line=func.end_line,
                        evidence=[
                            Evidence(
                                description=f"Function '{func.name}' has cyclomatic complexity of {func.complexity}, exceeding the threshold of {max_complexity}",
                                line_number=func.start_line,
                                code_snippet=snippet,
                                data={
                                    "function_name": func.name,
                                    "complexity": func.complexity,
                                    "max_complexity": max_complexity,
                                    "start_line": func.start_line,
                                    "end_line": func.end_line,
                                },
                            )
                        ],
                        remediation_hints=[
                            f"Refactor '{func.name}' to reduce complexity (currently {func.complexity}, max {max_complexity})",
                            "Extract conditional logic into smaller helper functions",
                            "Consider using early returns to reduce nesting",
                            "Replace complex conditionals with polymorphism or strategy pattern",
                            "Use guard clauses to handle edge cases early",
                        ],
                    )
                )

        return findings
