"""
Magic numbers detection rule.

Detects unexplained numeric literals that should be extracted
to named constants for better code readability and maintainability.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class MagicNumbersRule(BaseRule):
    """Detect magic numbers that should be named constants."""

    # Common acceptable numbers (don't flag these)
    DEFAULT_ALLOWED_NUMBERS = {0, 1, -1, 2, 10, 100, 1000}

    # Patterns to find numeric literals
    NUMBER_PATTERNS = {
        "python": r"(?<![a-zA-Z_\d\.])(-?\d+(?:\.\d+)?)\b(?![a-zA-Z_\[])",
        "javascript": r"(?<![a-zA-Z_\d\.])(-?\d+(?:\.\d+)?)\b(?![a-zA-Z_\[])",
        "typescript": r"(?<![a-zA-Z_\d\.])(-?\d+(?:\.\d+)?)\b(?![a-zA-Z_\[])",
    }

    # Patterns that indicate the number is acceptable
    ACCEPTABLE_CONTEXTS = [
        r"^\s*#",  # Comment line
        r"^\s*//",  # Comment line (JS)
        r'["\'].*\d+.*["\']',  # Inside string
        r"^\s*[A-Z_][A-Z0-9_]*\s*=",  # Constant definition (UPPER_CASE = value)
        r"range\s*\(\s*\d+",  # range() arguments
        r"enumerate\s*\(",  # enumerate()
        r"\[\s*\d+\s*\]",  # Array index
        r"\[\s*\d+\s*:\s*\d*\s*\]",  # Slice notation
        r":\s*\d+\s*\]",  # Slice end
        r"sleep\s*\(",  # sleep() is often acceptable
        r"time\.\w+\s*\(",  # time functions
        r"datetime\.",  # datetime operations
        r"timedelta\s*\(",  # timedelta
        r"timeout\s*=",  # timeout parameter
        r"retry\s*=",  # retry parameter
        r"max_\w+\s*=",  # max_* parameter
        r"min_\w+\s*=",  # min_* parameter
        r"port\s*=",  # port parameter
        r"version\s*=",  # version number
        r"__version__",  # version string
        r"assert\s+",  # assertions often use literals
        r"pytest\.param\(",  # pytest parameters
        r"@pytest\.",  # pytest decorators
    ]

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.MAGIC_NUMBERS"

    @property
    def name(self) -> str:
        return "Magic Numbers Detection"

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
            "Detects unexplained numeric literals (magic numbers) that should be "
            "extracted to named constants. Named constants improve code readability "
            "and make values easier to update."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_acceptable_context(self, line: str) -> bool:
        """Check if the line contains an acceptable context for magic numbers."""
        for pattern in self.ACCEPTABLE_CONTEXTS:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def _is_test_file(self, file_path: str) -> bool:
        """Check if the file is a test file."""
        file_path_lower = file_path.lower()
        return any(
            marker in file_path_lower
            for marker in [
                "test_",
                "_test",
                "tests/",
                "spec/",
                "__tests__/",
                ".test.",
                ".spec.",
            ]
        )

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for magic numbers.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected magic numbers
        """
        findings = []
        language = context.language

        # Skip unsupported languages
        if language not in self.NUMBER_PATTERNS:
            return findings

        # Get configuration
        allowed_numbers = set(self.DEFAULT_ALLOWED_NUMBERS)
        if context.config:
            config_allowed = context.config.get_rule_parameter(
                self.rule_id, "allowed_numbers", None
            )
            if config_allowed:
                allowed_numbers = set(config_allowed)

        # Skip test files (common to use literals in tests)
        file_path_str = str(context.file_path)
        is_test_file = self._is_test_file(file_path_str)
        if is_test_file:
            return findings

        pattern = self.NUMBER_PATTERNS[language]
        lines = context.lines

        # Track findings by line to avoid duplicates
        reported_lines: set[int] = set()

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip if acceptable context
            if self._is_acceptable_context(line):
                continue

            # Find all numbers in line
            matches = list(re.finditer(pattern, line))

            for match in matches:
                try:
                    number_str = match.group(1)
                    # Try to parse as int or float
                    number = float(number_str) if "." in number_str else int(number_str)

                    # Skip allowed numbers
                    if number in allowed_numbers:
                        continue

                    # Skip very small numbers (likely acceptable)
                    if abs(number) <= 2:
                        continue

                    # Skip already reported lines
                    if line_num in reported_lines:
                        continue

                    reported_lines.add(line_num)

                    findings.append(
                        self._create_finding(
                            summary=f"Magic number: {number_str}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=f"Unexplained numeric literal {number_str} should be a named constant",
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "number": number,
                                        "number_str": number_str,
                                        "position": match.start(),
                                    },
                                )
                            ],
                            remediation_hints=[
                                f"Extract {number_str} to a named constant with a descriptive name",
                                "Example: MAX_RETRY_COUNT = 5 instead of using 5 directly",
                                "Constants improve readability and make values easier to update",
                            ],
                            confidence=0.7,  # Lower confidence as context matters
                        )
                    )

                except (ValueError, TypeError):
                    continue

        return findings
