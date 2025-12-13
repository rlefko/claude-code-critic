"""
Unsafe concurrency detection rule.

Detects potential race conditions, shared state without locking,
and other concurrency anti-patterns.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class UnsafeConcurrencyRule(BaseRule):
    """Detect potential concurrency issues.

    Identifies patterns that may lead to race conditions, such as
    shared state modification without locking, check-then-act patterns
    (TOCTOU), and async functions without proper await.
    """

    # Concurrency risk patterns by language
    CONCURRENCY_PATTERNS = {
        "python": [
            # Global state modification
            (
                r"^\s*global\s+\w+",
                "Global variable modification - consider thread safety",
                0.65,
            ),
            # Check-then-act patterns
            (
                r"if\s+\w+\s*(==|is|in).*:\s*$",
                "Check-then-act pattern - may have race condition",
                0.50,
            ),
            # Daemon threads without join
            (
                r"\.daemon\s*=\s*True",
                "Daemon thread - data may be lost on exit",
                0.50,
            ),
            # Async without await
            (
                r"async\s+def\s+\w+.*:\s*$",
                "Async function - verify await usage",
                0.40,
            ),
            # Shared mutable default arguments
            (
                r"def\s+\w+\s*\([^)]*=\s*\[\s*\]",
                "Mutable default argument (list) - shared across calls",
                0.75,
            ),
            (
                r"def\s+\w+\s*\([^)]*=\s*\{\s*\}",
                "Mutable default argument (dict) - shared across calls",
                0.75,
            ),
        ],
        "javascript": [
            # Shared state in callbacks/promises
            (
                r"let\s+\w+\s*=.*;[\s\S]*?\.then\s*\(",
                "Variable may be modified in async callback",
                0.55,
            ),
            (
                r"var\s+\w+.*;[\s\S]*?setTimeout\s*\(",
                "var in closure with setTimeout - potential race",
                0.55,
            ),
            # Event loop blocking
            (
                r"while\s*\([^)]+\)\s*\{(?![\s\S]*?await)",
                "Synchronous while loop may block event loop",
                0.60,
            ),
            # Async without await
            (
                r"async\s+function\s+\w+\s*\([^)]*\)\s*\{(?![\s\S]*?await)",
                "Async function without await",
                0.50,
            ),
        ],
        "typescript": [
            # Same as JavaScript plus class-specific
            (
                r"private\s+\w+\s*[=:][^;]+;",
                "Private mutable field - verify thread safety if shared",
                0.40,
            ),
            (
                r"async\s+\w+\s*\([^)]*\)\s*:\s*Promise",
                "Async method - verify await usage",
                0.45,
            ),
            (
                r"while\s*\([^)]+\)\s*\{(?![\s\S]*?await)",
                "Synchronous loop may block event loop",
                0.60,
            ),
        ],
    }

    # Patterns indicating proper synchronization
    SAFE_PATTERNS = {
        "python": [
            r"threading\.Lock\s*\(",
            r"threading\.RLock\s*\(",
            r"asyncio\.Lock\s*\(",
            r"with\s+\w*lock",
            r"\.acquire\s*\(",
            r"@synchronized",
            r"multiprocessing\.Manager",
            r"queue\.Queue",
            r"concurrent\.futures",
        ],
        "javascript": [
            r"\bmutex\b",
            r"\bsemaphore\b",
            r"\block\b",
            r"await\s+",
        ],
        "typescript": [
            r"\bmutex\b",
            r"\bsemaphore\b",
            r"@Lock\b",
            r"synchronized",
            r"await\s+",
        ],
    }

    @property
    def rule_id(self) -> str:
        return "RESILIENCE.UNSAFE_CONCURRENCY"

    @property
    def name(self) -> str:
        return "Concurrency Issue Detection"

    @property
    def category(self) -> str:
        return "resilience"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects potential concurrency issues including race conditions, "
            "shared state without locking, check-then-act (TOCTOU) patterns, "
            "and async functions without proper await."
        )

    @property
    def is_fast(self) -> bool:
        return True  # Pattern matching only

    def _has_synchronization(
        self, lines: list[str], start: int, end: int, language: str
    ) -> bool:
        """Check if code section has proper synchronization."""
        patterns = self.SAFE_PATTERNS.get(language, [])
        context = "\n".join(lines[max(0, start - 10) : min(len(lines), end + 5)])

        return any(re.search(pattern, context, re.IGNORECASE) for pattern in patterns)

    def _find_function_bounds(
        self, lines: list[str], line_num: int, language: str
    ) -> tuple[int, int]:
        """Find the bounds of the function containing this line."""
        start = 0
        end = len(lines) - 1

        if language == "python":
            # Find function start
            for i in range(line_num, -1, -1):
                if re.search(r"^\s*(?:async\s+)?def\s+", lines[i]):
                    start = i
                    break

            # Find function end
            base_indent = len(lines[start]) - len(lines[start].lstrip())
            for i in range(line_num + 1, len(lines)):
                stripped = lines[i].strip()
                if not stripped:
                    continue
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if current_indent <= base_indent:
                    end = i - 1
                    break
        else:
            # Find function start (look for function/async function)
            brace_count = 0
            for i in range(line_num, -1, -1):
                if re.search(r"(?:async\s+)?function\s+\w+|=>\s*\{", lines[i]):
                    start = i
                    break

            # Count braces for end
            for i in range(start, len(lines)):
                for char in lines[i]:
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end = i
                            break
                if brace_count == 0 and i > start:
                    break

        return (start, end)

    def _is_async_without_await(self, lines: list[str], start: int, end: int) -> bool:
        """Check if async function lacks await statements."""
        for i in range(start, min(end + 1, len(lines))):
            if re.search(r"\bawait\s+", lines[i]):
                return False
        return True

    def _get_remediation_hint(self, description: str, language: str) -> list[str]:
        """Get specific remediation hints based on the issue."""
        hints = []

        if "global" in description.lower():
            hints = [
                "Protect global state with threading.Lock() or asyncio.Lock()",
                "Consider using thread-local storage (threading.local())",
                "Pass state as function parameters instead of using globals",
            ]
        elif "check-then-act" in description.lower() or "race" in description.lower():
            hints = [
                "Use atomic operations or locks to prevent race conditions",
                "Consider using compare-and-swap patterns",
                "Use database transactions for atomic updates",
            ]
        elif "daemon" in description.lower():
            hints = [
                "Call thread.join() before program exit for clean shutdown",
                "Use atexit handlers to wait for daemon threads",
                "Consider using regular threads if data integrity is important",
            ]
        elif "mutable default" in description.lower():
            hints = [
                "Use None as default and initialize inside function",
                "Example: `def func(items=None): items = items or []`",
            ]
        elif "async" in description.lower() or "await" in description.lower():
            hints = [
                "Ensure await is used for all async operations",
                "Missing await can cause unexpected behavior",
            ]
        elif "event loop" in description.lower() or "block" in description.lower():
            hints = [
                "Avoid long-running synchronous operations in async code",
                "Use setImmediate/nextTick or move blocking work to a worker",
            ]
        else:
            hints = [
                "Review this code for potential race conditions",
                "Consider using appropriate synchronization primitives",
            ]

        return hints

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for concurrency issues.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for concurrency patterns
        """
        findings = []
        language = context.language
        lines = context.lines

        patterns = self.CONCURRENCY_PATTERNS.get(language, [])
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
                    # Get function bounds
                    start, end = self._find_function_bounds(lines, line_num, language)

                    # Check for synchronization
                    if self._has_synchronization(lines, start, end, language):
                        continue

                    # Special check for async without await
                    if (
                        "async" in description.lower()
                        and "await" in description.lower()
                    ) and not self._is_async_without_await(lines, start, end):
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
                                        "match": match.group(0),
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hint(
                                description, language
                            ),
                            confidence=confidence,
                        )
                    )

        return findings
