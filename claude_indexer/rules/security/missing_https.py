"""
Missing HTTPS detection rule.

Detects HTTP URLs that should use HTTPS for security,
especially for API endpoints, webhooks, and authentication.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class MissingHTTPSRule(BaseRule):
    """Detect HTTP URLs that should use HTTPS."""

    # Patterns for HTTP URLs that should use HTTPS
    # Format: (pattern, description, confidence)
    HTTP_PATTERNS = [
        # API endpoints over HTTP
        (
            r'http://[^"\'\s]+\.(com|org|net|io|dev|co|app)/api/',
            "HTTP API endpoint (should use HTTPS)",
            0.90,
        ),
        # Webhook URLs over HTTP
        (
            r'http://[^"\'\s]+/webhook',
            "HTTP webhook URL (should use HTTPS)",
            0.90,
        ),
        # Auth/login endpoints over HTTP
        (
            r'http://[^"\'\s]+/(auth|login|signin|oauth|token)',
            "Authentication endpoint over HTTP",
            0.95,
        ),
        # Payment/checkout URLs
        (
            r'http://[^"\'\s]+/(pay|checkout|billing|stripe|payment)',
            "Payment endpoint over HTTP",
            0.95,
        ),
        # Generic external HTTP URLs (lower confidence)
        (
            r'http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[a-zA-Z0-9][^"\'\s]{10,}',
            "HTTP URL (consider using HTTPS)",
            0.70,
        ),
    ]

    # Patterns to exclude (false positives)
    EXCLUDE_PATTERNS = [
        r'localhost',
        r'127\.0\.0\.1',
        r'0\.0\.0\.0',
        r'192\.168\.',
        r'10\.',
        r'172\.(1[6-9]|2[0-9]|3[01])\.',
        r'example\.com',
        r'example\.org',
        r'test\.com',
        r'\[::1\]',  # IPv6 localhost
        r'\.local\b',
        r'\.internal\b',
        r'\.dev\.local',
    ]

    @property
    def rule_id(self) -> str:
        return "SECURITY.MISSING_HTTPS"

    @property
    def name(self) -> str:
        return "Missing HTTPS Detection"

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
        # HTTP URLs can be in any file type
        return None

    @property
    def description(self) -> str:
        return (
            "Detects HTTP URLs that should use HTTPS for secure communication, "
            "especially for API endpoints, webhooks, and authentication."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_excluded_url(self, url: str) -> bool:
        """Check if URL should be excluded (local/dev environment)."""
        for pattern in self.EXCLUDE_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for HTTP URLs that should use HTTPS.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected insecure URLs
        """
        findings = []
        file_path_str = str(context.file_path)

        # Check if this is a test/config file (lower severity)
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

            for pattern, description, base_confidence in self.HTTP_PATTERNS:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    matched_url = match.group(0)

                    # Skip excluded URLs (localhost, private IPs, etc.)
                    if self._is_excluded_url(matched_url):
                        continue

                    # Adjust confidence for test files
                    confidence = base_confidence * 0.6 if is_test_file else base_confidence

                    findings.append(
                        self._create_finding(
                            summary=f"Insecure HTTP URL: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "url": matched_url,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=[
                                "Replace http:// with https:// for secure communication",
                                "Ensure the server supports HTTPS and has valid SSL certificates",
                                "Use HSTS headers to enforce HTTPS connections",
                            ],
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def can_auto_fix(self) -> bool:
        return True

    def auto_fix(
        self, finding: Finding, context: RuleContext
    ) -> "AutoFix | None":
        """Generate auto-fix to replace http:// with https://.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix to replace HTTP with HTTPS
        """
        from ..fix import AutoFix

        if finding.line_number is None:
            return None

        line = context.get_line_content(finding.line_number)
        if line is None:
            return None

        # Simple replacement of http:// to https://
        # Only if the URL is not a local/dev URL
        url_match = re.search(r'http://[^\s"\'>]+', line)
        if url_match and not self._is_excluded_url(url_match.group(0)):
            new_line = line.replace("http://", "https://", 1)
            return AutoFix(
                finding=finding,
                old_code=line,
                new_code=new_line,
                line_start=finding.line_number,
                line_end=finding.line_number,
                description="Replace http:// with https://",
            )

        return None
