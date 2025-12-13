"""Design token models for UI consistency checking.

This module defines data structures for design system tokens including
colors, spacing, typography, radii, and shadows.
"""

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ColorToken:
    """A design token representing a color value.

    Colors are stored in canonical RGBA hex format (#RRGGBBAA or #RRGGBB)
    for consistent comparison.
    """

    name: str  # Token name, e.g., "primary-500" or "brand-blue"
    value: str  # Canonical RGBA hex, e.g., "#3B82F6FF"
    original_value: str | None = None  # Original value before normalization
    category: str | None = None  # e.g., "primary", "neutral", "semantic"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "original_value": self.original_value,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColorToken":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
            original_value=data.get("original_value"),
            category=data.get("category"),
        )

    @staticmethod
    def normalize_color(value: str) -> str:
        """Normalize a color value to canonical RGBA hex format.

        Supports: #RGB, #RRGGBB, #RRGGBBAA, rgb(), rgba(), hsl(), hsla()
        """
        value = value.strip().lower()

        # Already in hex format
        if value.startswith("#"):
            # #RGB -> #RRGGBB
            if len(value) == 4:
                return f"#{value[1]*2}{value[2]*2}{value[3]*2}ff".upper()
            # #RRGGBB -> #RRGGBBFF
            if len(value) == 7:
                return f"{value}ff".upper()
            # #RRGGBBAA already canonical
            if len(value) == 9:
                return value.upper()

        # rgb(r, g, b) or rgba(r, g, b, a)
        rgb_match = re.match(
            r"rgba?\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*([\d.]+))?\s*\)",
            value,
        )
        if rgb_match:
            r, g, b = (
                int(rgb_match.group(1)),
                int(rgb_match.group(2)),
                int(rgb_match.group(3)),
            )
            a = float(rgb_match.group(4)) if rgb_match.group(4) else 1.0
            a_hex = format(int(a * 255), "02X")
            return f"#{r:02X}{g:02X}{b:02X}{a_hex}"

        # hsl(h, s%, l%) or hsla(h, s%, l%, a)
        hsl_match = re.match(
            r"hsla?\s*\(\s*(\d+)\s*,\s*(\d+)%\s*,\s*(\d+)%\s*(?:,\s*([\d.]+))?\s*\)",
            value,
        )
        if hsl_match:
            hue, sat, light = (
                int(hsl_match.group(1)),
                int(hsl_match.group(2)) / 100,
                int(hsl_match.group(3)) / 100,
            )
            a = float(hsl_match.group(4)) if hsl_match.group(4) else 1.0

            # HSL to RGB conversion
            c = (1 - abs(2 * light - 1)) * sat
            x = c * (1 - abs((hue / 60) % 2 - 1))
            m = light - c / 2

            if hue < 60:
                r1, g1, b1 = c, x, 0
            elif hue < 120:
                r1, g1, b1 = x, c, 0
            elif hue < 180:
                r1, g1, b1 = 0, c, x
            elif hue < 240:
                r1, g1, b1 = 0, x, c
            elif hue < 300:
                r1, g1, b1 = x, 0, c
            else:
                r1, g1, b1 = c, 0, x

            r, g, b = int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255)
            a_hex = format(int(a * 255), "02X")
            return f"#{r:02X}{g:02X}{b:02X}{a_hex}"

        # Return original if can't parse
        return value.upper()


@dataclass
class SpacingToken:
    """A design token representing a spacing value.

    Spacing values are stored in pixels for consistent comparison.
    """

    name: str  # Token name, e.g., "4" or "md"
    value: float  # Value in pixels
    original_value: str | None = None  # Original value, e.g., "1rem"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "value": self.value,
            "original_value": self.original_value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SpacingToken":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
            original_value=data.get("original_value"),
        )

    @staticmethod
    def normalize_length(value: str, base_font_size: float = 16.0) -> float:
        """Normalize a length value to pixels.

        Supports: px, rem, em (relative to base_font_size)
        """
        value = value.strip().lower()

        # Already in pixels
        px_match = re.match(r"([\d.]+)\s*px", value)
        if px_match:
            return float(px_match.group(1))

        # rem units
        rem_match = re.match(r"([\d.]+)\s*rem", value)
        if rem_match:
            return float(rem_match.group(1)) * base_font_size

        # em units (treated same as rem for token purposes)
        em_match = re.match(r"([\d.]+)\s*em", value)
        if em_match:
            return float(em_match.group(1)) * base_font_size

        # Plain number (assume pixels)
        try:
            return float(value)
        except ValueError:
            return 0.0


@dataclass
class RadiusToken:
    """A design token representing a border radius value.

    Radius values are stored in pixels for consistent comparison.
    """

    name: str  # Token name, e.g., "sm" or "lg"
    value: float  # Value in pixels

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RadiusToken":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
        )


