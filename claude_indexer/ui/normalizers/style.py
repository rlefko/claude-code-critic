"""Style normalizer for CSS duplicate detection.

This module provides functionality to normalize CSS styles for accurate
comparison and duplicate detection. It canonicalizes colors, lengths,
and property ordering to enable hash-based similarity detection.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from ..tokens import ColorToken, SpacingToken
from .hashing import compute_simhash


@dataclass
class NormalizedStyle:
    """Normalized style with hashes for comparison.

    Contains the normalized declarations along with exact and near hashes
    for duplicate detection.
    """

    declarations: dict[str, str]  # Sorted, normalized property: value
    exact_hash: str  # SHA256 of canonical representation
    near_hash: str  # SimHash for near-duplicate detection
    original_declarations: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "declarations": self.declarations,
            "exact_hash": self.exact_hash,
            "near_hash": self.near_hash,
            "original_declarations": self.original_declarations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedStyle":
        """Create from dictionary."""
        return cls(
            declarations=data["declarations"],
            exact_hash=data["exact_hash"],
            near_hash=data["near_hash"],
            original_declarations=data.get("original_declarations", {}),
        )

    def is_exact_duplicate(self, other: "NormalizedStyle") -> bool:
        """Check if this style is an exact duplicate of another."""
        return self.exact_hash == other.exact_hash

    def similarity(self, other: "NormalizedStyle") -> float:
        """Compute similarity with another normalized style."""
        from .hashing import simhash_similarity

        return simhash_similarity(self.near_hash, other.near_hash)


class StyleNormalizer:
    """Normalizes CSS styles for consistent comparison.

    Handles color normalization, length conversion, property sorting,
    and hash generation for duplicate detection.
    """

    # Properties that should have their values normalized as colors
    COLOR_PROPERTIES = frozenset(
        [
            "color",
            "background-color",
            "border-color",
            "outline-color",
            "fill",
            "stroke",
            "border-top-color",
            "border-right-color",
            "border-bottom-color",
            "border-left-color",
            "text-decoration-color",
            "caret-color",
            "column-rule-color",
        ]
    )

    # Properties that should have their values normalized as lengths
    LENGTH_PROPERTIES = frozenset(
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
            "width",
            "height",
            "min-width",
            "min-height",
            "max-width",
            "max-height",
            "gap",
            "row-gap",
            "column-gap",
            "border-width",
            "border-top-width",
            "border-right-width",
            "border-bottom-width",
            "border-left-width",
            "outline-width",
            "font-size",
            "line-height",
            "letter-spacing",
            "word-spacing",
            "border-radius",
            "border-top-left-radius",
            "border-top-right-radius",
            "border-bottom-right-radius",
            "border-bottom-left-radius",
            "top",
            "right",
            "bottom",
            "left",
            "inset",
        ]
    )

    # Properties that can be collapsed to shorthands
    SHORTHAND_GROUPS = {
        "margin": [
            "margin-top",
            "margin-right",
            "margin-bottom",
            "margin-left",
        ],
        "padding": [
            "padding-top",
            "padding-right",
            "padding-bottom",
            "padding-left",
        ],
        "border-radius": [
            "border-top-left-radius",
            "border-top-right-radius",
            "border-bottom-right-radius",
            "border-bottom-left-radius",
        ],
        "border-width": [
            "border-top-width",
            "border-right-width",
            "border-bottom-width",
            "border-left-width",
        ],
        "border-color": [
            "border-top-color",
            "border-right-color",
            "border-bottom-color",
            "border-left-color",
        ],
    }

    def __init__(self, base_font_size: float = 16.0, collapse_shorthands: bool = True):
        """Initialize the style normalizer.

        Args:
            base_font_size: Base font size for rem/em conversion.
            collapse_shorthands: Whether to collapse longhands to shorthands.
        """
        self.base_font_size = base_font_size
        self.collapse_shorthands = collapse_shorthands

    def normalize(self, declarations: dict[str, str]) -> NormalizedStyle:
        """Normalize declarations and compute hashes.

        Args:
            declarations: Dictionary of CSS property -> value pairs.

        Returns:
            NormalizedStyle with normalized declarations and hashes.
        """
        # Step 1: Normalize individual values
        normalized = {}
        for prop, value in declarations.items():
            norm_prop = self._normalize_property_name(prop)
            norm_value = self._normalize_value(norm_prop, value)
            normalized[norm_prop] = norm_value

        # Step 2: Collapse shorthands (optional, conservative)
        if self.collapse_shorthands:
            normalized = self._collapse_shorthands(normalized)

        # Step 3: Sort properties for deterministic ordering
        sorted_decls = dict(sorted(normalized.items()))

        # Step 4: Compute hashes
        exact_hash = self._compute_exact_hash(sorted_decls)
        near_hash = self._compute_near_hash(sorted_decls)

        return NormalizedStyle(
            declarations=sorted_decls,
            exact_hash=exact_hash,
            near_hash=near_hash,
            original_declarations=declarations,
        )

    def _normalize_property_name(self, prop: str) -> str:
        """Normalize property name (lowercase, strip whitespace)."""
        return prop.lower().strip()

    def _normalize_value(self, prop: str, value: str) -> str:
        """Normalize property value based on property type.

        Args:
            prop: Normalized property name.
            value: Original property value.

        Returns:
            Normalized value string.
        """
        value = value.strip()

        # Handle special keywords that shouldn't be normalized
        if value.lower() in (
            "inherit",
            "initial",
            "unset",
            "revert",
            "auto",
            "none",
        ):
            return value.lower()

        # Normalize colors
        if prop in self.COLOR_PROPERTIES or self._looks_like_color(value):
            return self._normalize_color(value)

        # Normalize lengths
        if prop in self.LENGTH_PROPERTIES or self._looks_like_length(value):
            return self._normalize_length(value)

        # Default: lowercase and normalize whitespace
        return re.sub(r"\s+", " ", value.lower())

    def _looks_like_color(self, value: str) -> bool:
        """Check if a value looks like a color."""
        value = value.strip().lower()
        return (
            value.startswith("#") or value.startswith("rgb") or value.startswith("hsl")
        )

    def _looks_like_length(self, value: str) -> bool:
        """Check if a value looks like a length."""
        value = value.strip().lower()
        return bool(re.match(r"^-?[\d.]+\s*(px|rem|em|%|vh|vw|vmin|vmax)?$", value))

    def _normalize_color(self, value: str) -> str:
        """Normalize color to canonical RGBA hex format."""
        try:
            return ColorToken.normalize_color(value)
        except Exception:
            return value.lower()

    def _normalize_length(self, value: str) -> str:
        """Normalize length value to pixels."""
        value = value.strip().lower()

        # Handle percentage and viewport units - keep as-is
        if value.endswith("%") or any(
            value.endswith(unit) for unit in ("vh", "vw", "vmin", "vmax")
        ):
            return value

        # Convert to pixels
        try:
            px_value = SpacingToken.normalize_length(value, self.base_font_size)
            if px_value == 0:
                return "0"
            # Return as integer if whole number
            if px_value == int(px_value):
                return f"{int(px_value)}px"
            return f"{px_value}px"
        except Exception:
            return value

    def _collapse_shorthands(self, declarations: dict[str, str]) -> dict[str, str]:
        """Collapse longhand properties to shorthands where possible.

        Only collapses when all longhands are present and have the same value.
        This is conservative to avoid changing semantics.

        Args:
            declarations: Dictionary of normalized declarations.

        Returns:
            Dictionary with collapsed shorthands where applicable.
        """
        result = declarations.copy()

        for shorthand, longhands in self.SHORTHAND_GROUPS.items():
            # Only collapse if ALL longhands are present
            if all(lh in result for lh in longhands):
                values = [result[lh] for lh in longhands]

                # Only collapse if all values are the same (simple case)
                if len(set(values)) == 1:
                    result[shorthand] = values[0]
                    for lh in longhands:
                        del result[lh]

        return result

    def _compute_exact_hash(self, declarations: dict[str, str]) -> str:
        """Compute SHA256 hash of normalized declarations.

        Args:
            declarations: Sorted, normalized declarations.

        Returns:
            SHA256 hex digest.
        """
        canonical = ";".join(f"{k}:{v}" for k, v in sorted(declarations.items()))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _compute_near_hash(self, declarations: dict[str, str]) -> str:
        """Compute SimHash for near-duplicate detection.

        Args:
            declarations: Sorted, normalized declarations.

        Returns:
            SimHash hex string.
        """
        # Create feature set from declarations
        features = [f"{k}={v}" for k, v in declarations.items()]
        return compute_simhash(features)

    def compute_similarity(
        self, style1: NormalizedStyle, style2: NormalizedStyle
    ) -> float:
        """Compute similarity between two normalized styles.

        Args:
            style1: First normalized style.
            style2: Second normalized style.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        from .hashing import simhash_similarity

        return simhash_similarity(style1.near_hash, style2.near_hash)

    def are_near_duplicates(
        self,
        style1: NormalizedStyle,
        style2: NormalizedStyle,
        threshold: float = 0.9,
    ) -> bool:
        """Check if two styles are near-duplicates.

        Args:
            style1: First normalized style.
            style2: Second normalized style.
            threshold: Similarity threshold for near-duplicate (default 0.9).

        Returns:
            True if styles are near-duplicates.
        """
        if style1.exact_hash == style2.exact_hash:
            return True
        return self.compute_similarity(style1, style2) >= threshold

    def normalize_declaration_list(
        self,
        styles: list[dict[str, str]],
    ) -> list[NormalizedStyle]:
        """Normalize a list of style declarations.

        Args:
            styles: List of declaration dictionaries.

        Returns:
            List of normalized styles.
        """
        return [self.normalize(s) for s in styles]

    def find_duplicates(
        self,
        styles: list[NormalizedStyle],
    ) -> list[tuple[int, int]]:
        """Find exact duplicate pairs in a list of normalized styles.

        Args:
            styles: List of normalized styles.

        Returns:
            List of (index1, index2) pairs that are exact duplicates.
        """
        duplicates = []
        seen: dict[str, int] = {}

        for i, style in enumerate(styles):
            if style.exact_hash in seen:
                duplicates.append((seen[style.exact_hash], i))
            else:
                seen[style.exact_hash] = i

        return duplicates

    def find_near_duplicates(
        self,
        styles: list[NormalizedStyle],
        threshold: float = 0.9,
    ) -> list[tuple[int, int, float]]:
        """Find near-duplicate pairs in a list of normalized styles.

        Args:
            styles: List of normalized styles.
            threshold: Similarity threshold for near-duplicate.

        Returns:
            List of (index1, index2, similarity) tuples.
        """
        near_duplicates = []

        for i in range(len(styles)):
            for j in range(i + 1, len(styles)):
                # Skip exact duplicates
                if styles[i].exact_hash == styles[j].exact_hash:
                    continue

                similarity = self.compute_similarity(styles[i], styles[j])
                if similarity >= threshold:
                    near_duplicates.append((i, j, similarity))

        return near_duplicates
