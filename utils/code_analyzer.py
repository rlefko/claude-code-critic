#!/usr/bin/env python3
"""
CodeAnalyzer - Centralized code analysis with compiled patterns for Memory Guard.
Fixes code duplication, performance issues, and logic gaps.
"""

import re
from re import Pattern


class CodeAnalyzer:
    """Centralized code analysis with optimized compiled patterns."""

    def __init__(self):
        """Initialize with pre-compiled regex patterns for performance."""

        # Import patterns (Python and JavaScript)
        self.import_patterns: list[Pattern] = [
            re.compile(
                r"^\s*(from\s+[\w.]+\s+)?import\s+"
            ),  # Python: import, from X import
            re.compile(
                r"^\s*import\s+[\w{},\s'\".*]+\s+from\s+['\"]"
            ),  # JS: import X from 'module'
            re.compile(r"^\s*import\s+['\"][\w./]+['\"]"),  # JS: import 'module'
            re.compile(
                r"^\s*const\s+\w+\s*=\s*require\s*\("
            ),  # JS: const X = require()
        ]

        # Type hint patterns (Python type annotations)
        self.type_hint_patterns: list[Pattern] = [
            re.compile(r"^\s*\w+\s*:\s*\w+\s*$"),  # var: Type
            re.compile(r"^\s*\w+\s*:\s*\w+\s*="),  # var: Type =
            re.compile(r"^\s*\w+\s*=\s*\w+\s*$"),  # TypeAlias = Type
            re.compile(r"^\s*[A-Z]\w*\s*=\s*TypeVar\s*\("),  # T = TypeVar(...)
            re.compile(r"^\s*[A-Z]\w*\s*:\s*TypeAlias\s*="),  # MyType: TypeAlias =
        ]

        # Decorator patterns (Python decorators - trivial alone)
        self.decorator_patterns: list[Pattern] = [
            re.compile(r"^\s*@property\s*$"),
            re.compile(r"^\s*@staticmethod\s*$"),
            re.compile(r"^\s*@classmethod\s*$"),
            re.compile(r"^\s*@abstractmethod\s*$"),
            re.compile(r"^\s*@dataclass\s*$"),
            re.compile(r"^\s*@dataclass\(.*\)\s*$"),
            re.compile(r"^\s*@override\s*$"),
            re.compile(r"^\s*@deprecated\s*$"),
            re.compile(r"^\s*@\w+\s*$"),  # Generic single decorator
            re.compile(r"^\s*@\w+\(.*\)\s*$"),  # Decorator with args
        ]

        # TypeScript interface/type patterns (trivial type definitions)
        self.typescript_type_patterns: list[Pattern] = [
            re.compile(r"^\s*interface\s+\w+\s*\{?\s*$"),  # interface Name {
            re.compile(r"^\s*type\s+\w+\s*="),  # type Name =
            re.compile(r"^\s*export\s+interface\s+\w+"),  # export interface
            re.compile(r"^\s*export\s+type\s+\w+"),  # export type
            re.compile(r"^\s*\}\s*$"),  # closing brace
            re.compile(r"^\s*\w+\s*:\s*\w+[\[\]<>,\s\w]*;?\s*$"),  # property: Type;
            re.compile(r"^\s*\w+\?\s*:\s*\w+"),  # optional?: Type
            re.compile(r"^\s*readonly\s+\w+\s*:"),  # readonly prop:
        ]

        # Docstring patterns (Python/JS documentation)
        self.docstring_patterns: list[Pattern] = [
            re.compile(r'^\s*"""'),  # Python docstring start/end
            re.compile(r"^\s*'''"),  # Python docstring alt
            re.compile(r"^\s*/\*\*"),  # JSDoc start
            re.compile(r"^\s*\*"),  # JSDoc middle line
            re.compile(r"^\s*\*/"),  # JSDoc end
            re.compile(r"^\s*//"),  # Single-line comment
            re.compile(r"^\s*#"),  # Python comment
        ]

        # Assignment patterns (Python and JavaScript)
        self.assignment_patterns: list[Pattern] = [
            re.compile(r"^[a-z_][a-zA-Z0-9_]*\s*=\s*.+$"),  # Python: variable = value
            re.compile(
                r"^\s*(const|let|var)\s+[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*.+$"
            ),  # JS: const/let/var variable = value
        ]

        # Configuration constant patterns (Python and JavaScript)
        self.config_patterns: list[Pattern] = [
            re.compile(r"^[A-Z_][A-Z0-9_]*\s*=\s*.+$"),  # Python: CONSTANT = value
            re.compile(
                r"^\s*(const|let|var)\s+[A-Z_][A-Z0-9_]*\s*=\s*.+$"
            ),  # JS: const CONSTANT = value
        ]

        # Definition patterns (Python and JavaScript/TypeScript)
        self.definition_patterns: list[Pattern] = [
            re.compile(
                r"^\s*(def|class|async\s+def)\s+", re.MULTILINE
            ),  # Python: def, class, async def
            re.compile(r"^\s*function\s+\w+\s*\(", re.MULTILINE),  # JS: function name()
            re.compile(
                r"^\s*async\s+function\s+\w+\s*\(", re.MULTILINE
            ),  # JS: async function name()
            re.compile(
                r"^\s*const\s+\w+\s*=\s*(\(.*\)\s*=>|\(\)\s*=>|async\s*\(.*\)\s*=>)",
                re.MULTILINE,
            ),  # JS: const name = () =>
            re.compile(
                r"^\s*const\s+\w+\s*=\s*function", re.MULTILINE
            ),  # JS: const name = function
            re.compile(r"^\s*class\s+\w+", re.MULTILINE),  # JS/Python: class Name
            # TypeScript method signatures with access modifiers
            re.compile(
                r"^\s*(private|public|protected)\s+\w+\s*\(", re.MULTILINE
            ),  # TS: private/public/protected method()
            re.compile(
                r"^\s*(private|public|protected)\s+async\s+\w+\s*\(", re.MULTILINE
            ),  # TS: private/public/protected async method()
            re.compile(
                r"^\s*(private|public|protected)\s+static\s+\w+\s*\(", re.MULTILINE
            ),  # TS: private/public/protected static method()
            re.compile(
                r"^\s*(private|public|protected)\s+static\s+async\s+\w+\s*\(",
                re.MULTILINE,
            ),  # TS: private/public/protected static async method()
            re.compile(
                r"^\s*\w+\s*\([^)]*\)\s*:\s*\w+.*\s*\{", re.MULTILINE
            ),  # TS: method(params): ReturnType {
        ]

        # Code block extraction pattern - supports multiple formats
        self.code_block_pattern: Pattern = re.compile(
            r"```(?:\w+)?\n(.*?)\n```", re.DOTALL
        )

    def extract_code_content(self, code_info: str) -> str:
        """
        Extract actual code content from formatted code_info.

        Args:
            code_info: Formatted code info string (may contain ``` blocks)

        Returns:
            Clean code content string
        """
        if not code_info.strip():
            return ""

        # Extract from code blocks if present
        if "```" in code_info:
            code_blocks = self.code_block_pattern.findall(code_info)
            return "\n".join(code_blocks)
        else:
            return code_info

    def is_import_only(self, lines: list[str]) -> bool:
        """
        Check if all non-empty lines are import statements.

        Args:
            lines: List of code lines

        Returns:
            True if all lines are imports, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.import_patterns)
            for line in non_empty_lines
        )

    def is_simple_assignment(self, lines: list[str]) -> bool:
        """
        Check if lines contain only simple variable assignments.

        Args:
            lines: List of code lines

        Returns:
            True if simple assignments only (max 2 lines), False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines or len(non_empty_lines) > 2:
            return False

        return all(
            any(pattern.match(line) for pattern in self.assignment_patterns)
            for line in non_empty_lines
        )

    def is_config_constant(self, lines: list[str]) -> bool:
        """
        Check if lines contain only configuration constants.

        Args:
            lines: List of code lines

        Returns:
            True if all lines are config constants, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.config_patterns)
            for line in non_empty_lines
        )

    def is_type_hint_only(self, lines: list[str]) -> bool:
        """
        Check if lines contain only type hints/annotations.

        Args:
            lines: List of code lines

        Returns:
            True if all lines are type hints, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.type_hint_patterns)
            for line in non_empty_lines
        )

    def is_decorator_only(self, lines: list[str]) -> bool:
        """
        Check if lines contain only decorators (without function body).

        Args:
            lines: List of code lines

        Returns:
            True if all lines are decorators, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.decorator_patterns)
            for line in non_empty_lines
        )

    def is_typescript_type_only(self, lines: list[str]) -> bool:
        """
        Check if lines contain only TypeScript interface/type definitions.

        Args:
            lines: List of code lines

        Returns:
            True if all lines are TS type definitions, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.typescript_type_patterns)
            for line in non_empty_lines
        )

    def is_docstring_only(self, lines: list[str]) -> bool:
        """
        Check if lines contain only docstrings/comments.

        Args:
            lines: List of code lines

        Returns:
            True if all lines are documentation, False otherwise
        """
        non_empty_lines = [line.strip() for line in lines if line.strip()]
        if not non_empty_lines:
            return False

        return all(
            any(pattern.match(line) for pattern in self.docstring_patterns)
            for line in non_empty_lines
        )

    def has_definitions(self, content: str) -> bool:
        """
        Check if content contains function or class definitions.

        Args:
            content: Code content string

        Returns:
            True if definitions found, False otherwise
        """
        if not content.strip():
            return False

        return any(pattern.search(content) for pattern in self.definition_patterns)

    def analyze_code(self, code_info: str) -> dict:
        """
        Comprehensive code analysis in a single pass.

        Args:
            code_info: Formatted code info string

        Returns:
            Analysis results dictionary
        """
        content = self.extract_code_content(code_info)
        if not content.strip():
            return {
                "is_empty": True,
                "is_trivial": True,
                "reason": "Empty code content",
                "has_definitions": False,
            }

        lines = content.split("\n")

        # Check import-only
        if self.is_import_only(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Import statements only - no duplication risk",
                "has_definitions": False,
            }

        # Check docstring/comment-only changes
        if self.is_docstring_only(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Documentation/comments only - no duplication risk",
                "has_definitions": False,
            }

        # Check decorator-only changes (decorators without function body)
        if self.is_decorator_only(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Decorators only - no duplication risk",
                "has_definitions": False,
            }

        # Check type hint-only changes
        if self.is_type_hint_only(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Type annotations only - no duplication risk",
                "has_definitions": False,
            }

        # Check TypeScript interface/type-only changes
        if self.is_typescript_type_only(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "TypeScript type definitions - no duplication risk",
                "has_definitions": False,
            }

        # Check for definitions FIRST (before simple assignments)
        has_defs = self.has_definitions(content)
        if has_defs:
            return {
                "is_empty": False,
                "is_trivial": False,
                "reason": "",
                "has_definitions": True,
            }

        # Check config constants
        if self.is_config_constant(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Configuration constants - no duplication risk",
                "has_definitions": False,
            }

        # Check simple assignments (after checking for definitions)
        if self.is_simple_assignment(lines):
            return {
                "is_empty": False,
                "is_trivial": True,
                "reason": "Simple variable assignments - no duplication risk",
                "has_definitions": False,
            }

        return {
            "is_empty": False,
            "is_trivial": False,
            "reason": "",
            "has_definitions": False,
        }
