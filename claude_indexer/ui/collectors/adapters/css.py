"""CSS adapter for extracting styles from CSS/SCSS/LESS files.

This module provides the CSSAdapter class that extracts style rules
and declarations from CSS stylesheets.
"""

import re
from pathlib import Path

from ...models import SymbolKind, Visibility
from ..base import BaseSourceAdapter, ExtractedComponent, ExtractedStyle


class CSSAdapter(BaseSourceAdapter):
    """Adapter for CSS/SCSS/SASS/LESS files.

    Extracts CSS rules, selectors, and declarations from stylesheet files.
    Uses regex-based parsing for broad compatibility.
    """

    SUPPORTED_EXTENSIONS = [".css", ".scss", ".sass", ".less"]

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return self.SUPPORTED_EXTENSIONS

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract_components(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedComponent]:
        """CSS files don't define components.

        Args:
            file_path: Path to the CSS file.
            content: Optional file content.

        Returns:
            Empty list (CSS has no components).
        """
        return []

    def extract_style_usage(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedStyle]:
        """Extract all CSS rules from the file.

        Args:
            file_path: Path to the CSS file.
            content: Optional file content.

        Returns:
            List of ExtractedStyle objects.
        """
        content = self._read_file(file_path, content)
        styles = []

        # Remove comments for easier parsing
        content = self._remove_comments(content)

        # Find all rule sets
        for match in self._find_rule_sets(content):
            selector = match["selector"]
            declarations = match["declarations"]
            start_line = match["start_line"]
            end_line = match["end_line"]

            # Parse declarations
            decl_dict = self._parse_declarations(declarations)

            # Extract class names from selector
            class_names = self._extract_class_names(selector)

            styles.append(
                ExtractedStyle(
                    source_ref=self._create_symbol_ref(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        name=selector,
                        kind=SymbolKind.CSS,
                        visibility=Visibility.PUBLIC,
                    ),
                    selector=selector,
                    declarations=decl_dict,
                    is_inline=False,
                    class_names=class_names,
                )
            )

        return styles

    def _remove_comments(self, content: str) -> str:
        """Remove CSS comments from content.

        Args:
            content: CSS content with comments.

        Returns:
            Content with comments removed.
        """
        # Remove /* ... */ comments
        content = re.sub(r"/\*[\s\S]*?\*/", "", content)
        # Remove // comments (SCSS/LESS)
        content = re.sub(r"//[^\n]*", "", content)
        return content

    def _find_rule_sets(self, content: str) -> list[dict]:
        """Find all CSS rule sets in content.

        Args:
            content: CSS content (comments removed).

        Returns:
            List of dicts with selector, declarations, and line info.
        """
        rule_sets = []
        lines = content.split("\n")
        len(lines)

        # Simple regex to find rule sets: selector { declarations }
        # This handles most cases but may miss complex nested SCSS
        pattern = r"([^{}]+)\{([^{}]*)\}"

        for match in re.finditer(pattern, content):
            selector = match.group(1).strip()
            declarations = match.group(2).strip()

            # Skip empty selectors or at-rules
            if not selector or selector.startswith("@"):
                continue

            # Calculate line numbers
            start_pos = match.start()
            end_pos = match.end()
            start_line = content[:start_pos].count("\n") + 1
            end_line = content[:end_pos].count("\n") + 1

            rule_sets.append(
                {
                    "selector": selector,
                    "declarations": declarations,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )

        return rule_sets

    def _parse_declarations(self, declarations: str) -> dict[str, str]:
        """Parse CSS declarations into a dictionary.

        Args:
            declarations: CSS declaration block content.

        Returns:
            Dictionary of property -> value pairs.
        """
        result = {}

        # Split by semicolons and parse each declaration
        for decl in declarations.split(";"):
            decl = decl.strip()
            if not decl:
                continue

            # Split on first colon only (values may contain colons)
            parts = decl.split(":", 1)
            if len(parts) == 2:
                prop = parts[0].strip()
                value = parts[1].strip()
                if prop and value:
                    result[prop] = value

        return result

    def _extract_class_names(self, selector: str) -> list[str]:
        """Extract class names from a CSS selector.

        Args:
            selector: CSS selector string.

        Returns:
            List of class names found in the selector.
        """
        # Match .classname patterns
        matches = re.findall(r"\.([a-zA-Z_-][a-zA-Z0-9_-]*)", selector)
        return list(set(matches))  # Deduplicate

    def extract_css_variables(
        self, file_path: Path, content: str | None = None
    ) -> dict[str, str]:
        """Extract CSS custom properties (variables) from file.

        Args:
            file_path: Path to the CSS file.
            content: Optional file content.

        Returns:
            Dictionary of variable name -> value pairs.
        """
        content = self._read_file(file_path, content)
        content = self._remove_comments(content)

        variables = {}

        # Match --variable-name: value;
        pattern = r"(--[a-zA-Z0-9_-]+)\s*:\s*([^;]+);"
        for match in re.finditer(pattern, content):
            name = match.group(1)
            value = match.group(2).strip()
            variables[name] = value

        return variables
