"""Token resolver for mapping CSS values to design system tokens.

This module provides functionality to resolve CSS values (colors, spacing, etc.)
to their nearest design system tokens and detect off-scale (token drift) values.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..tokens import (
    ColorToken,
    SpacingToken,
    TokenSet,
)


class TokenCategory(Enum):
    """Categories of design tokens."""

    COLOR = "color"
    SPACING = "spacing"
    RADIUS = "radius"
    TYPOGRAPHY = "typography"
    SHADOW = "shadow"


class ResolutionStatus(Enum):
    """Status of token resolution."""

    EXACT_MATCH = "exact_match"  # Value matches a token exactly
    NEAR_MATCH = "near_match"  # Value is close to a token (within tolerance)
    OFF_SCALE = "off_scale"  # Value doesn't match any token


@dataclass
class TokenResolution:
    """Result of resolving a value to a token.

    Contains the original value, its normalized form, resolution status,
    and information about the matched or nearest token.
    """

    category: TokenCategory
    original_value: str
    normalized_value: str
    status: ResolutionStatus
    matched_token: str | None = None  # Token name if matched
    distance: float = 0.0  # Distance from nearest token
    nearest_token: str | None = None  # Nearest token even if off-scale
    suggestion: str | None = None  # Remediation suggestion

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "category": self.category.value,
            "original_value": self.original_value,
            "normalized_value": self.normalized_value,
            "status": self.status.value,
            "matched_token": self.matched_token,
            "distance": self.distance,
            "nearest_token": self.nearest_token,
            "suggestion": self.suggestion,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenResolution":
        """Create from dictionary."""
        return cls(
            category=TokenCategory(data["category"]),
            original_value=data["original_value"],
            normalized_value=data["normalized_value"],
            status=ResolutionStatus(data["status"]),
            matched_token=data.get("matched_token"),
            distance=data.get("distance", 0.0),
            nearest_token=data.get("nearest_token"),
            suggestion=data.get("suggestion"),
        )

    @property
    def is_on_scale(self) -> bool:
        """Check if value is on the design scale."""
        return self.status in (
            ResolutionStatus.EXACT_MATCH,
            ResolutionStatus.NEAR_MATCH,
        )


class TokenResolver:
    """Resolves CSS values to design system tokens.

    This is the main class for detecting token drift - values that don't
    align with the design system's defined tokens.
    """

    # Default tolerances for "near match" detection
    SPACING_TOLERANCE = 1.0  # 1px tolerance for spacing
    RADIUS_TOLERANCE = 0.5  # 0.5px tolerance for radius
    COLOR_TOLERANCE = 0.02  # 2% tolerance for color channels
    TYPOGRAPHY_TOLERANCE = 1.0  # 1px tolerance for font sizes

    # CSS properties categorization
    COLOR_PROPERTIES = frozenset(
        [
            "color",
            "background-color",
            "border-color",
            "outline-color",
            "fill",
            "stroke",
            "box-shadow",
            "text-shadow",
            "background",
            "border",
            "border-top-color",
            "border-right-color",
            "border-bottom-color",
            "border-left-color",
        ]
    )

    SPACING_PROPERTIES = frozenset(
        [
            "margin",
            "margin-top",
            "margin-right",
            "margin-bottom",
            "margin-left",
            "padding",
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
            "gap",
            "row-gap",
            "column-gap",
            "width",
            "height",
            "min-width",
            "min-height",
            "max-width",
            "max-height",
            "top",
            "right",
            "bottom",
            "left",
        ]
    )

    RADIUS_PROPERTIES = frozenset(
        [
            "border-radius",
            "border-top-left-radius",
            "border-top-right-radius",
            "border-bottom-right-radius",
            "border-bottom-left-radius",
        ]
    )

    TYPOGRAPHY_PROPERTIES = frozenset(
        [
            "font-size",
            "line-height",
        ]
    )

    SHADOW_PROPERTIES = frozenset(
        [
            "box-shadow",
            "text-shadow",
        ]
    )

    def __init__(
        self,
        token_set: TokenSet,
        spacing_tolerance: float | None = None,
        radius_tolerance: float | None = None,
        color_tolerance: float | None = None,
        typography_tolerance: float | None = None,
        base_font_size: float = 16.0,
    ):
        """Initialize the TokenResolver with a token set.

        Args:
            token_set: The design system tokens to resolve against.
            spacing_tolerance: Custom tolerance for spacing matching (default 1.0px).
            radius_tolerance: Custom tolerance for radius matching (default 0.5px).
            color_tolerance: Custom tolerance for color matching (default 0.02).
            typography_tolerance: Custom tolerance for typography matching (default 1.0px).
            base_font_size: Base font size for rem/em conversion (default 16.0px).
        """
        self.token_set = token_set
        self.base_font_size = base_font_size

        # Custom tolerances
        self.spacing_tolerance = (
            spacing_tolerance
            if spacing_tolerance is not None
            else self.SPACING_TOLERANCE
        )
        self.radius_tolerance = (
            radius_tolerance if radius_tolerance is not None else self.RADIUS_TOLERANCE
        )
        self.color_tolerance = (
            color_tolerance if color_tolerance is not None else self.COLOR_TOLERANCE
        )
        self.typography_tolerance = (
            typography_tolerance
            if typography_tolerance is not None
            else self.TYPOGRAPHY_TOLERANCE
        )

        # Build lookup structures
        self._color_lookup = self._build_color_lookup()

    def _build_color_lookup(self) -> dict[str, str]:
        """Build normalized color value to token name lookup."""
        return {token.value: token.name for token in self.token_set.colors.values()}

    def resolve(self, value: str, category: TokenCategory) -> TokenResolution:
        """Resolve a value to a token in the given category.

        Args:
            value: The CSS value to resolve.
            category: The token category to resolve against.

        Returns:
            TokenResolution with match status and details.
        """
        if category == TokenCategory.COLOR:
            return self.resolve_color(value)
        elif category == TokenCategory.SPACING:
            return self.resolve_spacing(value)
        elif category == TokenCategory.RADIUS:
            return self.resolve_radius(value)
        elif category == TokenCategory.TYPOGRAPHY:
            return self.resolve_typography(value)
        elif category == TokenCategory.SHADOW:
            return self.resolve_shadow(value)
        else:
            raise ValueError(f"Unknown category: {category}")

    def resolve_color(self, value: str) -> TokenResolution:
        """Resolve color value to token.

        Args:
            value: A color value (hex, rgb, rgba, hsl, hsla).

        Returns:
            TokenResolution with color matching details.
        """
        normalized = ColorToken.normalize_color(value)

        # Check for exact match
        if normalized in self._color_lookup:
            return TokenResolution(
                category=TokenCategory.COLOR,
                original_value=value,
                normalized_value=normalized,
                status=ResolutionStatus.EXACT_MATCH,
                matched_token=self._color_lookup[normalized],
                distance=0.0,
            )

        # Find nearest color
        nearest_token, distance = self._find_nearest_color(normalized)

        if nearest_token and distance <= self.color_tolerance:
            return TokenResolution(
                category=TokenCategory.COLOR,
                original_value=value,
                normalized_value=normalized,
                status=ResolutionStatus.NEAR_MATCH,
                matched_token=nearest_token,
                distance=distance,
                nearest_token=nearest_token,
            )

        return TokenResolution(
            category=TokenCategory.COLOR,
            original_value=value,
            normalized_value=normalized,
            status=ResolutionStatus.OFF_SCALE,
            distance=distance,
            nearest_token=nearest_token,
            suggestion=(
                f"Consider using token '{nearest_token}' instead"
                if nearest_token
                else None
            ),
        )

    def resolve_spacing(self, value: str) -> TokenResolution:
        """Resolve spacing value to token.

        Args:
            value: A spacing value (px, rem, em, or unitless).

        Returns:
            TokenResolution with spacing matching details.
        """
        px_value = SpacingToken.normalize_length(value, self.base_font_size)
        normalized_value = (
            f"{px_value}px" if px_value != int(px_value) else f"{int(px_value)}px"
        )

        # Check if on scale
        token_name, distance = self.token_set.find_nearest_spacing(px_value)

        if distance == 0:
            return TokenResolution(
                category=TokenCategory.SPACING,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.EXACT_MATCH,
                matched_token=token_name,
                distance=0.0,
            )

        if token_name and distance <= self.spacing_tolerance:
            return TokenResolution(
                category=TokenCategory.SPACING,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.NEAR_MATCH,
                matched_token=token_name,
                distance=distance,
                nearest_token=token_name,
            )

        suggestion = None
        if token_name and token_name in self.token_set.spacing:
            token_value = self.token_set.spacing[token_name].value
            suggestion = (
                f"Consider using spacing token '{token_name}' ({token_value}px) instead"
            )

        return TokenResolution(
            category=TokenCategory.SPACING,
            original_value=value,
            normalized_value=normalized_value,
            status=ResolutionStatus.OFF_SCALE,
            distance=distance,
            nearest_token=token_name,
            suggestion=suggestion,
        )

    def resolve_radius(self, value: str) -> TokenResolution:
        """Resolve border-radius value to token.

        Args:
            value: A radius value (px, rem, em, or unitless).

        Returns:
            TokenResolution with radius matching details.
        """
        px_value = SpacingToken.normalize_length(value, self.base_font_size)
        normalized_value = (
            f"{px_value}px" if px_value != int(px_value) else f"{int(px_value)}px"
        )

        token_name, distance = self.token_set.find_nearest_radius(px_value)

        if distance == 0:
            return TokenResolution(
                category=TokenCategory.RADIUS,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.EXACT_MATCH,
                matched_token=token_name,
                distance=0.0,
            )

        if token_name and distance <= self.radius_tolerance:
            return TokenResolution(
                category=TokenCategory.RADIUS,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.NEAR_MATCH,
                matched_token=token_name,
                distance=distance,
                nearest_token=token_name,
            )

        suggestion = None
        if token_name and token_name in self.token_set.radii:
            token_value = self.token_set.radii[token_name].value
            suggestion = (
                f"Consider using radius token '{token_name}' ({token_value}px) instead"
            )

        return TokenResolution(
            category=TokenCategory.RADIUS,
            original_value=value,
            normalized_value=normalized_value,
            status=ResolutionStatus.OFF_SCALE,
            distance=distance,
            nearest_token=token_name,
            suggestion=suggestion,
        )

    def resolve_typography(self, value: str) -> TokenResolution:
        """Resolve font-size value to typography token.

        Args:
            value: A font-size value (px, rem, em, or unitless).

        Returns:
            TokenResolution with typography matching details.
        """
        px_value = SpacingToken.normalize_length(value, self.base_font_size)
        normalized_value = (
            f"{px_value}px" if px_value != int(px_value) else f"{int(px_value)}px"
        )

        # Find nearest typography token by size
        nearest_token = None
        min_distance = float("inf")

        for name, token in self.token_set.typography.items():
            distance = abs(token.size - px_value)
            if distance < min_distance:
                min_distance = distance
                nearest_token = name

        if min_distance == 0:
            return TokenResolution(
                category=TokenCategory.TYPOGRAPHY,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.EXACT_MATCH,
                matched_token=nearest_token,
                distance=0.0,
            )

        if nearest_token and min_distance <= self.typography_tolerance:
            return TokenResolution(
                category=TokenCategory.TYPOGRAPHY,
                original_value=value,
                normalized_value=normalized_value,
                status=ResolutionStatus.NEAR_MATCH,
                matched_token=nearest_token,
                distance=min_distance,
                nearest_token=nearest_token,
            )

        suggestion = None
        if nearest_token:
            suggestion = f"Consider using typography token '{nearest_token}'"

        return TokenResolution(
            category=TokenCategory.TYPOGRAPHY,
            original_value=value,
            normalized_value=normalized_value,
            status=ResolutionStatus.OFF_SCALE,
            distance=min_distance,
            nearest_token=nearest_token,
            suggestion=suggestion,
        )

    def resolve_shadow(self, value: str) -> TokenResolution:
        """Resolve box-shadow value to token.

        Shadow matching uses exact string matching since shadows are complex
        multi-value properties.

        Args:
            value: A box-shadow CSS value.

        Returns:
            TokenResolution with shadow matching details.
        """
        normalized = value.strip().lower()

        for name, token in self.token_set.shadows.items():
            # Check both the value and name for matching
            if token.value.lower() == normalized or token.name.lower() == normalized:
                return TokenResolution(
                    category=TokenCategory.SHADOW,
                    original_value=value,
                    normalized_value=normalized,
                    status=ResolutionStatus.EXACT_MATCH,
                    matched_token=name,
                    distance=0.0,
                )

        # No exact match - report as off-scale
        return TokenResolution(
            category=TokenCategory.SHADOW,
            original_value=value,
            normalized_value=normalized,
            status=ResolutionStatus.OFF_SCALE,
            suggestion="Consider using a defined shadow token",
        )

    def _find_nearest_color(self, normalized: str) -> tuple[str | None, float]:
        """Find nearest color token by color distance.

        Uses Euclidean distance in RGBA color space.

        Args:
            normalized: Normalized color value (#RRGGBBAA format).

        Returns:
            Tuple of (token_name, distance) where distance is normalized to 0-1.
        """
        if not self.token_set.colors:
            return None, float("inf")

        # Parse the normalized color
        try:
            r1, g1, b1, a1 = self._parse_rgba(normalized)
        except ValueError:
            return None, float("inf")

        nearest = None
        min_distance = float("inf")

        for name, token in self.token_set.colors.items():
            try:
                r2, g2, b2, a2 = self._parse_rgba(token.value)
                # Euclidean distance in RGBA space
                distance = (
                    (r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2 + (a1 - a2) ** 2
                ) ** 0.5
                # Normalize to 0-1 range (max possible distance is sqrt(4 * 255^2) = 510)
                distance = distance / 510.0

                if distance < min_distance:
                    min_distance = distance
                    nearest = name
            except ValueError:
                continue

        return nearest, min_distance

    def _parse_rgba(self, hex_color: str) -> tuple[int, int, int, int]:
        """Parse #RRGGBBAA to (r, g, b, a) tuple.

        Args:
            hex_color: Color in #RRGGBB or #RRGGBBAA format.

        Returns:
            Tuple of (r, g, b, a) values as integers 0-255.

        Raises:
            ValueError: If the color format is invalid.
        """
        hex_color = hex_color.lstrip("#").upper()
        if len(hex_color) == 6:
            hex_color += "FF"  # Add full opacity
        if len(hex_color) != 8:
            raise ValueError(f"Invalid color format: {hex_color}")

        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        a = int(hex_color[6:8], 16)
        return r, g, b, a

    def categorize_property(self, prop: str) -> TokenCategory | None:
        """Categorize a CSS property for token resolution.

        Args:
            prop: A CSS property name.

        Returns:
            TokenCategory if the property should be resolved, None otherwise.
        """
        prop = prop.lower().strip()

        # Check shadow first (it overlaps with color for box-shadow)
        if prop in self.SHADOW_PROPERTIES:
            return TokenCategory.SHADOW

        if prop in self.COLOR_PROPERTIES or "color" in prop:
            return TokenCategory.COLOR

        if prop in self.SPACING_PROPERTIES:
            return TokenCategory.SPACING

        if prop in self.RADIUS_PROPERTIES:
            return TokenCategory.RADIUS

        if prop in self.TYPOGRAPHY_PROPERTIES:
            return TokenCategory.TYPOGRAPHY

        return None

    def resolve_declarations(
        self,
        declarations: dict[str, str],
    ) -> dict[str, TokenResolution]:
        """Resolve all declarations in a style block.

        Args:
            declarations: Dictionary of CSS property -> value pairs.

        Returns:
            Dictionary of property -> TokenResolution for resolvable properties.
        """
        results = {}

        for prop, value in declarations.items():
            category = self.categorize_property(prop)
            if category:
                results[prop] = self.resolve(value, category)

        return results

    def get_off_scale_declarations(
        self,
        declarations: dict[str, str],
    ) -> list[TokenResolution]:
        """Get all off-scale declarations from a style block.

        Convenience method for quickly finding token drift issues.

        Args:
            declarations: Dictionary of CSS property -> value pairs.

        Returns:
            List of TokenResolution objects for off-scale values only.
        """
        resolutions = self.resolve_declarations(declarations)
        return [
            r for r in resolutions.values() if r.status == ResolutionStatus.OFF_SCALE
        ]
