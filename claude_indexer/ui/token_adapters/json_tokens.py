"""JSON design token adapter.

Extracts design tokens from JSON token files, supporting Style Dictionary
and similar token formats.
"""

import json
from pathlib import Path
from typing import Any

from ..tokens import (
    ColorToken,
    RadiusToken,
    ShadowToken,
    SpacingToken,
    TokenSet,
    TypographyToken,
)
from .base import TokenAdapter


class JSONTokenAdapter(TokenAdapter):
    """Adapter for extracting design tokens from JSON token files.

    Supports various JSON token formats including:
    - Style Dictionary format (with $value and value keys)
    - Tokens Studio format
    - Flat key-value format
    - Nested category format

    Token categorization is based on:
    - Explicit "type" or "$type" fields
    - Category names in nested structure (color, spacing, etc.)
    - Value format detection (e.g., hex colors, px values)
    """

    @property
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        return [".json", ".tokens.json"]

    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file.

        Handles .json files, with preference for files with 'token'
        in the name or .tokens.json extension.
        """
        name_lower = file_path.name.lower()
        suffix_lower = file_path.suffix.lower()

        if suffix_lower == ".json":
            # Prefer files with 'token' in name
            return "token" in name_lower or "design" in name_lower

        return False

    def extract(self, file_path: Path) -> TokenSet:
        """Extract tokens from a JSON token file.

        Args:
            file_path: Path to the JSON token file.

        Returns:
            TokenSet containing all extracted tokens.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"JSON token file not found: {file_path}")

        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)

        token_set = self._extract_from_data(data)
        token_set.source_files.append(str(file_path))
        return token_set

    def extract_from_content(
        self, content: str, source_name: str = "inline"
    ) -> TokenSet:
        """Extract tokens from JSON content string.

        Args:
            content: JSON content to parse.
            source_name: Name for source tracking.

        Returns:
            TokenSet containing all extracted tokens.
        """
        data = json.loads(content)
        token_set = self._extract_from_data(data)
        token_set.source_files.append(source_name)
        return token_set

    def _extract_from_data(self, data: dict[str, Any]) -> TokenSet:
        """Extract tokens from parsed JSON data.

        Args:
            data: Parsed JSON data.

        Returns:
            TokenSet containing all extracted tokens.
        """
        colors: dict[str, ColorToken] = {}
        spacing: dict[str, SpacingToken] = {}
        radii: dict[str, RadiusToken] = {}
        typography: dict[str, TypographyToken] = {}
        shadows: dict[str, ShadowToken] = {}

        # Process the data recursively
        self._process_object(
            data,
            prefix="",
            colors=colors,
            spacing=spacing,
            radii=radii,
            typography=typography,
            shadows=shadows,
        )

        return TokenSet(
            colors=colors,
            spacing=spacing,
            radii=radii,
            typography=typography,
            shadows=shadows,
        )

    def _process_object(
        self,
        obj: dict[str, Any],
        prefix: str,
        colors: dict[str, ColorToken],
        spacing: dict[str, SpacingToken],
        radii: dict[str, RadiusToken],
        typography: dict[str, TypographyToken],
        shadows: dict[str, ShadowToken],
        category_hint: str | None = None,
    ) -> None:
        """Recursively process a JSON object to extract tokens.

        Args:
            obj: The JSON object to process.
            prefix: Current path prefix for nested keys.
            colors: Dict to store color tokens.
            spacing: Dict to store spacing tokens.
            radii: Dict to store radius tokens.
            typography: Dict to store typography tokens.
            shadows: Dict to store shadow tokens.
            category_hint: Hint about the token category from parent keys.
        """
        for key, value in obj.items():
            # Skip metadata keys
            if key.startswith("$") and key not in ("$value", "$type"):
                continue

            # Build the full token name
            full_name = f"{prefix}-{key}" if prefix else key
            full_name = full_name.strip("-")

            # Determine category hint from key
            key_lower = key.lower()
            new_category_hint = category_hint

            if key_lower in ("color", "colors", "colour", "colours"):
                new_category_hint = "color"
            elif key_lower in ("spacing", "space", "spaces"):
                new_category_hint = "spacing"
            elif key_lower in (
                "radius",
                "radii",
                "borderradius",
                "border-radius",
                "rounded",
            ):
                new_category_hint = "radius"
            elif key_lower in (
                "typography",
                "font",
                "fonts",
                "fontsize",
                "font-size",
                "text",
            ):
                new_category_hint = "typography"
            elif key_lower in ("shadow", "shadows", "boxshadow", "elevation"):
                new_category_hint = "shadow"

            if isinstance(value, dict):
                # Check if this is a leaf token (has $value or value)
                token_value = value.get("$value") or value.get("value")
                token_type = value.get("$type") or value.get("type")

                if token_value is not None:
                    # This is a token leaf
                    self._add_token(
                        full_name,
                        token_value,
                        token_type,
                        new_category_hint,
                        colors,
                        spacing,
                        radii,
                        typography,
                        shadows,
                    )
                else:
                    # Recurse into nested object
                    self._process_object(
                        value,
                        full_name,
                        colors,
                        spacing,
                        radii,
                        typography,
                        shadows,
                        new_category_hint,
                    )
            elif isinstance(value, (str, int, float)):
                # Direct value (flat format)
                self._add_token(
                    full_name,
                    value,
                    None,
                    new_category_hint,
                    colors,
                    spacing,
                    radii,
                    typography,
                    shadows,
                )

    def _add_token(
        self,
        name: str,
        value: Any,
        explicit_type: str | None,
        category_hint: str | None,
        colors: dict[str, ColorToken],
        spacing: dict[str, SpacingToken],
        radii: dict[str, RadiusToken],
        typography: dict[str, TypographyToken],
        shadows: dict[str, ShadowToken],
    ) -> None:
        """Add a token to the appropriate category.

        Args:
            name: Token name.
            value: Token value.
            explicit_type: Explicit type from $type field.
            category_hint: Category hint from parent structure.
            colors: Dict to store color tokens.
            spacing: Dict to store spacing tokens.
            radii: Dict to store radius tokens.
            typography: Dict to store typography tokens.
            shadows: Dict to store shadow tokens.
        """
        # Convert value to string for processing
        str_value = str(value) if value is not None else ""

        # Determine token type
        token_type = explicit_type or self._infer_type(name, str_value, category_hint)

        if token_type == "color":
            try:
                normalized = ColorToken.normalize_color(str_value)
                category = self._extract_color_category(name)
                colors[name] = ColorToken(
                    name=name,
                    value=normalized,
                    original_value=str_value,
                    category=category,
                )
            except (ValueError, AttributeError):
                pass

        elif token_type == "spacing" or token_type == "dimension":
            px_value = SpacingToken.normalize_length(str_value)
            if px_value >= 0:
                spacing[name] = SpacingToken(
                    name=name,
                    value=px_value,
                    original_value=str_value,
                )

        elif token_type == "borderRadius" or token_type == "radius":
            px_value = SpacingToken.normalize_length(str_value)
            if str_value.lower() == "full" or str_value == "9999px":
                px_value = 9999.0
            if px_value >= 0:
                radii[name] = RadiusToken(
                    name=name,
                    value=px_value,
                )

        elif token_type == "boxShadow" or token_type == "shadow":
            shadows[name] = ShadowToken(
                name=name,
                value=str_value,
            )

        elif token_type == "fontSizes" or token_type == "fontSize":
            px_value = SpacingToken.normalize_length(str_value)
            if px_value > 0:
                typography[name] = TypographyToken(
                    name=name,
                    size=px_value,
                )

    def _infer_type(
        self, name: str, value: str, category_hint: str | None
    ) -> str | None:
        """Infer the token type from name, value, and category hint.

        Args:
            name: Token name.
            value: Token value as string.
            category_hint: Category hint from parent structure.

        Returns:
            Inferred token type or None.
        """
        # Use category hint if available
        if category_hint:
            return category_hint

        name_lower = name.lower()
        value_lower = value.lower()

        # Check value format
        if (
            value_lower.startswith("#")
            or value_lower.startswith("rgb")
            or value_lower.startswith("hsl")
        ):
            return "color"

        # Check name patterns
        color_patterns = ("color", "bg", "background", "foreground", "text-", "border")
        spacing_patterns = ("spacing", "space", "gap", "margin", "padding", "inset")
        radius_patterns = ("radius", "rounded", "corner")
        shadow_patterns = ("shadow", "elevation")
        font_patterns = ("font-size", "fontsize", "text-size", "fs-")

        for pattern in color_patterns:
            if pattern in name_lower:
                return "color"

        for pattern in spacing_patterns:
            if pattern in name_lower:
                return "spacing"

        for pattern in radius_patterns:
            if pattern in name_lower:
                return "radius"

        for pattern in shadow_patterns:
            if pattern in name_lower:
                return "shadow"

        for pattern in font_patterns:
            if pattern in name_lower:
                return "fontSize"

        # Check if value looks like a dimension
        if value_lower.endswith(("px", "rem", "em", "%")):
            return "spacing"

        return None

    def _extract_color_category(self, name: str) -> str | None:
        """Extract color category from token name."""
        name_lower = name.lower()
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
            "brand",
        ]
        for cat in categories:
            if cat in name_lower:
                return cat
        return None
