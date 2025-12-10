"""CSS Variables token adapter.

Extracts design tokens from CSS files containing :root CSS custom properties.
"""

import re
from pathlib import Path

from ..tokens import (
    ColorToken,
    RadiusToken,
    ShadowToken,
    SpacingToken,
    TokenSet,
    TypographyToken,
)
from .base import TokenAdapter


class CSSVariablesAdapter(TokenAdapter):
    """Adapter for extracting design tokens from CSS custom properties.

    Parses CSS files looking for :root { --var-name: value; } patterns
    and categorizes tokens based on naming conventions.

    Naming conventions recognized:
    - Colors: --color-*, --bg-*, --text-*, --border-color-*
    - Spacing: --spacing-*, --space-*, --gap-*, --margin-*, --padding-*
    - Radius: --radius-*, --rounded-*, --border-radius-*
    - Typography: --font-size-*, --text-*, --leading-*, --tracking-*
    - Shadows: --shadow-*, --elevation-*
    """

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return [".css", ".scss", ".less"]

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file."""
        return file_path.suffix.lower() in self.supported_extensions

    def extract(self, file_path: Path) -> TokenSet:
        """Extract tokens from a CSS file.

        Args:
            file_path: Path to the CSS file.

        Returns:
            TokenSet containing all extracted tokens.

        Raises:
            FileNotFoundError: If the file doesn't exist.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"CSS file not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        token_set = self.extract_from_content(content, str(file_path))
        token_set.source_files.append(str(file_path))
        return token_set

    def extract_from_content(self, content: str, source_name: str = "inline") -> TokenSet:
        """Extract tokens from CSS content string.

        Args:
            content: CSS content to parse.
            source_name: Name for source tracking.

        Returns:
            TokenSet containing all extracted tokens.
        """
        colors: dict[str, ColorToken] = {}
        spacing: dict[str, SpacingToken] = {}
        radii: dict[str, RadiusToken] = {}
        typography: dict[str, TypographyToken] = {}
        shadows: dict[str, ShadowToken] = {}

        # Extract all CSS custom properties from :root or * selectors
        # Match :root { ... } or :root, :host { ... } blocks
        root_pattern = re.compile(
            r":root\s*(?:,\s*:host)?\s*\{([^}]+)\}", re.IGNORECASE | re.DOTALL
        )

        for match in root_pattern.finditer(content):
            block_content = match.group(1)
            # Extract individual --var: value pairs
            var_pattern = re.compile(r"--([\w-]+)\s*:\s*([^;]+);")

            for var_match in var_pattern.finditer(block_content):
                var_name = var_match.group(1).strip()
                var_value = var_match.group(2).strip()

                # Categorize based on naming convention
                lower_name = var_name.lower()

                if self._is_color_var(lower_name, var_value):
                    category = self._extract_color_category(lower_name)
                    colors[var_name] = ColorToken(
                        name=var_name,
                        value=ColorToken.normalize_color(var_value),
                        original_value=var_value,
                        category=category,
                    )
                elif self._is_spacing_var(lower_name):
                    px_value = SpacingToken.normalize_length(var_value)
                    spacing[var_name] = SpacingToken(
                        name=var_name,
                        value=px_value,
                        original_value=var_value,
                    )
                elif self._is_radius_var(lower_name):
                    px_value = SpacingToken.normalize_length(var_value)
                    radii[var_name] = RadiusToken(
                        name=var_name,
                        value=px_value,
                    )
                elif self._is_shadow_var(lower_name):
                    shadows[var_name] = ShadowToken(
                        name=var_name,
                        value=var_value,
                    )
                elif self._is_font_size_var(lower_name):
                    px_value = SpacingToken.normalize_length(var_value)
                    typography[var_name] = TypographyToken(
                        name=var_name,
                        size=px_value,
                    )

        return TokenSet(
            colors=colors,
            spacing=spacing,
            radii=radii,
            typography=typography,
            shadows=shadows,
        )

    def _is_color_var(self, name: str, value: str) -> bool:
        """Check if a variable is a color token."""
        color_prefixes = (
            "color-",
            "bg-",
            "text-",
            "border-color",
            "background-",
            "foreground-",
            "accent-",
            "primary-",
            "secondary-",
            "success-",
            "warning-",
            "error-",
            "danger-",
            "info-",
            "neutral-",
            "gray-",
            "grey-",
        )
        if any(name.startswith(prefix) for prefix in color_prefixes):
            return True

        # Also check if value looks like a color
        value_lower = value.lower()
        return (
            value_lower.startswith("#")
            or value_lower.startswith("rgb")
            or value_lower.startswith("hsl")
            or value_lower in ("transparent", "currentcolor", "inherit")
        )

    def _is_spacing_var(self, name: str) -> bool:
        """Check if a variable is a spacing token."""
        spacing_prefixes = (
            "spacing-",
            "space-",
            "gap-",
            "margin-",
            "padding-",
            "inset-",
        )
        return any(name.startswith(prefix) for prefix in spacing_prefixes)

    def _is_radius_var(self, name: str) -> bool:
        """Check if a variable is a radius token."""
        radius_prefixes = ("radius-", "rounded-", "border-radius-", "corner-")
        return any(name.startswith(prefix) for prefix in radius_prefixes)

    def _is_shadow_var(self, name: str) -> bool:
        """Check if a variable is a shadow token."""
        shadow_prefixes = ("shadow-", "elevation-", "box-shadow-")
        return any(name.startswith(prefix) for prefix in shadow_prefixes)

    def _is_font_size_var(self, name: str) -> bool:
        """Check if a variable is a font size token."""
        font_prefixes = ("font-size-", "text-size-", "fs-")
        return any(name.startswith(prefix) for prefix in font_prefixes)

    def _extract_color_category(self, name: str) -> str | None:
        """Extract color category from variable name."""
        categories = [
            "primary",
            "secondary",
            "accent",
            "success",
            "warning",
            "error",
            "danger",
            "info",
            "neutral",
            "gray",
            "grey",
        ]
        for cat in categories:
            if cat in name:
                return cat
        return None
