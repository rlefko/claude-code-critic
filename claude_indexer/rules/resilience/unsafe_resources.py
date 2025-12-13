"""
Unsafe resource handling detection rule.

Detects resources that are opened but may not be properly closed,
risking memory leaks or resource exhaustion.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class UnsafeResourceRule(BaseRule):
    """Detect potential resource leaks.

    Identifies resources that are opened but may not be properly closed,
    such as files without context managers, database connections without
    cleanup, or event listeners without removal.
    """

    # Resource acquisition patterns by language
    RESOURCE_PATTERNS = {
        "python": [
            # File operations without context manager
            (
                r"^\s*\w+\s*=\s*open\s*\(",
                "File opened without context manager (use 'with')",
                0.85,
            ),
            # Database connections
            (
                r"^\s*\w+\s*=\s*\w+\.connect\s*\(",
                "Database connection without context manager",
                0.75,
            ),
            (
                r"cursor\s*=\s*\w+\.cursor\s*\(",
                "Cursor opened without context manager",
                0.70,
            ),
            # Network resources
            (
                r"^\s*\w+\s*=\s*socket\.socket\s*\(",
                "Socket created without close/context manager",
                0.80,
            ),
            (
                r"^\s*\w+\s*=\s*urllib\.request\.urlopen\s*\(",
                "URL opened without context manager",
                0.75,
            ),
            # Subprocess
            (
                r"^\s*\w+\s*=\s*subprocess\.Popen\s*\(",
                "Subprocess opened - ensure proper cleanup",
                0.70,
            ),
        ],
        "javascript": [
            # File handles (Node.js)
            (
                r"fs\.open\s*\([^)]+,\s*[^)]+,\s*function",
                "fs.open callback - ensure close on error",
                0.70,
            ),
            (
                r"fs\.createReadStream\s*\(",
                "Stream created - ensure close/destroy on error",
                0.65,
            ),
            (
                r"fs\.createWriteStream\s*\(",
                "Write stream - ensure close on completion",
                0.65,
            ),
            # Database
            (
                r"\.connect\s*\(\s*\)",
                "Database connection opened - ensure close",
                0.70,
            ),
            (
                r"new\s+Pool\s*\(",
                "Connection pool - ensure pool.end() on shutdown",
                0.60,
            ),
            # Event listeners (memory leak pattern)
            (
                r"addEventListener\s*\([^)]+\)",
                "Event listener added - ensure removeEventListener",
                0.50,
            ),
            (
                r"\.on\s*\(\s*['\"]",
                "Event handler attached - consider cleanup",
                0.45,
            ),
            # Timers
            (
                r"setInterval\s*\(",
                "setInterval - ensure clearInterval cleanup",
                0.60,
            ),
        ],
        "typescript": [
            # Same as JavaScript plus subscription patterns
            (
                r"\.subscribe\s*\(",
                "Observable subscription - ensure unsubscribe",
                0.65,
            ),
            (
                r"addEventListener\s*\([^)]+\)",
                "Event listener - ensure cleanup in ngOnDestroy/useEffect",
                0.60,
            ),
            (
                r"setInterval\s*\(",
                "setInterval - ensure clearInterval cleanup",
                0.60,
            ),
            (
                r"fs\.createReadStream\s*\(",
                "Stream created - ensure close/destroy on error",
                0.65,
            ),
        ],
    }

    # Cleanup patterns that indicate proper resource handling
    CLEANUP_PATTERNS = {
        "python": [
            r"\bwith\s+",  # Context manager
            r"\.close\s*\(",
            r"\.release\s*\(",
            r"\.shutdown\s*\(",
            r"\bfinally\s*:",
        ],
        "javascript": [
            r"\.close\s*\(",
            r"\.destroy\s*\(",
            r"\.end\s*\(",
            r"\bclearInterval\b",
            r"\bclearTimeout\b",
            r"\bremoveEventListener\b",
            r"\.off\s*\(",
            r"\.finally\s*\(",
        ],
        "typescript": [
            r"\.unsubscribe\s*\(",
            r"\.close\s*\(",
            r"\.destroy\s*\(",
            r"\bclearInterval\b",
            r"\bremoveEventListener\b",
            r"\bngOnDestroy\b",
            r"useEffect.*return",
        ],
    }

    @property
    def rule_id(self) -> str:
        return "RESILIENCE.UNSAFE_RESOURCE"

    @property
    def name(self) -> str:
        return "Resource Leak Detection"

    @property
    def category(self) -> str:
        return "resilience"

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
            "Detects resources that are opened but may not be properly closed, "
            "risking memory leaks or resource exhaustion. Checks for files, "
            "database connections, event listeners, and subscriptions."
        )

    @property
    def is_fast(self) -> bool:
        return True  # Pattern matching with simple scope analysis

    def _is_in_context_manager(
        self, lines: list[str], line_num: int, language: str
    ) -> bool:
        """Check if the resource is managed by a context manager."""
        if language == "python":
            # Look for 'with' statement above at same or lower indentation
            current_indent = len(lines[line_num]) - len(lines[line_num].lstrip())
            for i in range(max(0, line_num - 5), line_num):
                line = lines[i]
                if re.search(r"^\s*with\s+", line):
                    with_indent = len(line) - len(line.lstrip())
                    if with_indent <= current_indent:
                        return True
        return False

    def _extract_variable_name(self, line: str) -> str | None:
        """Extract the variable name from an assignment."""
        match = re.match(r"^\s*(\w+)\s*=", line)
        if match:
            return match.group(1)
        return None

    def _find_function_end(self, lines: list[str], start: int, language: str) -> int:
        """Find the end of the current function scope."""
        if language == "python":
            # Find the function definition above
            base_indent = None
            for i in range(start, -1, -1):
                if re.search(r"^\s*(?:async\s+)?def\s+", lines[i]):
                    base_indent = len(lines[i]) - len(lines[i].lstrip())
                    break

            if base_indent is None:
                return len(lines) - 1

            # Find end of function
            for i in range(start + 1, len(lines)):
                stripped = lines[i].strip()
                if not stripped or stripped.startswith("#"):
                    continue
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if current_indent <= base_indent:
                    return i - 1

        else:  # JavaScript/TypeScript
            # Count braces to find function end
            brace_count = 0
            for i in range(start, len(lines)):
                for char in lines[i]:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            return i

        return len(lines) - 1

    def _has_cleanup_in_scope(
        self, lines: list[str], var_name: str, start: int, end: int, language: str
    ) -> bool:
        """Check if the variable is properly cleaned up in scope."""
        patterns = self.CLEANUP_PATTERNS.get(language, [])

        for i in range(start, min(end + 1, len(lines))):
            line = lines[i]

            # Check for cleanup with variable name
            for pattern in patterns:
                if re.search(pattern, line):
                    # If variable is mentioned on cleanup line, or generic cleanup
                    if var_name and var_name in line:
                        return True
                    # Generic cleanup patterns
                    if pattern in (r"\bfinally\s*:", r"\.finally\s*\("):
                        return True

        return False

    def _has_try_finally(
        self, lines: list[str], start: int, end: int, language: str
    ) -> bool:
        """Check if the resource is in a try/finally block."""
        if language == "python":
            for i in range(max(0, start - 10), start):
                if re.search(r"^\s*try\s*:", lines[i]):
                    # Look for matching finally
                    for j in range(start, min(end + 5, len(lines))):
                        if re.search(r"^\s*finally\s*:", lines[j]):
                            return True
        else:
            for i in range(max(0, start - 10), start):
                if re.search(r"\btry\s*\{", lines[i]):
                    # Look for matching finally
                    for j in range(start, min(end + 5, len(lines))):
                        if re.search(r"\bfinally\s*\{", lines[j]):
                            return True

        return False

    def _get_remediation_hint(self, language: str, pattern_desc: str) -> list[str]:
        """Get language-specific remediation hints."""
        if language == "python":
            if "open" in pattern_desc.lower():
                return [
                    "Use a context manager: `with open(...) as f:` for automatic cleanup",
                    "Or manually call `.close()` in a `finally` block",
                ]
            else:
                return [
                    "Use a context manager (`with` statement) for automatic cleanup",
                    "Or ensure `.close()` is called in a `finally` block",
                ]
        elif language in ("javascript", "typescript"):
            if "listener" in pattern_desc.lower():
                return [
                    "Store the listener reference and call removeEventListener on cleanup",
                    "In React, use useEffect cleanup function",
                    "In Angular, use ngOnDestroy lifecycle hook",
                ]
            elif "interval" in pattern_desc.lower():
                return [
                    "Store interval ID and call clearInterval on cleanup",
                    "In React, clear in useEffect cleanup function",
                ]
            elif "subscribe" in pattern_desc.lower():
                return [
                    "Store subscription and call .unsubscribe() on component destroy",
                    "Use takeUntil pattern with a destroy subject",
                ]
            else:
                return [
                    "Ensure .close() or .destroy() is called on cleanup",
                    "Use try/finally or .finally() for guaranteed cleanup",
                ]

        return ["Ensure proper cleanup/close is called for this resource"]

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for potential resource leaks.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for unsafe resource patterns
        """
        findings = []
        language = context.language
        lines = context.lines

        patterns = self.RESOURCE_PATTERNS.get(language, [])
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

            for pattern, description, confidence in patterns:
                match = re.search(pattern, line)
                if match:
                    # Skip if in context manager
                    if self._is_in_context_manager(lines, line_num, language):
                        continue

                    # Extract variable name
                    var_name = self._extract_variable_name(line)

                    # Find function scope
                    func_end = self._find_function_end(lines, line_num, language)

                    # Check for cleanup in scope
                    if var_name and self._has_cleanup_in_scope(
                        lines, var_name, line_num, func_end, language
                    ):
                        continue

                    # Check for try/finally
                    if self._has_try_finally(lines, line_num, func_end, language):
                        continue

                    # Get code snippet
                    snippet = line.strip()
                    if len(snippet) > 100:
                        snippet = snippet[:100] + "..."

                    findings.append(
                        self._create_finding(
                            summary=description,
                            file_path=str(context.file_path),
                            line_number=line_num + 1,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num + 1,
                                    code_snippet=snippet,
                                    data={
                                        "pattern": pattern,
                                        "variable": var_name,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hint(
                                language, description
                            ),
                            confidence=confidence,
                        )
                    )

        return findings
