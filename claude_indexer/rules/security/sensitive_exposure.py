"""
Sensitive data exposure detection rule.

Detects logging, printing, or exposing sensitive information
like passwords, tokens, API keys, and personal data.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class SensitiveExposureRule(BaseRule):
    """Detect sensitive data exposure in logs and output."""

    # Sensitive data keywords to detect
    SENSITIVE_KEYWORDS = [
        r'password',
        r'passwd',
        r'secret',
        r'api[_-]?key',
        r'apikey',
        r'auth[_-]?token',
        r'access[_-]?token',
        r'refresh[_-]?token',
        r'bearer',
        r'credential',
        r'private[_-]?key',
        r'ssn',
        r'social[_-]?security',
        r'credit[_-]?card',
        r'card[_-]?number',
        r'cvv',
        r'pin\b',
    ]

    # Language-specific patterns for sensitive data exposure
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # Logging sensitive data
            (
                r'(logger|logging)\.(info|debug|warning|error|critical)\s*\([^)]*({keywords})',
                "Logging {match} (sensitive data exposure)",
                0.90,
            ),
            # Print sensitive data
            (
                r'print\s*\([^)]*({keywords})',
                "Printing {match} (sensitive data exposure)",
                0.85,
            ),
            # Exception messages with sensitive data
            (
                r'raise\s+\w+\s*\([^)]*({keywords})',
                "Exception message contains {match}",
                0.85,
            ),
            # f-string with sensitive data
            (
                r'f["\'][^"\']*\{{[^}}]*({keywords})[^}}]*\}}',
                "f-string contains {match}",
                0.80,
            ),
        ],
        "javascript": [
            # Console logging sensitive data
            (
                r'console\.(log|info|debug|warn|error)\s*\([^)]*({keywords})',
                "console.log with {match} (sensitive data exposure)",
                0.90,
            ),
            # JSON.stringify of sensitive objects
            (
                r'JSON\.stringify\s*\([^)]*({keywords})',
                "JSON.stringify contains {match}",
                0.80,
            ),
            # Alert with sensitive data
            (
                r'alert\s*\([^)]*({keywords})',
                "alert() with {match}",
                0.90,
            ),
            # Response with sensitive data
            (
                r'res\.(send|json)\s*\([^)]*({keywords})',
                "Response contains {match}",
                0.80,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r'console\.(log|info|debug|warn|error)\s*\([^)]*({keywords})',
                "console.log with {match} (sensitive data exposure)",
                0.90,
            ),
            (
                r'JSON\.stringify\s*\([^)]*({keywords})',
                "JSON.stringify contains {match}",
                0.80,
            ),
        ],
        "java": [
            # Logger with sensitive data
            (
                r'(logger|LOG)\.(info|debug|warn|error|trace)\s*\([^)]*({keywords})',
                "Logger with {match} (sensitive data exposure)",
                0.90,
            ),
            # System.out with sensitive data
            (
                r'System\.(out|err)\.print(ln)?\s*\([^)]*({keywords})',
                "System.out with {match}",
                0.85,
            ),
            # Exception with sensitive data
            (
                r'throw\s+new\s+\w+\s*\([^)]*({keywords})',
                "Exception message contains {match}",
                0.85,
            ),
        ],
        "php": [
            # echo/print sensitive data
            (
                r'(echo|print)\s+.*\$({keywords})',
                "Outputting {match} (sensitive data exposure)",
                0.85,
            ),
            # error_log with sensitive data
            (
                r'error_log\s*\([^)]*\$({keywords})',
                "error_log with {match}",
                0.90,
            ),
            # var_dump/print_r sensitive data
            (
                r'(var_dump|print_r)\s*\([^)]*\$({keywords})',
                "Debug output with {match}",
                0.85,
            ),
        ],
        "go": [
            # fmt.Print/log with sensitive data
            (
                r'(fmt|log)\.(Print|Println|Printf|Fprint)\s*\([^)]*({keywords})',
                "Logging {match} (sensitive data exposure)",
                0.90,
            ),
            # Error messages with sensitive data
            (
                r'errors\.(New|Errorf)\s*\([^)]*({keywords})',
                "Error message contains {match}",
                0.85,
            ),
        ],
        "ruby": [
            # puts/print sensitive data
            (
                r'(puts|print|p)\s+.*({keywords})',
                "Outputting {match} (sensitive data exposure)",
                0.85,
            ),
            # Rails logger with sensitive data
            (
                r'(Rails\.)?logger\.(info|debug|warn|error)\s+.*({keywords})',
                "Logger with {match}",
                0.90,
            ),
            # Exception with sensitive data
            (
                r'raise\s+.*({keywords})',
                "Exception message contains {match}",
                0.85,
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "SECURITY.SENSITIVE_EXPOSURE"

    @property
    def name(self) -> str:
        return "Sensitive Data Exposure Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return list(self.PATTERNS.keys())

    @property
    def description(self) -> str:
        return (
            "Detects logging, printing, or exposing sensitive information "
            "like passwords, tokens, API keys, and personal data."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _build_pattern(self, pattern_template: str) -> str:
        """Build pattern with sensitive keywords."""
        keywords_pattern = "|".join(self.SENSITIVE_KEYWORDS)
        return pattern_template.replace("{keywords}", keywords_pattern)

    def _get_matched_keyword(self, line: str) -> str | None:
        """Get the matched sensitive keyword from a line."""
        for keyword in self.SENSITIVE_KEYWORDS:
            if re.search(keyword, line, re.IGNORECASE):
                match = re.search(keyword, line, re.IGNORECASE)
                if match:
                    return match.group(0)
        return None

    def _is_redacted(self, line: str) -> bool:
        """Check if the sensitive data appears to be redacted."""
        redaction_patterns = [
            r'\*+',
            r'\[REDACTED\]',
            r'\[HIDDEN\]',
            r'\[MASKED\]',
            r'<redacted>',
            r'xxx+',
            r'\.{3,}',
            r'mask',
            r'redact',
            r'hide',
            r'filter',
        ]
        for pattern in redaction_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for sensitive data exposure.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected sensitive data exposure
        """
        findings = []
        language = context.language

        # Get patterns for this language
        pattern_templates = self.PATTERNS.get(language, [])
        if not pattern_templates:
            return findings

        file_path_str = str(context.file_path)

        # Check if this is a test file
        is_test_file = any(
            marker in file_path_str.lower()
            for marker in ["test_", "_test", "tests/", "spec/", "mock/", "fixture"]
        )

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Skip lines with nosec markers
            if "nosec" in line.lower() or "noqa" in line.lower():
                continue

            # Skip if data appears redacted
            if self._is_redacted(line):
                continue

            for pattern_template, desc_template, base_confidence in pattern_templates:
                pattern = self._build_pattern(pattern_template)
                if re.search(pattern, line, re.IGNORECASE):
                    # Get the specific keyword that matched
                    matched_keyword = self._get_matched_keyword(line)
                    description = desc_template.replace("{match}", matched_keyword or "sensitive data")

                    if is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    findings.append(
                        self._create_finding(
                            summary=f"Sensitive data exposure: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=self._redact_line(line.strip()),
                                    data={
                                        "language": language,
                                        "matched_keyword": matched_keyword,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hints(language),
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _redact_line(self, line: str) -> str:
        """Redact potential sensitive values in the line for safe display."""
        # Redact quoted strings that look like they might contain sensitive data
        for keyword in self.SENSITIVE_KEYWORDS:
            if re.search(keyword, line, re.IGNORECASE):
                # Redact the value assignment
                line = re.sub(
                    rf'({keyword}\s*[=:]\s*)["\'][^"\']+["\']',
                    r'\1"[REDACTED]"',
                    line,
                    flags=re.IGNORECASE
                )
        return line

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        return [
            "Never log sensitive data like passwords, tokens, or API keys",
            "Use structured logging with sensitive field filters/redaction",
            "Review error messages to ensure they don't expose sensitive information",
            "Configure your logging framework to automatically mask sensitive fields",
        ]
