"""
Hardcoded secrets detection rule.

Detects hardcoded API keys, passwords, tokens, and other secrets
that should not be committed to source code.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class HardcodedSecretsRule(BaseRule):
    """Detect hardcoded secrets in source code."""

    # Patterns for detecting various types of secrets
    # Format: (pattern, description, confidence)
    SECRET_PATTERNS = [
        # AWS Keys
        (
            r'(?i)(aws[_-]?access[_-]?key[_-]?id)\s*[=:]\s*["\']?(AKIA[A-Z0-9]{16})["\']?',
            "AWS Access Key ID",
            0.98,
        ),
        (
            r'(?i)(aws[_-]?secret[_-]?access[_-]?key)\s*[=:]\s*["\'][a-zA-Z0-9/+=]{40}["\']',
            "AWS Secret Access Key",
            0.98,
        ),
        # GitHub Tokens
        (
            r"gh[pousr]_[A-Za-z0-9_]{36,}",
            "GitHub personal access token",
            0.98,
        ),
        # Slack Tokens
        (
            r"xox[baprs]-[0-9]{10,}-[a-zA-Z0-9]{10,}",
            "Slack token",
            0.98,
        ),
        # Private Keys
        (
            r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----",
            "Private key in source code",
            0.98,
        ),
        # Generic API Keys
        (
            r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}["\']',
            "Hardcoded API key",
            0.90,
        ),
        # Bearer Tokens
        (
            r'(?i)["\']?bearer\s+[a-zA-Z0-9_\-\.]{20,}["\']?',
            "Hardcoded bearer token",
            0.90,
        ),
        # JWT Tokens
        (
            r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*",
            "JWT token in source code",
            0.90,
        ),
        # Database Connection Strings with credentials
        (
            r"(?i)(mongodb|postgres|mysql|redis|postgresql)://[^:]+:[^@]+@",
            "Database connection string with credentials",
            0.95,
        ),
        # Password assignments
        (
            r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']',
            "Hardcoded password",
            0.85,
        ),
        # Generic secret/token patterns
        (
            r'(?i)(secret|token|auth)[_-]?(key|token|secret)?\s*[=:]\s*["\'][a-zA-Z0-9_\-]{20,}["\']',
            "Hardcoded secret/token",
            0.80,
        ),
        # Stripe Keys
        (
            r"sk_live_[a-zA-Z0-9]{24,}",
            "Stripe live secret key",
            0.98,
        ),
        (
            r"pk_live_[a-zA-Z0-9]{24,}",
            "Stripe live publishable key",
            0.95,
        ),
        # SendGrid API Key
        (
            r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
            "SendGrid API key",
            0.98,
        ),
        # Twilio
        (
            r'(?i)twilio[_-]?(auth[_-]?token|account[_-]?sid)\s*[=:]\s*["\'][a-zA-Z0-9]{32,}["\']',
            "Twilio credential",
            0.95,
        ),
        # Google API Key
        (
            r"AIza[0-9A-Za-z_-]{35}",
            "Google API key",
            0.95,
        ),
        # Heroku API Key
        (
            r'(?i)heroku[_-]?api[_-]?key\s*[=:]\s*["\'][a-f0-9-]{36}["\']',
            "Heroku API key",
            0.95,
        ),
        # OpenAI API Key
        (
            r"sk-[a-zA-Z0-9]{48,}",
            "OpenAI API key",
            0.95,
        ),
    ]

    # Placeholder values to ignore (false positives)
    PLACEHOLDER_PATTERNS = [
        r"(?i)xxx+",
        r"(?i)your[_-].*[_-]here",
        r"(?i)change[_-]?me",
        r"(?i)placeholder",
        r"(?i)example",
        r"(?i)sample",
        r"(?i)dummy",
        r"(?i)test[_-]?key",
        r"(?i)fake[_-]?",
        r"(?i)mock[_-]?",
        r"(?i)<.*>",  # Template placeholders like <API_KEY>
        r"(?i)\$\{.*\}",  # Variable placeholders like ${API_KEY}
        r"(?i)TODO",
        r"(?i)FIXME",
    ]

    # File patterns to skip or lower confidence
    SKIP_FILE_PATTERNS = [
        r"\.example$",
        r"\.sample$",
        r"\.template$",
        r"\.dist$",
    ]

    @property
    def rule_id(self) -> str:
        return "SECURITY.HARDCODED_SECRETS"

    @property
    def name(self) -> str:
        return "Hardcoded Secrets Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        # Secrets can be in any file type
        return None

    @property
    def description(self) -> str:
        return (
            "Detects hardcoded secrets such as API keys, passwords, tokens, "
            "and private keys that should not be committed to version control."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_placeholder(self, value: str) -> bool:
        """Check if a detected value is a placeholder."""
        return any(re.search(pattern, value) for pattern in self.PLACEHOLDER_PATTERNS)

    def _is_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped based on name pattern."""
        return any(re.search(pattern, file_path) for pattern in self.SKIP_FILE_PATTERNS)

    def _is_env_reference(self, line: str) -> bool:
        """Check if the line references environment variables."""
        env_patterns = [
            r"os\.environ",
            r"os\.getenv",
            r"process\.env",
            r"ENV\[",
            r"getenv\(",
            r"\$\{[A-Z_]+\}",  # Shell variable substitution
        ]
        return any(re.search(pattern, line) for pattern in env_patterns)

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for hardcoded secrets in the file.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected secrets
        """
        findings = []
        file_path_str = str(context.file_path)

        # Skip example/template files entirely
        if self._is_skip_file(file_path_str):
            return findings

        # Check if this is a test file (lower severity)
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

            # Skip lines that reference environment variables
            if self._is_env_reference(line):
                continue

            # Skip lines with nosec markers
            if "nosec" in line.lower() or "noqa" in line.lower():
                continue

            for pattern, description, base_confidence in self.SECRET_PATTERNS:
                match = re.search(pattern, line)
                if match:
                    matched_text = match.group(0)

                    # Skip if it looks like a placeholder
                    if self._is_placeholder(matched_text):
                        continue

                    # Adjust confidence for test files
                    confidence = (
                        base_confidence * 0.7 if is_test_file else base_confidence
                    )

                    findings.append(
                        self._create_finding(
                            summary=f"Hardcoded secret: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=self._redact_secret(line.strip()),
                                    data={
                                        "pattern_type": description,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=[
                                "Use environment variables: os.environ.get('SECRET_NAME')",
                                "Use a secrets manager (AWS Secrets Manager, HashiCorp Vault)",
                                "Store secrets in .env files and add to .gitignore",
                            ],
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _redact_secret(self, line: str) -> str:
        """Redact secret values in the line for safe display."""
        # Redact anything that looks like a secret value
        redacted = re.sub(r'["\'][a-zA-Z0-9_\-\.+=/]{20,}["\']', '"[REDACTED]"', line)
        # Redact private key content
        redacted = re.sub(r"-----BEGIN.*-----", "-----BEGIN [REDACTED]-----", redacted)
        return redacted
