"""Computed style capture from rendered elements.

Captures key visual properties and normalizes for comparison.
"""

from dataclasses import dataclass, field
from typing import Any

try:
    from playwright.async_api import ElementHandle, Page

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    ElementHandle = None
    Page = None

from ..normalizers.style import StyleNormalizer


@dataclass
class CapturedStyles:
    """Captured computed styles for an element."""

    typography: dict[str, str] = field(default_factory=dict)
    spacing: dict[str, str] = field(default_factory=dict)
    shape: dict[str, str] = field(default_factory=dict)
    elevation: dict[str, str] = field(default_factory=dict)
    background: dict[str, str] = field(default_factory=dict)
    interaction: dict[str, str] = field(default_factory=dict)
    layout: dict[str, str] = field(default_factory=dict)

    def to_flat_dict(self) -> dict[str, str]:
        """Flatten all style categories into single dict."""
        result = {}
        result.update(self.typography)
        result.update(self.spacing)
        result.update(self.shape)
        result.update(self.elevation)
        result.update(self.background)
        result.update(self.interaction)
        result.update(self.layout)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "typography": self.typography,
            "spacing": self.spacing,
            "shape": self.shape,
            "elevation": self.elevation,
            "background": self.background,
            "interaction": self.interaction,
            "layout": self.layout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CapturedStyles":
        """Create from dictionary."""
        return cls(
            typography=data.get("typography", {}),
            spacing=data.get("spacing", {}),
            shape=data.get("shape", {}),
            elevation=data.get("elevation", {}),
            background=data.get("background", {}),
            interaction=data.get("interaction", {}),
            layout=data.get("layout", {}),
        )

    def diff(self, other: "CapturedStyles") -> dict[str, tuple[str, str]]:
        """Compute style differences with another CapturedStyles.

        Args:
            other: Another CapturedStyles to compare with.

        Returns:
            Dict of property -> (self_value, other_value) for differences.
        """
        self_flat = self.to_flat_dict()
        other_flat = other.to_flat_dict()

        differences: dict[str, tuple[str, str]] = {}

        all_keys = set(self_flat.keys()) | set(other_flat.keys())
        for key in all_keys:
            self_val = self_flat.get(key, "")
            other_val = other_flat.get(key, "")
            if self_val != other_val:
                differences[key] = (self_val, other_val)

        return differences


