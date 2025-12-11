"""
Path traversal detection rule.

Detects potential path traversal vulnerabilities from user-controlled
file paths that could allow access to files outside intended directories.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class PathTraversalRule(BaseRule):
    """Detect path traversal vulnerabilities."""

    # Language-specific patterns for path traversal
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # open() with user input indicators
            (
                r'open\s*\([^)]*[\+\{%]',
                "open() with dynamic path",
                0.80,
            ),
            # open with request data
            (
                r'open\s*\([^)]*request\.',
                "open() with request data",
                0.90,
            ),
            # os.path.join with request
            (
                r'os\.path\.join\s*\([^)]*request\.',
                "os.path.join with request data",
                0.85,
            ),
            # Path() with user input
            (
                r'Path\s*\([^)]*request\.',
                "Path() with request data",
                0.85,
            ),
            # send_file with user input
            (
                r'send_file\s*\([^)]*request\.',
                "send_file() with request data",
                0.90,
            ),
            # send_from_directory without validation
            (
                r'send_from_directory\s*\([^)]*[\+\{]',
                "send_from_directory with dynamic input",
                0.80,
            ),
            # shutil operations with user input
            (
                r'shutil\.(copy|move|rmtree)\s*\([^)]*request\.',
                "shutil operation with request data",
                0.90,
            ),
            # os.remove/unlink with user input
            (
                r'os\.(remove|unlink)\s*\([^)]*[\+\{%]',
                "file deletion with dynamic path",
                0.85,
            ),
            # Literal path traversal
            (
                r'["\'][^"\']*\.\./\.\.',
                "Path traversal sequence in string literal",
                0.95,
            ),
        ],
        "javascript": [
            # fs operations with dynamic input
            (
                r'fs\.(readFile|writeFile|unlink|rmdir|readdir)\s*\([^)]*[\+\`]',
                "fs operation with dynamic path",
                0.85,
            ),
            # fs operations with req
            (
                r'fs\.\w+\s*\([^)]*req\.(body|params|query)',
                "fs operation with request data",
                0.90,
            ),
            # path.join with request data
            (
                r'path\.join\s*\([^)]*req\.(body|params|query)',
                "path.join with request data",
                0.90,
            ),
            # sendFile/download with user input
            (
                r'(sendFile|download)\s*\([^)]*req\.',
                "file send with request data",
                0.90,
            ),
            # res.sendFile with dynamic path
            (
                r'res\.sendFile\s*\([^)]*[\+\`]',
                "sendFile with dynamic path",
                0.85,
            ),
            # __dirname + user input
            (
                r'__dirname\s*\+\s*req\.',
                "__dirname concatenated with user input",
                0.90,
            ),
            # Literal path traversal
            (
                r'["\'][^"\']*\.\./\.\.',
                "Path traversal sequence in string literal",
                0.95,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r'fs\.(readFile|writeFile|unlink|rmdir|readdir)\s*\([^)]*[\+\`]',
                "fs operation with dynamic path",
                0.85,
            ),
            (
                r'fs\.\w+\s*\([^)]*req\.(body|params|query)',
                "fs operation with request data",
                0.90,
            ),
            (
                r'path\.join\s*\([^)]*req\.(body|params|query)',
                "path.join with request data",
                0.90,
            ),
            (
                r'(sendFile|download)\s*\([^)]*req\.',
                "file send with request data",
                0.90,
            ),
        ],
        "java": [
            # File constructor with user input
            (
                r'new\s+File\s*\([^)]*\+',
                "File constructor with dynamic path",
                0.80,
            ),
            # Paths.get with user input
            (
                r'Paths\.get\s*\([^)]*\+',
                "Paths.get with dynamic input",
                0.80,
            ),
            # FileInputStream with user input
            (
                r'new\s+FileInputStream\s*\([^)]*\+',
                "FileInputStream with dynamic path",
                0.85,
            ),
            # Request parameter in path
            (
                r'(getParameter|getAttribute)\s*\([^)]*\).*File',
                "Request parameter used in file path",
                0.85,
            ),
        ],
        "php": [
            # include/require with user input
            (
                r'(include|require)(_once)?\s*\([^)]*\$_(GET|POST|REQUEST)',
                "include with user input (LFI/RFI)",
                0.95,
            ),
            # file_get_contents with user input
            (
                r'file_get_contents\s*\([^)]*\$_(GET|POST|REQUEST)',
                "file_get_contents with user input",
                0.90,
            ),
            # fopen with user input
            (
                r'fopen\s*\([^)]*\$_(GET|POST|REQUEST)',
                "fopen with user input",
                0.90,
            ),
            # unlink with user input
            (
                r'unlink\s*\([^)]*\$',
                "unlink with variable path",
                0.80,
            ),
            # readfile with user input
            (
                r'readfile\s*\([^)]*\$_(GET|POST|REQUEST)',
                "readfile with user input",
                0.90,
            ),
        ],
        "go": [
            # os.Open with user input
            (
                r'os\.(Open|Create|Remove)\s*\([^)]*\+',
                "os file operation with dynamic path",
                0.85,
            ),
            # ioutil.ReadFile with user input
            (
                r'ioutil\.(ReadFile|WriteFile)\s*\([^)]*\+',
                "ioutil with dynamic path",
                0.85,
            ),
            # filepath.Join with user input
            (
                r'filepath\.Join\s*\([^)]*r\.FormValue',
                "filepath.Join with form data",
                0.90,
            ),
            # http.ServeFile with user input
            (
                r'http\.ServeFile\s*\([^)]*r\.URL',
                "ServeFile with URL path",
                0.85,
            ),
        ],
        "ruby": [
            # File.open with user input
            (
                r'File\.(open|read|write)\s*\([^)]*params\[',
                "File operation with params",
                0.90,
            ),
            # send_file with user input
            (
                r'send_file\s*\([^)]*params\[',
                "send_file with params",
                0.90,
            ),
            # IO operations with interpolation
            (
                r'(File|IO)\.\w+\s*\([^)]*#\{',
                "File/IO with string interpolation",
                0.80,
            ),
            # Pathname with user input
            (
                r'Pathname\.(new|glob)\s*\([^)]*params\[',
                "Pathname with params",
                0.85,
            ),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "SECURITY.PATH_TRAVERSAL"

    @property
    def name(self) -> str:
        return "Path Traversal Detection"

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
            "Detects potential path traversal vulnerabilities from user-controlled "
            "file paths that could allow unauthorized file access."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _has_path_validation(self, surrounding_lines: list[str]) -> bool:
        """Check if path validation is present nearby."""
        validation_patterns = [
            r'realpath',
            r'abspath',
            r'normpath',
            r'canonicalize',
            r'startswith.*base',
            r'startswith.*root',
            r'startswith.*allowed',
            r'path\.resolve',
            r'\.startsWith\s*\(',
            r'allowlist|whitelist',
            r'\.includes\s*\(',
            r'indexOf.*-1',
            r'sanitize.*path',
            r'secure.*filename',
            r'\.\..*reject',
            r'contains\s*\(\s*["\']\.\.["\']\s*\)',
        ]
        text = " ".join(surrounding_lines)
        for pattern in validation_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for path traversal vulnerabilities.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected path traversal risks
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
                    start = max(0, line_num - 7)
                    end = min(len(lines), line_num + 3)
                    surrounding = lines[start:end]

                    # Lower confidence if validation is present
                    if self._has_path_validation(surrounding):
                        confidence = base_confidence * 0.5
                    elif is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    # Skip low confidence findings
                    if confidence < 0.50:
                        continue

                    findings.append(
                        self._create_finding(
                            summary=f"Potential path traversal: {description}",
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
                "Use os.path.realpath() and verify path is within allowed directory",
                "Example: if not realpath(path).startswith(realpath(BASE_DIR)): raise",
                "Use werkzeug.utils.secure_filename() for user-provided filenames",
            ],
            "javascript": [
                "Use path.resolve() and verify path starts with base directory",
                "Reject paths containing '..' or use allowlist of valid filenames",
                "Example: if (!resolved.startsWith(baseDir)) throw new Error()",
            ],
            "typescript": [
                "Use path.resolve() and validate against allowed base directory",
                "Leverage TypeScript types to distinguish safe vs. unsafe paths",
                "Implement path validation middleware for file operations",
            ],
            "java": [
                "Use File.getCanonicalPath() and verify within allowed directory",
                "Implement allowlist validation for filenames",
                "Use Java NIO with careful path validation",
            ],
            "php": [
                "Use realpath() and verify path prefix matches allowed directory",
                "Use basename() to strip directory components from user input",
                "Implement allowlist of valid file paths",
            ],
            "go": [
                "Use filepath.Clean() and verify path is within base directory",
                "Check that filepath.Rel() doesn't return paths starting with ..",
                "Implement strict validation before file operations",
            ],
            "ruby": [
                "Use File.expand_path() and verify within allowed directory",
                "Use File.basename() for user-provided filenames",
                "Implement Rails' send_file with proper path validation",
            ],
        }
        return hints.get(language, [
            "Canonicalize paths and verify they're within allowed directories",
            "Use allowlists for valid filenames/paths when possible",
            "Reject any path containing '..' or absolute path prefixes",
        ])
