"""
Insecure cryptography detection rule.

Detects use of weak or deprecated cryptographic algorithms
such as MD5, SHA1, DES, and insecure cipher modes.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class InsecureCryptoRule(BaseRule):
    """Detect use of weak or deprecated cryptographic algorithms."""

    # Language-specific patterns for insecure crypto
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # MD5
            (
                r"hashlib\.md5\s*\(",
                "MD5 is cryptographically broken",
                0.85,
            ),
            (
                r"from\s+hashlib\s+import.*\bmd5\b",
                "MD5 import (weak hash algorithm)",
                0.80,
            ),
            # SHA1
            (
                r"hashlib\.sha1\s*\(",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            (
                r"from\s+hashlib\s+import.*\bsha1\b",
                "SHA1 import (deprecated for security)",
                0.75,
            ),
            # DES encryption
            (
                r"DES\.(new|MODE_)",
                "DES is insecure due to small key size",
                0.95,
            ),
            (
                r"from\s+Crypto\.Cipher\s+import\s+DES",
                "DES import (insecure cipher)",
                0.90,
            ),
            # ECB mode
            (
                r"MODE_ECB|AES\.MODE_ECB",
                "ECB mode is insecure (reveals patterns)",
                0.95,
            ),
            # RC4
            (
                r"ARC4|RC4",
                "RC4 is cryptographically broken",
                0.95,
            ),
            # Blowfish (deprecated)
            (
                r"Blowfish\.(new|MODE_)",
                "Blowfish is deprecated for new applications",
                0.70,
            ),
            # Hardcoded IV
            (
                r'iv\s*=\s*b?["\'][a-zA-Z0-9+/=]{16,}["\']',
                "Hardcoded IV (should be random)",
                0.85,
            ),
            # Hardcoded salt
            (
                r'salt\s*=\s*b?["\'][a-zA-Z0-9+/=]{8,}["\']',
                "Hardcoded salt (should be random)",
                0.85,
            ),
        ],
        "javascript": [
            # MD5
            (
                r"(crypto|CryptoJS)\..*MD5",
                "MD5 is cryptographically broken",
                0.85,
            ),
            (
                r"createHash\s*\(\s*['\"]md5['\"]",
                "MD5 hash (cryptographically broken)",
                0.85,
            ),
            # SHA1
            (
                r"(crypto|CryptoJS)\..*SHA1",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            (
                r"createHash\s*\(\s*['\"]sha1['\"]",
                "SHA1 hash (deprecated for security)",
                0.80,
            ),
            # createCipher (deprecated)
            (
                r"createCipher\s*\(",
                "createCipher is deprecated, use createCipheriv",
                0.90,
            ),
            # DES
            (
                r'["\']des["\']|["\']des-',
                "DES is insecure due to small key size",
                0.95,
            ),
            # RC4
            (
                r'["\']rc4["\']',
                "RC4 is cryptographically broken",
                0.95,
            ),
            # ECB mode
            (
                r'["\']ecb["\']|-ecb',
                "ECB mode is insecure (reveals patterns)",
                0.95,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r"(crypto|CryptoJS)\..*MD5",
                "MD5 is cryptographically broken",
                0.85,
            ),
            (
                r"createHash\s*\(\s*['\"]md5['\"]",
                "MD5 hash (cryptographically broken)",
                0.85,
            ),
            (
                r"(crypto|CryptoJS)\..*SHA1",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            (
                r"createCipher\s*\(",
                "createCipher is deprecated, use createCipheriv",
                0.90,
            ),
        ],
        "java": [
            # MD5
            (
                r'MessageDigest\.getInstance\s*\(\s*["\']MD5["\']',
                "MD5 is cryptographically broken",
                0.85,
            ),
            # SHA1
            (
                r'MessageDigest\.getInstance\s*\(\s*["\']SHA-?1["\']',
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            # DES
            (
                r'Cipher\.getInstance\s*\(\s*["\']DES',
                "DES is insecure due to small key size",
                0.95,
            ),
            # ECB mode
            (
                r"/ECB/",
                "ECB mode is insecure (reveals patterns)",
                0.95,
            ),
            # RC4
            (
                r'Cipher\.getInstance\s*\(\s*["\']RC4["\']',
                "RC4 is cryptographically broken",
                0.95,
            ),
        ],
        "go": [
            # MD5
            (
                r"md5\.New\s*\(\)|md5\.Sum\s*\(",
                "MD5 is cryptographically broken",
                0.85,
            ),
            (
                r'"crypto/md5"',
                "MD5 import (cryptographically broken)",
                0.80,
            ),
            # SHA1
            (
                r"sha1\.New\s*\(\)|sha1\.Sum\s*\(",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            # DES
            (
                r"des\.NewCipher\s*\(",
                "DES is insecure due to small key size",
                0.95,
            ),
            # RC4
            (
                r"rc4\.NewCipher\s*\(",
                "RC4 is cryptographically broken",
                0.95,
            ),
        ],
        "php": [
            # MD5
            (
                r"\bmd5\s*\(",
                "MD5 is cryptographically broken (use password_hash)",
                0.85,
            ),
            # SHA1
            (
                r"\bsha1\s*\(",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            # DES
            (
                r"MCRYPT_DES|des-ecb|des-cbc",
                "DES is insecure due to small key size",
                0.95,
            ),
            # ECB mode
            (
                r"MCRYPT_MODE_ECB|-ecb",
                "ECB mode is insecure (reveals patterns)",
                0.95,
            ),
        ],
        "ruby": [
            # MD5
            (
                r"Digest::MD5|MD5\.new",
                "MD5 is cryptographically broken",
                0.85,
            ),
            # SHA1
            (
                r"Digest::SHA1|SHA1\.new",
                "SHA1 is deprecated for security purposes",
                0.80,
            ),
            # DES
            (
                r"OpenSSL::Cipher.*DES",
                "DES is insecure due to small key size",
                0.95,
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "SECURITY.INSECURE_CRYPTO"

    @property
    def name(self) -> str:
        return "Insecure Cryptography Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return list(self.PATTERNS.keys())

    @property
    def description(self) -> str:
        return (
            "Detects use of weak or deprecated cryptographic algorithms "
            "such as MD5, SHA1, DES, RC4, and insecure cipher modes like ECB."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_checksum_context(self, line: str, surrounding_lines: list[str]) -> bool:
        """Check if MD5/SHA1 is used for non-security purposes (checksums)."""
        checksum_indicators = [
            r"checksum",
            r"hash.*file",
            r"file.*hash",
            r"etag",
            r"cache[_-]?key",
            r"fingerprint",
            r"digest.*content",
        ]
        text_to_check = line + " " + " ".join(surrounding_lines)
        for pattern in checksum_indicators:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for insecure cryptographic usage.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected insecure crypto
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

            # Skip lines with nosec markers
            if "nosec" in line.lower() or "noqa" in line.lower():
                continue

            for pattern, description, base_confidence in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Get surrounding lines for context
                    start = max(0, line_num - 3)
                    end = min(len(lines), line_num + 2)
                    surrounding = lines[start:end]

                    # Lower confidence for checksum/non-security usage
                    is_checksum = self._is_checksum_context(line, surrounding)

                    if is_checksum:
                        confidence = base_confidence * 0.5
                    elif is_test_file:
                        confidence = base_confidence * 0.6
                    else:
                        confidence = base_confidence

                    # Get appropriate remediation hints
                    remediation = self._get_remediation_hints(description, language)

                    findings.append(
                        self._create_finding(
                            summary=f"Insecure crypto: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
                                        "is_checksum_context": is_checksum,
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

    def _get_remediation_hints(self, description: str, language: str) -> list[str]:
        """Get specific remediation hints based on the issue."""
        desc_lower = description.lower()

        if "md5" in desc_lower or "sha1" in desc_lower:
            return [
                "Use SHA-256 or SHA-3 for hashing: hashlib.sha256()",
                "For passwords, use bcrypt, scrypt, or Argon2",
                "If using for non-security checksums, add # nosec comment",
            ]
        elif "des" in desc_lower:
            return [
                "Use AES-256 instead of DES for encryption",
                "Ensure key length is at least 256 bits",
                "Use authenticated encryption modes (GCM, CCM)",
            ]
        elif "ecb" in desc_lower:
            return [
                "Use CBC, CTR, or GCM mode instead of ECB",
                "GCM mode provides both encryption and authentication",
                "Always use a unique IV for each encryption operation",
            ]
        elif "rc4" in desc_lower:
            return [
                "Use AES-GCM or ChaCha20-Poly1305 instead of RC4",
                "RC4 has multiple known vulnerabilities",
            ]
        elif "iv" in desc_lower or "salt" in desc_lower:
            hints_by_lang = {
                "python": "Use os.urandom() to generate random IV/salt",
                "javascript": "Use crypto.randomBytes() for random IV/salt",
                "java": "Use SecureRandom to generate IV/salt",
            }
            return [
                hints_by_lang.get(language, "Generate IV/salt using secure random"),
                "Never reuse IVs with the same key",
                "Store IV alongside ciphertext (it's not secret)",
            ]
        elif "createcipher" in desc_lower:
            return [
                "Use createCipheriv() with a random IV instead",
                "The IV should be unique for each encryption",
                "Store the IV with the ciphertext for decryption",
            ]

        return [
            "Use modern, well-vetted cryptographic algorithms",
            "Follow OWASP cryptographic guidelines",
            "Consider using a high-level crypto library",
        ]
