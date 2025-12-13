"""
Missing docstring detection rule.

Detects public functions and classes that don't have
documentation, making the codebase harder to understand.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class MissingDocstringRule(BaseRule):
    """Detect missing documentation on public functions and classes.

    Identifies public functions, methods, and classes that don't have
    proper documentation (docstrings in Python, JSDoc in JavaScript/TypeScript).
    """

    # Patterns to detect function/class definitions
    # Format: (pattern, type_name, capture_group_index_for_name)
    DEFINITION_PATTERNS = {
        "python": [
            # Regular function
            (r"^\s*def\s+(\w+)\s*\(", "function", 1),
            # Async function
            (r"^\s*async\s+def\s+(\w+)\s*\(", "async function", 1),
            # Class definition
            (r"^\s*class\s+(\w+)\s*[\(:]", "class", 1),
        ],
        "javascript": [
            # Function declaration
            (r"^\s*function\s+(\w+)\s*\(", "function", 1),
            # Async function declaration
            (r"^\s*async\s+function\s+(\w+)\s*\(", "async function", 1),
            # Exported function
            (r"^\s*export\s+function\s+(\w+)\s*\(", "exported function", 1),
            # Exported async function
            (
                r"^\s*export\s+async\s+function\s+(\w+)\s*\(",
                "exported async function",
                1,
            ),
            # Arrow function assignment
            (
                r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
                "arrow function",
                1,
            ),
            # Arrow function with parameters
            (
                r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\w+\s*=>",
                "arrow function",
                1,
            ),
            # Class definition
            (r"^\s*(?:export\s+)?class\s+(\w+)", "class", 1),
        ],
        "typescript": [
            # Function declaration
            (r"^\s*function\s+(\w+)\s*[<\(]", "function", 1),
            # Async function
            (r"^\s*async\s+function\s+(\w+)\s*[<\(]", "async function", 1),
            # Exported function
            (r"^\s*export\s+function\s+(\w+)\s*[<\(]", "exported function", 1),
            # Exported async function
            (
                r"^\s*export\s+async\s+function\s+(\w+)\s*[<\(]",
                "exported async function",
                1,
            ),
            # Arrow function assignment with type
            (
                r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*[^=]+)?\s*=\s*(?:async\s+)?\(",
                "arrow function",
                1,
            ),
            # Class definition
            (r"^\s*(?:export\s+)?class\s+(\w+)", "class", 1),
            # Interface definition
            (r"^\s*(?:export\s+)?interface\s+(\w+)", "interface", 1),
            # Type definition
            (r"^\s*(?:export\s+)?type\s+(\w+)\s*[<=]", "type", 1),
        ],
    }

    # Patterns for names that don't need documentation
    EXCLUDED_NAMES = {
        "python": [
            r"^_",  # Private functions/methods
            r"^__(?!init__$)",  # Magic methods except __init__
            r"^test_",  # Test functions
            r"^setup$",
            r"^teardown$",
            r"^setUp$",
            r"^tearDown$",
        ],
        "javascript": [
            r"^_",  # Private by convention
            r"^test",  # Test functions
            r"^it$",
            r"^describe$",
            r"^before",
            r"^after",
        ],
        "typescript": [
            r"^_",  # Private by convention
            r"^#",  # Private fields
            r"^test",
            r"^it$",
            r"^describe$",
            r"^before",
            r"^after",
        ],
    }

    @property
    def rule_id(self) -> str:
        return "DOCUMENTATION.MISSING_DOCSTRING"

    @property
    def name(self) -> str:
        return "Missing Docstring Detection"

    @property
    def category(self) -> str:
        return "documentation"

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
            "Detects public functions and classes without documentation. "
            "Good documentation helps other developers understand the code "
            "and reduces onboarding time."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_test_file(self, file_path: str) -> bool:
        """Check if the file is a test file."""
        path_lower = file_path.lower()
        return any(
            p in path_lower
            for p in ["test_", "_test.", ".test.", ".spec.", "/tests/", "/test/"]
        )

    def _is_excluded_name(self, name: str, language: str) -> bool:
        """Check if the name is excluded from documentation requirements."""
        patterns = self.EXCLUDED_NAMES.get(language, [])
        return any(re.match(pattern, name) for pattern in patterns)

    def _has_python_docstring(self, lines: list[str], def_line: int) -> bool:
        """Check if Python function/class has a docstring."""
        # Look for triple quotes on the line after the definition
        # Handle multi-line function signatures
        brace_count = 0
        colon_found = False

        for i in range(def_line, min(def_line + 10, len(lines))):
            line = lines[i]
            for char in line:
                if char == "(":
                    brace_count += 1
                elif char == ")":
                    brace_count -= 1
                elif char == ":" and brace_count == 0:
                    colon_found = True
                    break

            if colon_found:
                # Check the next non-empty line for docstring
                for j in range(i + 1, min(i + 5, len(lines))):
                    next_line = lines[j].strip()
                    if not next_line:
                        continue
                    # Check for docstring markers
                    if next_line.startswith('"""') or next_line.startswith("'''"):
                        return True
                    if next_line.startswith('r"""') or next_line.startswith("r'''"):
                        return True
                    if next_line.startswith('f"""') or next_line.startswith("f'''"):
                        return True
                    # First non-empty line is not a docstring
                    return False
                return False

        return False

    def _has_jsdoc_comment(self, lines: list[str], def_line: int) -> bool:
        """Check if JS/TS function/class has JSDoc comment above it."""
        # Look for /** ... */ in the lines above the definition
        for i in range(def_line - 1, max(-1, def_line - 10), -1):
            line = lines[i].strip()
            if not line:
                continue
            # Found JSDoc end
            if line.endswith("*/"):
                # Scan up to find JSDoc start
                return any("/**" in lines[j] for j in range(i, max(-1, i - 30), -1))
            # Found non-comment code
            if not line.startswith("*") and not line.startswith("//"):
                return False

        return False

    def _is_short_function(
        self, lines: list[str], def_line: int, language: str
    ) -> bool:
        """Check if function is very short (likely trivial)."""
        # Count lines in function body (simplified heuristic)
        if language == "python":
            # Count indented lines after definition
            if def_line >= len(lines):
                return True

            base_indent = len(lines[def_line]) - len(lines[def_line].lstrip())
            body_lines = 0

            for i in range(def_line + 1, min(def_line + 20, len(lines))):
                line = lines[i]
                if not line.strip():
                    continue
                line_indent = len(line) - len(line.lstrip())
                if line_indent <= base_indent:
                    break
                body_lines += 1

            return body_lines <= 2
        else:
            # For JS/TS, count lines until closing brace
            brace_count = 0
            body_lines = 0
            started = False

            for i in range(def_line, min(def_line + 20, len(lines))):
                line = lines[i]
                for char in line:
                    if char == "{":
                        brace_count += 1
                        started = True
                    elif char == "}":
                        brace_count -= 1
                        if started and brace_count == 0:
                            return body_lines <= 2

                if started:
                    body_lines += 1

            return body_lines <= 2

    def _get_remediation_hint(self, language: str, def_type: str) -> list[str]:
        """Get language-specific remediation hints."""
        if language == "python":
            if def_type == "class":
                return [
                    'Add a class docstring: """Brief description of the class."""',
                    "Document class attributes and key methods",
                    "Use Google, NumPy, or Sphinx docstring style",
                ]
            return [
                'Add a docstring: """Brief description of the function."""',
                "Document parameters with :param or Args:",
                "Document return value with :returns or Returns:",
            ]
        elif language in ("javascript", "typescript"):
            if def_type in ("class", "interface", "type"):
                return [
                    "Add JSDoc: /** @class Brief description */",
                    "Document class members and methods",
                ]
            return [
                "Add JSDoc: /** Brief description @param {type} name */",
                "Document all parameters with @param",
                "Document return value with @returns",
            ]
        return ["Add documentation describing the purpose and usage"]

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for missing docstrings/JSDoc comments.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for missing documentation
        """
        findings = []
        language = context.language
        lines = context.lines
        file_path = str(context.file_path)

        # Skip test files entirely
        if self._is_test_file(file_path):
            return findings

        # Get patterns for this language
        patterns = self.DEFINITION_PATTERNS.get(language, [])
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

            for pattern, def_type, name_group in patterns:
                match = re.search(pattern, line)
                if match:
                    name = match.group(name_group)

                    # Skip excluded names
                    if self._is_excluded_name(name, language):
                        continue

                    # Check for documentation
                    has_docs = False
                    if language == "python":
                        has_docs = self._has_python_docstring(lines, line_num)
                    else:
                        has_docs = self._has_jsdoc_comment(lines, line_num)

                    if has_docs:
                        continue

                    # Skip short/trivial functions
                    if def_type in ("function", "async function", "arrow function"):
                        if self._is_short_function(lines, line_num, language):
                            continue

                    # Determine confidence based on visibility
                    confidence = 0.75
                    if "export" in line.lower():
                        confidence = 0.90  # Exported = more important
                    elif def_type in ("class", "interface"):
                        confidence = 0.85  # Classes are important

                    # Get code snippet
                    snippet = line.strip()
                    if len(snippet) > 100:
                        snippet = snippet[:100] + "..."

                    findings.append(
                        self._create_finding(
                            summary=f"Missing documentation for {def_type} '{name}'",
                            file_path=file_path,
                            line_number=line_num + 1,
                            evidence=[
                                Evidence(
                                    description=f"{def_type.capitalize()} '{name}' has no documentation",
                                    line_number=line_num + 1,
                                    code_snippet=snippet,
                                    data={
                                        "name": name,
                                        "type": def_type,
                                        "pattern": pattern,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hint(
                                language, def_type
                            ),
                            confidence=confidence,
                        )
                    )
                    break  # Only one finding per line

        return findings
