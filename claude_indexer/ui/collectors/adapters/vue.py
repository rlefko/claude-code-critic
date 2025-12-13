"""Vue adapter for extracting components and styles from .vue files.

This module provides the VueAdapter class that extracts Vue
components from Single File Components (SFCs).
"""

import re
from pathlib import Path

from ...models import SymbolKind, Visibility
from ..base import BaseSourceAdapter, ExtractedComponent, ExtractedStyle


class VueAdapter(BaseSourceAdapter):
    """Adapter for Vue Single File Components (.vue).

    Extracts component definitions from the template, script, and style
    sections of Vue SFCs.
    """

    SUPPORTED_EXTENSIONS = [".vue"]

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return self.SUPPORTED_EXTENSIONS

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file."""
        return file_path.suffix.lower() == ".vue"

    def extract_components(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedComponent]:
        """Extract Vue component definition.

        Args:
            file_path: Path to the .vue file.
            content: Optional file content.

        Returns:
            List containing the Vue component.
        """
        content = self._read_file(file_path, content)
        components = []

        # Extract template section
        template = self._extract_section(content, "template")
        script = self._extract_section(content, "script")

        # Component name from filename or script
        component_name = self._extract_component_name(file_path, script)

        # Get template structure
        template_structure = ""
        style_refs = []

        if template:
            template_structure = self._extract_template_structure(template)
            style_refs = self._extract_style_refs(template)

        # Get props from script
        props = self._extract_props(script) if script else {}

        components.append(
            ExtractedComponent(
                name=component_name,
                source_ref=self._create_symbol_ref(
                    file_path=file_path,
                    start_line=1,
                    end_line=content.count("\n") + 1,
                    name=component_name,
                    kind=SymbolKind.COMPONENT,
                    visibility=Visibility.EXPORTED,
                ),
                tag_name=component_name,
                props=props,
                children_structure=template_structure,
                style_refs=style_refs,
                framework="vue",
            )
        )

        return components

    def extract_style_usage(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedStyle]:
        """Extract style usage from Vue SFC.

        Args:
            file_path: Path to the .vue file.
            content: Optional file content.

        Returns:
            List of ExtractedStyle objects.
        """
        content = self._read_file(file_path, content)
        styles = []

        # Extract from template section
        template = self._extract_section(content, "template")
        if template:
            template_start = content.find("<template")
            template_line_offset = (
                content[:template_start].count("\n") if template_start >= 0 else 0
            )

            # Find class bindings
            for match in re.finditer(
                r'(?:class|:class)\s*=\s*["\']([^"\']+)["\']', template
            ):
                class_names = match.group(1).split()
                line_number = (
                    template_line_offset + template[: match.start()].count("\n") + 1
                )

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

            # Find inline style bindings
            for match in re.finditer(r':style\s*=\s*["\']([^"\']+)["\']', template):
                match.group(1)
                line_number = (
                    template_line_offset + template[: match.start()].count("\n") + 1
                )

                styles.append(
                    ExtractedStyle(
                        source_ref=self._create_symbol_ref(
                            file_path=file_path,
                            start_line=line_number,
                            end_line=line_number,
                            kind=SymbolKind.STYLE_OBJECT,
                        ),
                        selector=None,
                        declarations={},  # Would need evaluation
                        is_inline=True,
                        class_names=[],
                    )
                )

        # Extract from style section
        style_section = self._extract_section(content, "style")
        if style_section:
            style_start = content.find("<style")
            style_line_offset = (
                content[:style_start].count("\n") if style_start >= 0 else 0
            )

            # Parse CSS rules
            for match in self._find_css_rules(style_section):
                selector = match["selector"]
                declarations = match["declarations"]
                line_number = style_line_offset + match["line_offset"]

                styles.append(
                    ExtractedStyle(
                        source_ref=self._create_symbol_ref(
                            file_path=file_path,
                            start_line=line_number,
                            end_line=line_number,
                            name=selector,
                            kind=SymbolKind.CSS,
                        ),
                        selector=selector,
                        declarations=declarations,
                        is_inline=False,
                        class_names=self._extract_class_names_from_selector(selector),
                    )
                )

        return styles

    def _extract_section(self, content: str, section: str) -> str | None:
        """Extract content between <section> and </section> tags.

        Args:
            content: Full file content.
            section: Section name (template, script, style).

        Returns:
            Section content or None if not found.
        """
        pattern = rf"<{section}[^>]*>([\s\S]*?)</{section}>"
        match = re.search(pattern, content, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_component_name(self, file_path: Path, script: str | None) -> str:
        """Extract component name from script or filename.

        Args:
            file_path: Path to the Vue file.
            script: Script section content.

        Returns:
            Component name.
        """
        # Try to find name in script
        if script:
            # Options API: name: 'ComponentName'
            match = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", script)
            if match:
                return match.group(1)

            # defineComponent with name
            match = re.search(
                r"defineComponent\(\s*\{[^}]*name\s*:\s*['\"]([^'\"]+)['\"]", script
            )
            if match:
                return match.group(1)

        # Fall back to filename
        return file_path.stem

    def _extract_template_structure(self, template: str) -> str:
        """Extract structural skeleton from template.

        Args:
            template: Template section content.

        Returns:
            Space-separated list of element tags.
        """
        tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9-]*)", template)
        return " ".join(tags)

    def _extract_style_refs(self, template: str) -> list[str]:
        """Extract class references from template.

        Args:
            template: Template section content.

        Returns:
            List of class names.
        """
        refs = []

        # Static classes
        for match in re.findall(r'class\s*=\s*["\']([^"\']+)["\']', template):
            refs.extend(match.split())

        # Dynamic classes (extract literal parts)
        for match in re.findall(r':class\s*=\s*["\']([^"\']+)["\']', template):
            # Try to extract literal class names from expressions
            refs.extend(re.findall(r"['\"]([a-zA-Z_-][a-zA-Z0-9_-]*)['\"]", match))

        return list(set(refs))

    def _extract_props(self, script: str) -> dict:
        """Extract props from script section.

        Args:
            script: Script section content.

        Returns:
            Dictionary of prop names.
        """
        props = {}

        # Options API: props: { name: Type, ... }
        props_match = re.search(r"props\s*:\s*\{([^}]+)\}", script)
        if props_match:
            props_content = props_match.group(1)
            for prop_match in re.finditer(r"(\w+)\s*:", props_content):
                props[prop_match.group(1)] = "any"

        # Options API: props: ['name1', 'name2', ...]
        array_match = re.search(r"props\s*:\s*\[([^\]]+)\]", script)
        if array_match:
            array_content = array_match.group(1)
            for name_match in re.finditer(r"['\"](\w+)['\"]", array_content):
                props[name_match.group(1)] = "any"

        # Composition API: defineProps
        define_props_match = re.search(r"defineProps\s*<\s*\{([^}]+)\}", script)
        if define_props_match:
            props_content = define_props_match.group(1)
            for prop_match in re.finditer(r"(\w+)\s*[?:]", props_content):
                props[prop_match.group(1)] = "any"

        return props

    def _find_css_rules(self, style_content: str) -> list[dict]:
        """Find CSS rules in style section.

        Args:
            style_content: Style section content.

        Returns:
            List of rule dicts with selector, declarations, line offset.
        """
        rules = []

        # Remove comments
        style_content = re.sub(r"/\*[\s\S]*?\*/", "", style_content)

        # Simple regex for CSS rules
        pattern = r"([^{}]+)\{([^{}]*)\}"
        for match in re.finditer(pattern, style_content):
            selector = match.group(1).strip()
            declarations_str = match.group(2).strip()

            if not selector or selector.startswith("@"):
                continue

            # Parse declarations
            declarations = {}
            for decl in declarations_str.split(";"):
                decl = decl.strip()
                if ":" in decl:
                    parts = decl.split(":", 1)
                    prop = parts[0].strip()
                    value = parts[1].strip()
                    if prop and value:
                        declarations[prop] = value

            line_offset = style_content[: match.start()].count("\n") + 1

            rules.append(
                {
                    "selector": selector,
                    "declarations": declarations,
                    "line_offset": line_offset,
                }
            )

        return rules

    def _extract_class_names_from_selector(self, selector: str) -> list[str]:
        """Extract class names from CSS selector.

        Args:
            selector: CSS selector string.

        Returns:
            List of class names.
        """
        matches = re.findall(r"\.([a-zA-Z_-][a-zA-Z0-9_-]*)", selector)
        return list(set(matches))
