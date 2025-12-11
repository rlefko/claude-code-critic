"""
Unsafe null access detection rule.

Detects potentially unsafe accesses to values that could be
null/None/undefined without proper guards.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class UnsafeNullRule(BaseRule):
    """Detect potentially unsafe null/None/undefined access.

    Identifies patterns where code accesses properties or methods
    on values that might be null without proper guards like
    null checks, optional chaining, or default values.
    """

    # Risky patterns by language
    UNSAFE_PATTERNS = {
        "python": [
            # Direct access after potentially None-returning functions
            (
                r"\.get\s*\([^)]+\)\s*\.",
                "Accessing method on .get() result without None check",
                0.75,
            ),
            (
                r"\.get\s*\([^)]+\)\s*\[",
                "Indexing .get() result without None check",
                0.80,
            ),
            # Optional function returns
            (
                r"\.find\s*\([^)]+\)\s*\.",
                "Method call on find() result without None check",
                0.70,
            ),
            (
                r"re\.search\s*\([^)]+\)\s*\.group",
                "Accessing regex match group without None check",
                0.85,
            ),
            (
                r"re\.match\s*\([^)]+\)\s*\.group",
                "Accessing regex match group without None check",
                0.85,
            ),
            # Query results
            (
                r"\.first\s*\(\s*\)\s*\.",
                "Accessing attribute on .first() without None check",
                0.80,
            ),
            # Environment variables
            (
                r"os\.environ\.get\s*\([^)]+\)\s*\.",
                "Method on environ.get() without default",
                0.75,
            ),
            (
                r"os\.getenv\s*\([^)]+\)\s*\.",
                "Method on getenv() without None check",
                0.75,
            ),
        ],
        "javascript": [
            # DOM operations
            (
                r"getElementById\s*\([^)]+\)\s*\.(?!\?)",
                "DOM element access without null check",
                0.80,
            ),
            (
                r"querySelector\s*\([^)]+\)\s*\.(?!\?)",
                "DOM query result access without null check",
                0.80,
            ),
            (
                r"querySelectorAll\s*\([^)]+\)\s*\[",
                "Indexing querySelectorAll without length check",
                0.70,
            ),
            # Array methods
            (
                r"\.find\s*\([^)]+\)\s*\.(?!\?)",
                "Accessing property on .find() without null check",
                0.75,
            ),
            # JSON parsing
            (
                r"JSON\.parse\s*\([^)]+\)\s*\.(?!\?)",
                "Accessing parsed JSON without null check",
                0.70,
            ),
            # Storage
            (
                r"localStorage\.getItem\s*\([^)]+\)\s*\.(?!\?)",
                "Storage item access without null check",
                0.80,
            ),
            (
                r"sessionStorage\.getItem\s*\([^)]+\)\s*\.(?!\?)",
                "Storage item access without null check",
                0.80,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r"getElementById\s*\([^)]+\)\s*\.(?!\?)",
                "DOM element access without null check",
                0.80,
            ),
            (
                r"querySelector\s*\([^)]+\)\s*\.(?!\?)",
                "DOM query result access without null check",
                0.80,
            ),
            (
                r"\.find\s*\([^)]+\)\s*\.(?!\?)",
                "Accessing property on .find() without null check",
                0.75,
            ),
            # Non-null assertion abuse
            (
                r"!\s*\.",
                "Non-null assertion (!) used - ensure value is actually non-null",
                0.50,
            ),
            (
                r"as\s+\w+\s*\.",
                "Type assertion followed by property access",
                0.55,
            ),
        ],
    }

    # Safe patterns that indicate proper null handling
    SAFE_PATTERNS = [
        r"if\s+\w+\s*(is\s+not\s+None|!=\s*None|!==?\s*null|!==?\s*undefined)",
        r"if\s+\(\s*\w+\s*\)",  # Truthiness check
        r"\?\.",  # Optional chaining
        r"\?\?",  # Nullish coalescing
        r"\bor\s+",  # Python default
        r"\|\|",  # JS default
        r"try\s*:",  # Python try block
        r"try\s*\{",  # JS try
        r"\.get\s*\([^,]+,\s*[^)]+\)",  # .get() with default
        r"if\s+\w+:",  # Python truthiness check
        r"if\s*\(\w+\)",  # JS/TS truthiness check
    ]

    @property
    def rule_id(self) -> str:
        return "RESILIENCE.UNSAFE_NULL"

    @property
    def name(self) -> str:
        return "Missing Null Check Detection"

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
            "Detects potentially unsafe accesses to values that could be "
            "null/None/undefined without proper guards like null checks, "
            "optional chaining, or default values."
        )

    @property
    def is_fast(self) -> bool:
        return True  # Pattern matching only

    def _has_guard_nearby(
        self, lines: list[str], line_num: int, context_lines: int = 5
    ) -> bool:
        """Check if there's a null guard in the surrounding context."""
        start = max(0, line_num - context_lines)
        end = min(len(lines), line_num + 1)
        context = "\n".join(lines[start:end])

        for pattern in self.SAFE_PATTERNS:
            if re.search(pattern, context, re.IGNORECASE):
                return True

        return False

    def _get_remediation_hint(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        if language == "python":
            return [
                "Add an explicit `if x is not None:` check before accessing",
                "Use a default value: `x = value.get('key', default)` or `x or default`",
                "Wrap in a try/except block if None is possible",
            ]
        elif language in ("javascript", "typescript"):
            return [
                "Use optional chaining: `obj?.property` instead of `obj.property`",
                "Add null check: `if (obj) { obj.property }`",
                "Use nullish coalescing: `obj ?? default`",
            ]
        return ["Add appropriate null check before accessing the value"]

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for unsafe null accesses.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for unsafe null patterns
        """
        findings = []
        language = context.language
        lines = context.lines

        # Get patterns for this language
        patterns = self.UNSAFE_PATTERNS.get(language, [])
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
                    # Check for nearby guard
                    if self._has_guard_nearby(lines, line_num):
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
                            remediation_hints=self._get_remediation_hint(language),
                            confidence=confidence,
                        )
                    )

        return findings
