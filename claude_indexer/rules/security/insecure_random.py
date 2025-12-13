"""
Insecure random number generation detection rule.

Detects use of non-cryptographically secure random number generators
in security-sensitive contexts like token generation or password creation.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class InsecureRandomRule(BaseRule):
    """Detect insecure random number generation for security purposes."""

    # Language-specific patterns for insecure random
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # random module for security-sensitive operations
            (
                r"random\.(random|randint|choice|randrange|sample|shuffle)\s*\(",
                "random module is not cryptographically secure",
                0.60,
            ),
            # Math.random equivalents
            (
                r"import\s+random\b",
                "random module imported (not secure for cryptographic use)",
                0.40,
            ),
        ],
        "javascript": [
            # Math.random
            (
                r"Math\.random\s*\(\)",
                "Math.random() is not cryptographically secure",
                0.60,
            ),
        ],
        "typescript": [
            # Math.random
            (
                r"Math\.random\s*\(\)",
                "Math.random() is not cryptographically secure",
                0.60,
            ),
        ],
        "java": [
            # java.util.Random
            (
                r"new\s+Random\s*\(",
                "java.util.Random is not cryptographically secure",
                0.60,
            ),
            (
                r"Math\.random\s*\(\)",
                "Math.random() is not cryptographically secure",
                0.60,
            ),
        ],
        "go": [
            # math/rand
            (
                r"rand\.(Int|Float|Intn|Read)\s*\(",
                "math/rand is not cryptographically secure",
                0.60,
            ),
        ],
        "ruby": [
            # rand/Random
            (
                r"\brand\s*\(|Random\.rand",
                "rand is not cryptographically secure",
                0.60,
            ),
        ],
        "php": [
            # rand, mt_rand
            (
                r"\b(rand|mt_rand|array_rand)\s*\(",
                "rand/mt_rand are not cryptographically secure",
                0.60,
            ),
        ],
    }

    # Security-sensitive context patterns (increases confidence)
    SECURITY_CONTEXT_PATTERNS = [
        r"token",
        r"password",
        r"secret",
        r"key",
        r"salt",
        r"nonce",
        r"iv\b",
        r"auth",
        r"session",
        r"csrf",
        r"reset",
        r"verify",
        r"otp",
        r"pin\b",
        r"code\b",
    ]

    @property
    def rule_id(self) -> str:
        return "SECURITY.INSECURE_RANDOM"

    @property
    def name(self) -> str:
        return "Insecure Random Detection"

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
            "Detects use of non-cryptographically secure random number generators "
            "in contexts where cryptographic randomness is required."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_security_context(self, line: str, surrounding_lines: list[str]) -> bool:
        """Check if the random usage is in a security-sensitive context."""
        # Check the current line and a few surrounding lines
        text_to_check = line + " " + " ".join(surrounding_lines)
        for pattern in self.SECURITY_CONTEXT_PATTERNS:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for insecure random number generation.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected insecure random usage
        """
        findings = []
        language = context.language

        # Get patterns for this language
        patterns = self.PATTERNS.get(language, [])
        if not patterns:
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

            for pattern, description, base_confidence in patterns:
                if re.search(pattern, line):
                    # Get surrounding lines for context analysis
                    start = max(0, line_num - 3)
                    end = min(len(lines), line_num + 2)
                    surrounding = lines[start:end]

                    # Check if it's in a security-sensitive context
                    in_security_context = self._is_security_context(line, surrounding)

                    # Adjust confidence based on context
                    if in_security_context:
                        confidence = min(base_confidence + 0.30, 0.95)
                    elif is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    # Only report high-confidence findings or security context
                    if confidence < 0.50 and not in_security_context:
                        continue

                    # Get language-specific remediation
                    remediation = self._get_remediation_hints(language)

                    findings.append(
                        self._create_finding(
                            summary=f"Insecure random: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
                                        "in_security_context": in_security_context,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=remediation,
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        hints = {
            "python": [
                "Use secrets.token_hex() or secrets.token_urlsafe() for tokens",
                "Use secrets.choice() for cryptographically secure random selection",
                "Use os.urandom() for raw random bytes",
            ],
            "javascript": [
                "Use crypto.randomBytes() for cryptographically secure random",
                "Use crypto.getRandomValues() in browser environments",
                "Use a library like 'uuid' for unique identifiers",
            ],
            "typescript": [
                "Use crypto.randomBytes() for cryptographically secure random",
                "Use crypto.getRandomValues() in browser environments",
                "Use a library like 'uuid' for unique identifiers",
            ],
            "java": [
                "Use java.security.SecureRandom instead of java.util.Random",
                "Example: SecureRandom.getInstanceStrong().nextBytes(bytes)",
            ],
            "go": [
                "Use crypto/rand instead of math/rand for security-sensitive operations",
                "Example: rand.Read(bytes) from crypto/rand package",
            ],
            "ruby": [
                "Use SecureRandom.hex() or SecureRandom.urlsafe_base64()",
                "Use OpenSSL::Random for cryptographic operations",
            ],
            "php": [
                "Use random_bytes() or random_int() (PHP 7+)",
                "Use openssl_random_pseudo_bytes() for secure random bytes",
            ],
        }
        return hints.get(
            language,
            [
                "Use a cryptographically secure random number generator",
                "Consult your language's documentation for secure alternatives",
            ],
        )
