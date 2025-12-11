"""
Insecure deserialization detection rule.

Detects use of unsafe deserialization methods like pickle, yaml.load,
marshal, and eval that can execute arbitrary code with untrusted data.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class InsecureDeserializeRule(BaseRule):
    """Detect insecure deserialization vulnerabilities."""

    # Language-specific patterns for insecure deserialization
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # pickle.loads/load
            (
                r'pickle\.loads?\s*\(',
                "pickle can execute arbitrary code during deserialization",
                0.90,
            ),
            # cPickle
            (
                r'cPickle\.loads?\s*\(',
                "cPickle can execute arbitrary code during deserialization",
                0.90,
            ),
            # yaml.load without SafeLoader
            (
                r'yaml\.load\s*\([^)]*\)(?!.*Loader\s*=\s*yaml\.(Safe|Base)Loader)',
                "yaml.load without SafeLoader can execute arbitrary code",
                0.85,
            ),
            # yaml.unsafe_load
            (
                r'yaml\.unsafe_load\s*\(',
                "yaml.unsafe_load can execute arbitrary code",
                0.95,
            ),
            # yaml.full_load
            (
                r'yaml\.full_load\s*\(',
                "yaml.full_load can execute arbitrary code",
                0.90,
            ),
            # marshal.loads/load
            (
                r'marshal\.loads?\s*\(',
                "marshal can execute arbitrary code during deserialization",
                0.90,
            ),
            # shelve (uses pickle internally)
            (
                r'shelve\.open\s*\(',
                "shelve uses pickle internally (deserialization risk)",
                0.75,
            ),
            # dill (pickle extension)
            (
                r'dill\.loads?\s*\(',
                "dill can execute arbitrary code during deserialization",
                0.90,
            ),
            # eval on data
            (
                r'eval\s*\([^)]*\.(read|recv|decode)',
                "eval on external data (code execution risk)",
                0.95,
            ),
            # ast.literal_eval with external data
            (
                r'ast\.literal_eval\s*\([^)]*request\.',
                "ast.literal_eval with request data (safer but review)",
                0.60,
            ),
            # jsonpickle
            (
                r'jsonpickle\.decode\s*\(',
                "jsonpickle can execute arbitrary code",
                0.85,
            ),
        ],
        "javascript": [
            # node-serialize (CVE-2017-5941)
            (
                r'serialize\.unserialize\s*\(',
                "node-serialize is vulnerable to RCE",
                0.98,
            ),
            # eval on parsed JSON (when combined with prototype pollution)
            (
                r'eval\s*\([^)]*JSON\.parse',
                "eval on parsed JSON (potential code execution)",
                0.85,
            ),
            # Function constructor with data
            (
                r'new\s+Function\s*\([^)]*\.(parse|read|body)',
                "Function constructor with external data",
                0.90,
            ),
            # BSON/MongoDB deserialization issues
            (
                r'BSON\.deserialize\s*\([^)]*request',
                "BSON deserialize with request data",
                0.80,
            ),
            # vm.runIn* with external code
            (
                r'vm\.(runInContext|runInNewContext)\s*\([^)]*\.(body|query|params)',
                "vm module with request data (code execution)",
                0.95,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r'serialize\.unserialize\s*\(',
                "node-serialize is vulnerable to RCE",
                0.98,
            ),
            (
                r'eval\s*\([^)]*JSON\.parse',
                "eval on parsed JSON (potential code execution)",
                0.85,
            ),
            (
                r'new\s+Function\s*\([^)]*\.(parse|read|body)',
                "Function constructor with external data",
                0.90,
            ),
        ],
        "java": [
            # ObjectInputStream (Java native deserialization)
            (
                r'new\s+ObjectInputStream\s*\(',
                "Java ObjectInputStream can execute arbitrary code",
                0.85,
            ),
            # readObject
            (
                r'\.readObject\s*\(\s*\)',
                "readObject can trigger gadget chains",
                0.80,
            ),
            # XMLDecoder
            (
                r'new\s+XMLDecoder\s*\(',
                "XMLDecoder can execute arbitrary code",
                0.90,
            ),
            # XStream without security
            (
                r'XStream\(\)\.fromXML\s*\(',
                "XStream without allowlist is vulnerable",
                0.85,
            ),
            # Jackson default typing
            (
                r'enableDefaultTyping\s*\(\s*\)',
                "Jackson enableDefaultTyping is vulnerable",
                0.90,
            ),
            # Kryo without registration
            (
                r'kryo\.setRegistrationRequired\s*\(\s*false\s*\)',
                "Kryo without registration is vulnerable",
                0.85,
            ),
        ],
        "php": [
            # unserialize
            (
                r'\bunserialize\s*\([^)]*\$_(GET|POST|REQUEST|COOKIE)',
                "unserialize with user input (object injection)",
                0.95,
            ),
            # Generic unserialize (warning)
            (
                r'\bunserialize\s*\(',
                "unserialize can lead to object injection",
                0.70,
            ),
            # __wakeup exploitation possible
            (
                r'function\s+__wakeup\s*\(',
                "__wakeup magic method (review for deserialization attacks)",
                0.50,
            ),
        ],
        "ruby": [
            # Marshal.load
            (
                r'Marshal\.load\s*\(',
                "Marshal.load can execute arbitrary code",
                0.90,
            ),
            # YAML.load (pre Ruby 2.5)
            (
                r'YAML\.load\s*\([^)]*(?!permitted)',
                "YAML.load without permitted_classes is unsafe",
                0.85,
            ),
            # JSON.parse with create_additions
            (
                r'JSON\.parse\s*\([^)]*create_additions\s*[=:]\s*true',
                "JSON.parse with create_additions can execute code",
                0.90,
            ),
        ],
        "go": [
            # gob.Decoder with external data
            (
                r'gob\.NewDecoder\s*\([^)]*r\.Body',
                "gob.Decoder with request body (type confusion risk)",
                0.75,
            ),
            # yaml.Unmarshal without strict mode
            (
                r'yaml\.Unmarshal\s*\([^)]*,\s*&?interface\{\}',
                "yaml.Unmarshal to interface{} (type confusion risk)",
                0.70,
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "SECURITY.INSECURE_DESERIALIZE"

    @property
    def name(self) -> str:
        return "Insecure Deserialization Detection"

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
            "Detects use of unsafe deserialization methods like pickle, yaml.load, "
            "marshal, and eval that can execute arbitrary code when processing untrusted data."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _has_safe_loader(self, line: str, surrounding_lines: list[str]) -> bool:
        """Check if safe loading options are used."""
        safe_patterns = [
            r'SafeLoader',
            r'BaseLoader',
            r'safe_load',
            r'permitted_classes',
            r'allowlist',
            r'whitelist',
            r'setRegistrationRequired.*true',
            r'validateTypes',
            r'TypeValidator',
        ]
        text_to_check = line + " " + " ".join(surrounding_lines)
        for pattern in safe_patterns:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for insecure deserialization vulnerabilities.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected insecure deserialization
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
                    start = max(0, line_num - 5)
                    end = min(len(lines), line_num + 3)
                    surrounding = lines[start:end]

                    # Lower confidence if safe loader is present
                    if self._has_safe_loader(line, surrounding):
                        continue  # Skip - using safe method

                    if is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    findings.append(
                        self._create_finding(
                            summary=f"Insecure deserialization: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
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

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        hints = {
            "python": [
                "Use json instead of pickle when possible (JSON is safe)",
                "For YAML, always use yaml.safe_load() instead of yaml.load()",
                "If pickle is necessary, only deserialize trusted data from secure sources",
            ],
            "javascript": [
                "Use JSON.parse() for data serialization (safe by default)",
                "Never use node-serialize or eval() with untrusted data",
                "Implement input validation before any deserialization",
            ],
            "typescript": [
                "Use JSON.parse() with proper TypeScript type validation",
                "Implement runtime type checking with libraries like zod or io-ts",
                "Never use eval() or Function constructor with external data",
            ],
            "java": [
                "Use ObjectInputFilter to validate deserialized classes",
                "Prefer JSON serialization with Jackson (with polymorphism disabled)",
                "Use allowlists for permitted classes during deserialization",
            ],
            "php": [
                "Use json_decode() instead of unserialize() for untrusted data",
                "If unserialize() is needed, use allowed_classes option (PHP 7+)",
                "Never unserialize user input directly",
            ],
            "ruby": [
                "Use JSON.parse() instead of Marshal.load for untrusted data",
                "For YAML, use YAML.safe_load() with permitted_classes",
                "Disable create_additions in JSON.parse()",
            ],
            "go": [
                "Use JSON encoding for external data exchange",
                "Avoid deserializing to interface{} without validation",
                "Implement type-specific unmarshaling",
            ],
        }
        return hints.get(language, [
            "Prefer safe formats like JSON over native serialization",
            "Implement strict input validation before deserialization",
            "Use allowlists for permitted types/classes",
        ])