class ComputedStyleCapture:
    """Captures and normalizes computed styles from elements.

    Focuses on high-signal properties that affect visual consistency:
    - Typography: font-family, size, weight, line-height, color
    - Spacing: padding, margin, gap
    - Shape: border, border-radius
    - Elevation: box-shadow
    - Backgrounds: background-color
    - Interaction: cursor, outline, focus ring
    - Layout: display, flex/grid properties
    """

    # Properties to capture per category
    TYPOGRAPHY_PROPS = [
        "font-family",
        "font-size",
        "font-weight",
        "line-height",
        "color",
        "text-align",
        "text-decoration",
        "letter-spacing",
    ]

    SPACING_PROPS = [
        "padding-top",
        "padding-right",
        "padding-bottom",
        "padding-left",
        "margin-top",
        "margin-right",
        "margin-bottom",
        "margin-left",
        "gap",
        "row-gap",
        "column-gap",
    ]

    SHAPE_PROPS = [
        "border-width",
        "border-style",
        "border-color",
        "border-top-left-radius",
        "border-top-right-radius",
        "border-bottom-right-radius",
        "border-bottom-left-radius",
    ]

    ELEVATION_PROPS = [
        "box-shadow",
    ]

    BACKGROUND_PROPS = [
        "background-color",
        "background-image",
    ]

    INTERACTION_PROPS = [
        "cursor",
        "outline-width",
        "outline-style",
        "outline-color",
        "outline-offset",
    ]

    LAYOUT_PROPS = [
        "display",
        "flex-direction",
        "justify-content",
        "align-items",
        "flex-wrap",
        "grid-template-columns",
        "grid-template-rows",
        "position",
        "width",
        "height",
        "min-width",
        "min-height",
        "max-width",
        "max-height",
    ]

    def __init__(
        self,
        normalizer: StyleNormalizer | None = None,
        normalize_values: bool = True,
    ):
        """Initialize style capture.

        Args:
            normalizer: StyleNormalizer instance for value normalization.
            normalize_values: Whether to normalize captured values.
        """
        self.normalizer = normalizer or StyleNormalizer()
        self.normalize_values = normalize_values
        self._all_props = (
            self.TYPOGRAPHY_PROPS
            + self.SPACING_PROPS
            + self.SHAPE_PROPS
            + self.ELEVATION_PROPS
            + self.BACKGROUND_PROPS
            + self.INTERACTION_PROPS
            + self.LAYOUT_PROPS
        )

    async def capture(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles:
        """Capture computed styles from element.

        Performance target: <50ms per element.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page (for evaluate context).

        Returns:
            CapturedStyles instance with categorized properties.
        """
        # Get all computed styles in a single evaluate call
        raw_styles = await element.evaluate(
            """(el, props) => {
                const computed = window.getComputedStyle(el);
                const result = {};
                for (const prop of props) {
                    result[prop] = computed.getPropertyValue(prop);
                }
                return result;
            }""",
            self._all_props,
        )

        # Categorize and normalize
        return self._categorize_styles(raw_styles)

    async def capture_batch(
        self,
        elements: list[tuple["ElementHandle", "Page"]],
    ) -> list[CapturedStyles]:
        """Capture styles from multiple elements efficiently.

        Args:
            elements: List of (ElementHandle, Page) tuples.

        Returns:
            List of CapturedStyles in same order.
        """
        results = []
        for element, page in elements:
            try:
                styles = await self.capture(element, page)
                results.append(styles)
            except Exception:
                # Return empty styles on failure
                results.append(CapturedStyles())
        return results

    def _categorize_styles(
        self,
        raw_styles: dict[str, str],
    ) -> CapturedStyles:
        """Categorize raw styles into typed structure.

        Args:
            raw_styles: Dict of CSS property -> value.

        Returns:
            CapturedStyles with categorized properties.
        """
        typography = {}
        spacing = {}
        shape = {}
        elevation = {}
        background = {}
        interaction = {}
        layout = {}

        for prop, value in raw_styles.items():
            # Normalize value if enabled
            if self.normalize_values and value:
                value = self._normalize_value(prop, value)

            if prop in self.TYPOGRAPHY_PROPS:
                typography[prop] = value
            elif prop in self.SPACING_PROPS:
                spacing[prop] = value
            elif prop in self.SHAPE_PROPS:
                shape[prop] = value
            elif prop in self.ELEVATION_PROPS:
                elevation[prop] = value
            elif prop in self.BACKGROUND_PROPS:
                background[prop] = value
            elif prop in self.INTERACTION_PROPS:
                interaction[prop] = value
            elif prop in self.LAYOUT_PROPS:
                layout[prop] = value

        return CapturedStyles(
            typography=typography,
            spacing=spacing,
            shape=shape,
            elevation=elevation,
            background=background,
            interaction=interaction,
            layout=layout,
        )

    def _normalize_value(self, prop: str, value: str) -> str:
        """Normalize a single CSS value.

        Args:
            prop: CSS property name.
            value: Raw CSS value.

        Returns:
            Normalized value.
        """
        # Use StyleNormalizer for known property types
        if prop in self.normalizer.COLOR_PROPERTIES:
            return self.normalizer._normalize_color(value)
        elif prop in self.normalizer.LENGTH_PROPERTIES:
            return self.normalizer._normalize_length(value)
        else:
            # Basic normalization: lowercase, trim whitespace
            return value.strip().lower() if value else ""

    def compute_similarity(
        self,
        styles1: CapturedStyles,
        styles2: CapturedStyles,
    ) -> float:
        """Compute similarity between two captured styles.

        Args:
            styles1: First CapturedStyles.
            styles2: Second CapturedStyles.

        Returns:
            Similarity score from 0.0 to 1.0.
        """
        flat1 = styles1.to_flat_dict()
        flat2 = styles2.to_flat_dict()

        if not flat1 and not flat2:
            return 1.0
        if not flat1 or not flat2:
            return 0.0

        all_keys = set(flat1.keys()) | set(flat2.keys())
        matches = sum(1 for k in all_keys if flat1.get(k) == flat2.get(k))

        return matches / len(all_keys) if all_keys else 1.0


__all__ = [
    "CapturedStyles",
    "ComputedStyleCapture",
]
