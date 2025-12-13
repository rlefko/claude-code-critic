"""Svelte adapter for extracting components and styles.

This module provides the SvelteAdapter class that extracts Svelte
components from .svelte files.
"""

import re
from pathlib import Path

from ...models import SymbolKind, Visibility
from ..base import BaseSourceAdapter, ExtractedComponent, ExtractedStyle


class SvelteAdapter(BaseSourceAdapter):
    """Adapter for Svelte component files (.svelte).

    Extracts component definitions from Svelte's template-based syntax.
    """

    SUPPORTED_EXTENSIONS = [".svelte"]

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return self.SUPPORTED_EXTENSIONS

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file."""
        return file_path.suffix.lower() == ".svelte"

    def extract_components(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedComponent]:
        """Extract Svelte component definition.

        Each .svelte file is a single component.

        Args:
            file_path: Path to the .svelte file.
            content: Optional file content.

        Returns:
            List containing the Svelte component.
        """
        content = self._read_file(file_path, content)
        components = []

        # Component name from filename
        component_name = file_path.stem

        # Extract script section for props
        script = self._extract_section(content, "script")
        props = self._extract_props(script) if script else {}

        # Get template structure (everything outside script and style)
        template = self._extract_template(content)
        template_structure = self._extract_template_structure(template)
        style_refs = self._extract_style_refs(template)

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
                framework="svelte",
            )
        )

        return components

    def extract_style_usage(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedStyle]:
        """Extract style usage from Svelte file.

        Args:
            file_path: Path to the .svelte file.
            content: Optional file content.

        Returns:
            List of ExtractedStyle objects.
        """
        content = self._read_file(file_path, content)
        styles = []

        # Extract from template
        template = self._extract_template(content)

        # Find class attributes
        for match in re.finditer(r'class\s*=\s*["\']([^"\']+)["\']', template):
            class_names = match.group(1).split()
            line_number = content[: content.find(match.group(0))].count("\n") + 1

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

        # Find class directives: class:name or class:name={condition}
        for match in re.finditer(r"class:([a-zA-Z_-][a-zA-Z0-9_-]*)", template):
            class_name = match.group(1)
            line_number = content[: content.find(match.group(0))].count("\n") + 1

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
                    class_names=[class_name],
                )
            )

        # Find inline styles: style="..."
        for match in re.finditer(r'style\s*=\s*["\']([^"\']+)["\']', template):
            style_content = match.group(1)
            line_number = content[: content.find(match.group(0))].count("\n") + 1
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

        # Extract from style section
        style_section = self._extract_section(content, "style")
        if style_section:
            style_start = content.find("<style")
            style_line_offset = (
                content[:style_start].count("\n") if style_start >= 0 else 0
            )

            for rule in self._find_css_rules(style_section):
                selector = rule["selector"]
                declarations = rule["declarations"]
                line_number = style_line_offset + rule["line_offset"]

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
            section: Section name (script, style).

        Returns:
            Section content or None if not found.
        """
        pattern = rf"<{section}[^>]*>([\s\S]*?)</{section}>"
        match = re.search(pattern, content, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_template(self, content: str) -> str:
        """Extract template content (outside script and style).

        Args:
            content: Full file content.

        Returns:
            Template content.
        """
        # Remove script sections
        template = re.sub(
            r"<script[^>]*>[\s\S]*?</script>", "", content, flags=re.IGNORECASE
        )
        # Remove style sections
        template = re.sub(
            r"<style[^>]*>[\s\S]*?</style>", "", template, flags=re.IGNORECASE
        )
        return template.strip()

    def _extract_template_structure(self, template: str) -> str:
        """Extract structural skeleton from template.

        Args:
            template: Template content.

        Returns:
            Space-separated list of element tags.
        """
        tags = re.findall(r"<([a-zA-Z][a-zA-Z0-9]*)", template)
        return " ".join(tags)

    def _extract_style_refs(self, template: str) -> list[str]:
        """Extract class references from template.

        Args:
            template: Template content.

        Returns:
            List of class names.
        """
        refs = []

        # Static classes
        for match in re.findall(r'class\s*=\s*["\']([^"\']+)["\']', template):
            refs.extend(match.split())

        # Class directives
        refs.extend(re.findall(r"class:([a-zA-Z_-][a-zA-Z0-9_-]*)", template))

        return list(set(refs))

    def _extract_props(self, script: str) -> dict:
        """Extract props from script section.

        Args:
            script: Script section content.

        Returns:
            Dictionary of prop names.
        """
        props = {}

        # Svelte uses export let for props
        for match in re.finditer(r"export\s+let\s+(\w+)", script):
            props[match.group(1)] = "any"

        # Also check for $props()
        props_match = re.search(r"\$props\s*\(\s*\)", script)
        if props_match:
            # Can't determine individual props without more context
            pass

        return props

    def _parse_inline_style(self, style_content: str) -> dict[str, str]:
        """Parse inline style string to declarations.

        Args:
            style_content: CSS inline style string.

        Returns:
            Dictionary of property -> value pairs.
        """
        declarations = {}

        for decl in style_content.split(";"):
            decl = decl.strip()
            if ":" in decl:
                parts = decl.split(":", 1)
                prop = parts[0].strip()
                value = parts[1].strip()
                if prop and value:
                    declarations[prop] = value

        return declarations

    def _find_css_rules(self, style_content: str) -> list[dict]:
        """Find CSS rules in style section.

        Args:
            style_content: Style section content.

        Returns:
            List of rule dicts.
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
