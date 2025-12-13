"""React/JSX adapter for extracting components and styles.

This module provides the ReactAdapter class that extracts React
components and their style usage from JSX/TSX files.
"""

import re
from pathlib import Path

from ...models import SymbolKind, Visibility
from ..base import BaseSourceAdapter, ExtractedComponent, ExtractedStyle


class ReactAdapter(BaseSourceAdapter):
    """Adapter for React/JSX/TSX files.

    Extracts React component definitions and their style usage,
    including className attributes and inline styles.
    """

    SUPPORTED_EXTENSIONS = [".jsx", ".tsx"]

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
        """Extract React component definitions.

        Args:
            file_path: Path to the JSX/TSX file.
            content: Optional file content.

        Returns:
            List of ExtractedComponent objects.
        """
        content = self._read_file(file_path, content)
        components = []

        # Find function components: function Name() or const Name = () =>
        # Also find arrow function components: const Name = () =>
        # And class components: class Name extends Component

        # Function components: export function ComponentName
        for match in re.finditer(
            r"(?:export\s+)?(?:default\s+)?function\s+([A-Z][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*(?::\s*[^{]+)?\s*\{",
            content,
        ):
            name = match.group(1)
            props = match.group(2)
            start_line = content[: match.start()].count("\n") + 1

            # Find the component's end (matching brace)
            body_start = match.end()
            end_line = self._find_component_end(content, body_start)

            # Extract JSX structure from the component body
            component_body = content[
                body_start : self._get_char_position(content, end_line)
            ]
            jsx_structure = self._extract_jsx_structure(component_body)
            style_refs = self._extract_style_refs(component_body)

            is_exported = "export" in match.group(0)

            components.append(
                ExtractedComponent(
                    name=name,
                    source_ref=self._create_symbol_ref(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        name=name,
                        kind=SymbolKind.COMPONENT,
                        visibility=(
                            Visibility.EXPORTED if is_exported else Visibility.LOCAL
                        ),
                    ),
                    tag_name=name,
                    props=self._parse_props(props),
                    children_structure=jsx_structure,
                    style_refs=style_refs,
                    framework="react",
                )
            )

        # Arrow function components: const Name = () =>
        for match in re.finditer(
            r"(?:export\s+)?(?:const|let)\s+([A-Z][a-zA-Z0-9_]*)\s*(?::\s*[^=]+)?\s*=\s*(?:\([^)]*\)|[a-zA-Z_][a-zA-Z0-9_]*)\s*(?::\s*[^=]+)?\s*=>\s*[\({]",
            content,
        ):
            name = match.group(1)
            start_line = content[: match.start()].count("\n") + 1

            # Find the component's end
            body_start = match.end()
            end_line = self._find_component_end(content, body_start - 1)

            component_body = content[
                body_start : self._get_char_position(content, end_line)
            ]
            jsx_structure = self._extract_jsx_structure(component_body)
            style_refs = self._extract_style_refs(component_body)

            is_exported = "export" in match.group(0)

            components.append(
                ExtractedComponent(
                    name=name,
                    source_ref=self._create_symbol_ref(
                        file_path=file_path,
                        start_line=start_line,
                        end_line=end_line,
                        name=name,
                        kind=SymbolKind.COMPONENT,
                        visibility=(
                            Visibility.EXPORTED if is_exported else Visibility.LOCAL
                        ),
                    ),
                    tag_name=name,
                    props={},  # Would need more complex parsing
                    children_structure=jsx_structure,
                    style_refs=style_refs,
                    framework="react",
                )
            )

        # Class components: class Name extends Component
        for match in re.finditer(
            r"(?:export\s+)?(?:default\s+)?class\s+([A-Z][a-zA-Z0-9_]*)\s+extends\s+(?:React\.)?(?:Component|PureComponent)",
            content,
        ):
            name = match.group(1)
            start_line = content[: match.start()].count("\n") + 1

            # Find class body
            body_match = re.search(r"\{", content[match.end() :])
            if body_match:
                body_start = match.end() + body_match.end()
                end_line = self._find_component_end(content, body_start)

                component_body = content[
                    body_start : self._get_char_position(content, end_line)
                ]
                jsx_structure = self._extract_jsx_structure(component_body)
                style_refs = self._extract_style_refs(component_body)

                is_exported = "export" in match.group(0)

                components.append(
                    ExtractedComponent(
                        name=name,
                        source_ref=self._create_symbol_ref(
                            file_path=file_path,
                            start_line=start_line,
                            end_line=end_line,
                            name=name,
                            kind=SymbolKind.COMPONENT,
                            visibility=(
                                Visibility.EXPORTED if is_exported else Visibility.LOCAL
                            ),
                        ),
                        tag_name=name,
                        props={},
                        children_structure=jsx_structure,
                        style_refs=style_refs,
                        framework="react",
                    )
                )

        return components

    def extract_style_usage(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedStyle]:
        """Extract style usage from JSX.

        Args:
            file_path: Path to the JSX/TSX file.
            content: Optional file content.

        Returns:
            List of ExtractedStyle objects.
        """
        content = self._read_file(file_path, content)
        styles = []

        # Find className attributes
        for match in re.finditer(r'className\s*=\s*["\']([^"\']+)["\']', content):
            class_names = match.group(1).split()
            line_number = content[: match.start()].count("\n") + 1

            styles.append(
                ExtractedStyle(
                    source_ref=self._create_symbol_ref(
                        file_path=file_path,
                        start_line=line_number,
                        end_line=line_number,
                        kind=SymbolKind.STYLE_OBJECT,
                    ),
                    selector=None,
                    declarations={},
                    is_inline=False,
                    class_names=class_names,
                )
            )

        # Find className with template literals or expressions
        for match in re.finditer(r"className\s*=\s*\{([^}]+)\}", content):
            expr = match.group(1)
            line_number = content[: match.start()].count("\n") + 1

            # Try to extract literal class names from expressions
            class_names = self._extract_classes_from_expression(expr)

            if class_names:
                styles.append(
                    ExtractedStyle(
                        source_ref=self._create_symbol_ref(
                            file_path=file_path,
                            start_line=line_number,
                            end_line=line_number,
                            kind=SymbolKind.STYLE_OBJECT,
                        ),
                        selector=None,
                        declarations={},
                        is_inline=False,
                        class_names=class_names,
                    )
                )

        # Find inline styles: style={{ ... }}
        for match in re.finditer(r"style\s*=\s*\{\{([^}]+)\}\}", content):
            style_content = match.group(1)
            line_number = content[: match.start()].count("\n") + 1
            declarations = self._parse_inline_style(style_content)

            styles.append(
                ExtractedStyle(
                    source_ref=self._create_symbol_ref(
                        file_path=file_path,
                        start_line=line_number,
                        end_line=line_number,
                        kind=SymbolKind.STYLE_OBJECT,
                    ),
                    selector=None,
                    declarations=declarations,
                    is_inline=True,
                    class_names=[],
                )
            )

        return styles

    def _find_component_end(self, content: str, start_pos: int) -> int:
        """Find the ending line of a component body.

        Uses brace matching to find the end of the component.

        Args:
            content: File content.
            start_pos: Position after the opening brace.

        Returns:
            Line number of the closing brace.
        """
        depth = 1
        pos = start_pos

        while pos < len(content) and depth > 0:
            char = content[pos]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            pos += 1

        return content[:pos].count("\n") + 1

    def _get_char_position(self, content: str, line_number: int) -> int:
        """Get character position for a line number.

        Args:
            content: File content.
            line_number: Line number (1-based).

        Returns:
            Character position of the start of that line.
        """
        lines = content.split("\n")
        pos = 0
        for i in range(min(line_number - 1, len(lines))):
            pos += len(lines[i]) + 1  # +1 for newline
        return pos

    def _extract_jsx_structure(self, content: str) -> str:
        """Extract normalized JSX structure from component body.

        Args:
            content: Component body content.

        Returns:
            Normalized JSX structure.
        """
        # Find JSX elements and extract tag structure
        tags = re.findall(r"<([A-Za-z][A-Za-z0-9]*)", content)
        return " ".join(tags) if tags else ""

    def _extract_style_refs(self, content: str) -> list[str]:
        """Extract style references from component.

        Args:
            content: Component content.

        Returns:
            List of class names and style references.
        """
        refs = []

        # Extract from className strings
        for match in re.findall(r'className\s*=\s*["\']([^"\']+)["\']', content):
            refs.extend(match.split())

        # Extract CSS module references (styles.xxx)
        refs.extend(re.findall(r"styles\.([a-zA-Z_][a-zA-Z0-9_]*)", content))

        return list(set(refs))

    def _parse_props(self, props_str: str) -> dict:
        """Parse component props definition.

        Args:
            props_str: Props string from function signature.

        Returns:
            Dictionary with prop information.
        """
        # Simple extraction - just identify prop names
        props = {}

        # Handle destructured props: { prop1, prop2, prop3: alias }
        if "{" in props_str:
            inner = re.search(r"\{([^}]*)\}", props_str)
            if inner:
                for prop in inner.group(1).split(","):
                    prop = prop.strip()
                    if prop:
                        # Handle renamed props: original: renamed
                        name = prop.split(":")[0].strip()
                        if name and not name.startswith("..."):
                            props[name] = "any"

        return props

    def _extract_classes_from_expression(self, expr: str) -> list[str]:
        """Extract class names from a className expression.

        Args:
            expr: JavaScript expression string.

        Returns:
            List of class names found.
        """
        classes = []

        # Look for string literals in the expression
        for match in re.findall(r'["\']([^"\']+)["\']', expr):
            classes.extend(match.split())

        # Look for template literal parts
        for match in re.findall(r"`([^`]+)`", expr):
            # Extract non-expression parts
            parts = re.sub(r"\$\{[^}]+\}", "", match)
            classes.extend(parts.split())

        return [c for c in classes if c and not c.startswith("$")]

    def _parse_inline_style(self, style_content: str) -> dict[str, str]:
        """Parse inline style object to CSS declarations.

        Args:
            style_content: Content between style={{ and }}.

        Returns:
            Dictionary of CSS property -> value pairs.
        """
        declarations = {}

        # Match property: value or property: 'value'
        for match in re.finditer(
            r"([a-zA-Z]+)\s*:\s*(?:['\"]([^'\"]+)['\"]|([^,}\s]+))", style_content
        ):
            prop = match.group(1)
            value = match.group(2) or match.group(3)

            # Convert camelCase to kebab-case
            css_prop = re.sub(r"([A-Z])", r"-\1", prop).lower()

            if value:
                declarations[css_prop] = value

        return declarations