@dataclass
class TypographyToken:
    """A design token representing typography settings.

    Combines font size, line height, weight, and family for
    consistent typography scale enforcement.
    """

    name: str  # Token name, e.g., "heading-1" or "body-sm"
    size: float  # Font size in pixels
    line_height: float | None = None  # Line height in pixels or unitless ratio
    weight: int | str | None = None  # Font weight (400, 700, "bold")
    family: str | None = None  # Font family
    letter_spacing: float | None = None  # Letter spacing in pixels or em

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "size": self.size,
            "line_height": self.line_height,
            "weight": self.weight,
            "family": self.family,
            "letter_spacing": self.letter_spacing,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TypographyToken":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            size=data["size"],
            line_height=data.get("line_height"),
            weight=data.get("weight"),
            family=data.get("family"),
            letter_spacing=data.get("letter_spacing"),
        )


@dataclass
class ShadowToken:
    """A design token representing a box shadow value.

    Shadows are stored as CSS shadow strings for flexibility.
    """

    name: str  # Token name, e.g., "sm" or "elevated"
    value: str  # CSS shadow value, e.g., "0 1px 2px rgba(0,0,0,0.1)"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShadowToken":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            value=data["value"],
        )


@dataclass
class TokenSet:
    """Aggregated design tokens from all configured sources.

    This is the unified token set used by the TokenResolver to
    determine if values are on-scale or off-scale.
    """

    colors: dict[str, ColorToken] = field(default_factory=dict)
    spacing: dict[str, SpacingToken] = field(default_factory=dict)
    radii: dict[str, RadiusToken] = field(default_factory=dict)
    typography: dict[str, TypographyToken] = field(default_factory=dict)
    shadows: dict[str, ShadowToken] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "colors": {k: v.to_dict() for k, v in self.colors.items()},
            "spacing": {k: v.to_dict() for k, v in self.spacing.items()},
            "radii": {k: v.to_dict() for k, v in self.radii.items()},
            "typography": {k: v.to_dict() for k, v in self.typography.items()},
            "shadows": {k: v.to_dict() for k, v in self.shadows.items()},
            "source_files": self.source_files,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenSet":
        """Create from dictionary."""
        return cls(
            colors={
                k: ColorToken.from_dict(v) for k, v in data.get("colors", {}).items()
            },
            spacing={
                k: SpacingToken.from_dict(v) for k, v in data.get("spacing", {}).items()
            },
            radii={
                k: RadiusToken.from_dict(v) for k, v in data.get("radii", {}).items()
            },
            typography={
                k: TypographyToken.from_dict(v)
                for k, v in data.get("typography", {}).items()
            },
            shadows={
                k: ShadowToken.from_dict(v) for k, v in data.get("shadows", {}).items()
            },
            source_files=data.get("source_files", []),
        )

    def merge(self, other: "TokenSet") -> "TokenSet":
        """Merge another TokenSet into this one.

        Later values override earlier ones for the same key.
        """
        return TokenSet(
            colors={**self.colors, **other.colors},
            spacing={**self.spacing, **other.spacing},
            radii={**self.radii, **other.radii},
            typography={**self.typography, **other.typography},
            shadows={**self.shadows, **other.shadows},
            source_files=self.source_files + other.source_files,
        )

    def get_spacing_scale(self) -> list[float]:
        """Get sorted list of spacing values for scale validation."""
        return sorted({t.value for t in self.spacing.values()})

    def get_radius_scale(self) -> list[float]:
        """Get sorted list of radius values for scale validation."""
        return sorted({t.value for t in self.radii.values()})

    def get_color_values(self) -> set[str]:
        """Get set of canonical color values for token validation."""
        return {t.value for t in self.colors.values()}

    def find_nearest_spacing(self, value: float) -> tuple[str | None, float]:
        """Find the nearest spacing token to a value.

        Returns (token_name, distance) where distance is 0 if exact match.
        """
        if not self.spacing:
            return None, value

        min_distance = float("inf")
        nearest_name = None

        for name, token in self.spacing.items():
            distance = abs(token.value - value)
            if distance < min_distance:
                min_distance = distance
                nearest_name = name

        return nearest_name, min_distance

    def find_nearest_radius(self, value: float) -> tuple[str | None, float]:
        """Find the nearest radius token to a value.

        Returns (token_name, distance) where distance is 0 if exact match.
        """
        if not self.radii:
            return None, value

        min_distance = float("inf")
        nearest_name = None

        for name, token in self.radii.items():
            distance = abs(token.value - value)
            if distance < min_distance:
                min_distance = distance
                nearest_name = name

        return nearest_name, min_distance

    def is_color_on_scale(self, value: str) -> bool:
        """Check if a color value matches any token (after normalization)."""
        normalized = ColorToken.normalize_color(value)
        return normalized in self.get_color_values()

    def is_spacing_on_scale(self, value: float, tolerance: float = 0.5) -> bool:
        """Check if a spacing value is within tolerance of any token."""
        _, distance = self.find_nearest_spacing(value)
        return distance <= tolerance

    def is_radius_on_scale(self, value: float, tolerance: float = 0.5) -> bool:
        """Check if a radius value is within tolerance of any token."""
        _, distance = self.find_nearest_radius(value)
        return distance <= tolerance

    @property
    def total_tokens(self) -> int:
        """Total number of tokens across all categories."""
        return (
            len(self.colors)
            + len(self.spacing)
            + len(self.radii)
            + len(self.typography)
            + len(self.shadows)
        )
