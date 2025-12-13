"""Tailwind CSS config token adapter.

Extracts design tokens from tailwind.config.js/ts files.
"""

import re
from pathlib import Path

from ..tokens import (
    ColorToken,
    RadiusToken,
    ShadowToken,
    SpacingToken,
    TokenSet,
)
from .base import TokenAdapter


class TailwindConfigAdapter(TokenAdapter):
    """Adapter for extracting design tokens from Tailwind CSS configuration.

    Parses tailwind.config.js or tailwind.config.ts files to extract
    theme tokens including colors, spacing, borderRadius, and boxShadow.

    Note: This adapter uses regex-based parsing to extract the theme object
    from JavaScript/TypeScript files. For complex configs with dynamic values,
    results may be incomplete.
    """

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return [".js", ".ts", ".mjs", ".cjs"]

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file.

        Only handles files named tailwind.config.*
        """
        if file_path.suffix.lower() not in self.supported_extensions:
            return False
        return file_path.stem.lower() == "tailwind.config"

    def extract(self, file_path: Path) -> TokenSet:
        """Extract tokens from a Tailwind config file.

        Args:
            file_path: Path to the Tailwind config file.

        Returns:
            TokenSet containing all extracted tokens.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Tailwind config not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        token_set = self.extract_from_content(content, str(file_path))
        token_set.source_files.append(str(file_path))
        return token_set

    def extract_from_content(
        self, content: str, source_name: str = "inline"
    ) -> TokenSet:
        """Extract tokens from Tailwind config content.

        Args:
            content: Tailwind config content to parse.
            source_name: Name for source tracking.

        Returns:
            TokenSet containing all extracted tokens.
        """
        colors: dict[str, ColorToken] = {}
        spacing: dict[str, SpacingToken] = {}
        radii: dict[str, RadiusToken] = {}
        shadows: dict[str, ShadowToken] = {}

        # Try to extract the theme object
        theme_content = self._extract_theme_section(content)
        if not theme_content:
            return TokenSet()

        # Extract colors
        colors_section = self._extract_section(theme_content, "colors")
        if colors_section:
            colors = self._parse_colors(colors_section)

        # Also check extend.colors
        extend_section = self._extract_section(theme_content, "extend")
        if extend_section:
            extend_colors = self._extract_section(extend_section, "colors")
            if extend_colors:
                colors.update(self._parse_colors(extend_colors))

        # Extract spacing
        spacing_section = self._extract_section(theme_content, "spacing")
        if spacing_section:
            spacing = self._parse_spacing(spacing_section)

        if extend_section:
            extend_spacing = self._extract_section(extend_section, "spacing")
            if extend_spacing:
                spacing.update(self._parse_spacing(extend_spacing))

        # Extract borderRadius
        radius_section = self._extract_section(theme_content, "borderRadius")
        if radius_section:
            radii = self._parse_radii(radius_section)

        if extend_section:
            extend_radius = self._extract_section(extend_section, "borderRadius")
            if extend_radius:
                radii.update(self._parse_radii(extend_radius))

        # Extract boxShadow
        shadow_section = self._extract_section(theme_content, "boxShadow")
        if shadow_section:
            shadows = self._parse_shadows(shadow_section)

        if extend_section:
            extend_shadow = self._extract_section(extend_section, "boxShadow")
            if extend_shadow:
                shadows.update(self._parse_shadows(extend_shadow))

        return TokenSet(
            colors=colors,
            spacing=spacing,
            radii=radii,
            shadows=shadows,
        )

    def _extract_theme_section(self, content: str) -> str | None:
        """Extract the theme section from Tailwind config."""
        # Look for theme: { ... } in the config
        # This is a simplified extraction that handles most common cases
        theme_pattern = re.compile(r"theme\s*:\s*\{", re.IGNORECASE)
        match = theme_pattern.search(content)
        if not match:
            return None

        # Find matching closing brace
        start = match.end() - 1  # Include the opening brace
        return self._extract_balanced_braces(content, start)

    def _extract_section(self, content: str, section_name: str) -> str | None:
        """Extract a named section from object content."""
        # Look for section_name: { ... } or section_name: '...' or section_name: "..."
        pattern = re.compile(rf"{section_name}\s*:\s*\{{", re.IGNORECASE)
        match = pattern.search(content)
        if match:
            start = match.end() - 1
            return self._extract_balanced_braces(content, start)
        return None

    def _extract_balanced_braces(self, content: str, start: int) -> str | None:
        """Extract content between balanced braces starting at position."""
        if start >= len(content) or content[start] != "{":
            return None

        depth = 0
        end = start
        in_string = False
        string_char = None

        for i in range(start, len(content)):
            char = content[i]

            # Handle string literals
            if char in ('"', "'", "`") and (i == 0 or content[i - 1] != "\\"):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if depth != 0:
            return None

        return content[start : end + 1]

    def _parse_colors(self, section: str) -> dict[str, ColorToken]:
        """Parse colors section into ColorTokens."""
        colors: dict[str, ColorToken] = {}

        # Extract simple key-value pairs: 'name': '#value' or name: '#value'
        simple_pattern = re.compile(r"""['"]?([\w-]+)['"]?\s*:\s*['"]([^'"]+)['"]""")

        for match in simple_pattern.finditer(section):
            name = match.group(1)
            value = match.group(2)

            # Skip if it looks like a reference or function
            if value.startswith("var(") or value.startswith("theme("):
                continue

            try:
                normalized = ColorToken.normalize_color(value)
                colors[name] = ColorToken(
                    name=name,
                    value=normalized,
                    original_value=value,
                )
            except (ValueError, AttributeError):
                # Skip values that can't be normalized
                pass

        # Also try to extract nested color objects (e.g., gray: { 100: '#f5f5f5', ... })
        nested_pattern = re.compile(
            r"""['"]?([\w-]+)['"]?\s*:\s*\{([^{}]+)\}""", re.DOTALL
        )

        for match in nested_pattern.finditer(section):
            prefix = match.group(1)
            nested_content = match.group(2)

            for nested_match in simple_pattern.finditer(nested_content):
                shade = nested_match.group(1)
                value = nested_match.group(2)

                if value.startswith("var(") or value.startswith("theme("):
                    continue

                full_name = f"{prefix}-{shade}"
                try:
                    normalized = ColorToken.normalize_color(value)
                    colors[full_name] = ColorToken(
                        name=full_name,
                        value=normalized,
                        original_value=value,
                        category=prefix,
                    )
                except (ValueError, AttributeError):
                    pass

        return colors

    def _parse_spacing(self, section: str) -> dict[str, SpacingToken]:
        """Parse spacing section into SpacingTokens."""
        spacing: dict[str, SpacingToken] = {}

        # Extract key-value pairs
        pattern = re.compile(r"""['"]?([\w.-]+)['"]?\s*:\s*['"]?([^'",}\s]+)['"]?""")

        for match in pattern.finditer(section):
            name = match.group(1)
            value = match.group(2).strip()

            # Skip references
            if value.startswith("var(") or value.startswith("theme("):
                continue

            px_value = SpacingToken.normalize_length(value)
            if px_value >= 0:
                spacing[name] = SpacingToken(
                    name=name,
                    value=px_value,
                    original_value=value,
                )

        return spacing

    def _parse_radii(self, section: str) -> dict[str, RadiusToken]:
        """Parse borderRadius section into RadiusTokens."""
        radii: dict[str, RadiusToken] = {}

        pattern = re.compile(r"""['"]?([\w-]+)['"]?\s*:\s*['"]?([^'",}\s]+)['"]?""")

        for match in pattern.finditer(section):
            name = match.group(1)
            value = match.group(2).strip()

            if value.startswith("var(") or value.startswith("theme("):
                continue

            # Handle special values
            if value == "9999px" or value == "full":
                px_value = 9999.0
            else:
                px_value = SpacingToken.normalize_length(value)

            if px_value >= 0:
                radii[name] = RadiusToken(
                    name=name,
                    value=px_value,
                )

        return radii

    def _parse_shadows(self, section: str) -> dict[str, ShadowToken]:
        """Parse boxShadow section into ShadowTokens."""
        shadows: dict[str, ShadowToken] = {}

        # Shadow values can be complex, extract name: "value" pairs
        pattern = re.compile(
            r"""['"]?([\w-]+)['"]?\s*:\s*['"]([^'"]+)['"]""", re.DOTALL
        )

        for match in pattern.finditer(section):
            name = match.group(1)
            value = match.group(2).strip()

            if value.startswith("var(") or value.startswith("theme("):
                continue

            shadows[name] = ShadowToken(
                name=name,
                value=value,
            )

        return shadows
