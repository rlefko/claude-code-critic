"""Hierarchy analyzer for visual hierarchy and typography analysis.

Analyzes UI elements for:
- Heading scale consistency
- Contrast ratio checks (text on background)
- Spacing rhythm adherence
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..collectors.runtime import CrawlResult
    from ..config import UIQualityConfig
    from ..models import RuntimeElementFingerprint

from ..models import Severity


@dataclass
class HeadingScaleMetrics:
    """Metrics for heading scale analysis."""

    heading_levels_found: dict[str, list[int]] = field(
        default_factory=dict
    )  # h1-h6 -> font sizes
    scale_consistent: bool = True
    scale_ratio: float | None = None
    inconsistencies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "heading_levels_found": self.heading_levels_found,
            "scale_consistent": self.scale_consistent,
            "scale_ratio": self.scale_ratio,
            "inconsistencies": self.inconsistencies,
        }


@dataclass
class ContrastMetrics:
    """Metrics for contrast ratio analysis."""

    total_checks: int = 0
    passing_checks: int = 0
    failing_checks: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate."""
        if self.total_checks == 0:
            return 1.0
        return self.passing_checks / self.total_checks

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_checks": self.total_checks,
            "passing_checks": self.passing_checks,
            "failing_checks": self.failing_checks,
            "pass_rate": self.pass_rate,
            "failures": self.failures,
        }


@dataclass
class SpacingRhythmMetrics:
    """Metrics for spacing rhythm analysis."""

    total_spacings: int = 0
    on_scale_spacings: int = 0
    rhythm_adherence: float = 1.0
    common_spacings: dict[str, int] = field(default_factory=dict)
    irregular_spacings: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_spacings": self.total_spacings,
            "on_scale_spacings": self.on_scale_spacings,
            "rhythm_adherence": self.rhythm_adherence,
            "common_spacings": self.common_spacings,
            "irregular_spacings": self.irregular_spacings,
        }


class HierarchyAnalyzer:
    """Analyzes UI elements for visual hierarchy.

    Checks heading scales, contrast ratios, and spacing rhythm
    to ensure visual hierarchy is clear and consistent.
    """

    # Minimum contrast ratios (WCAG 2.1)
    MIN_CONTRAST_NORMAL_TEXT = 4.5
    MIN_CONTRAST_LARGE_TEXT = 3.0
    LARGE_TEXT_SIZE_PX = 18

    # Ideal heading scale ratio (major third)
    IDEAL_SCALE_RATIO = 1.25

    def __init__(self, config: "UIQualityConfig"):
        """Initialize the hierarchy analyzer.

        Args:
            config: UI quality configuration.
        """
        self.config = config
        self._spacing_scale = {
            int(s) for s in (config.design_system.allowed_scales.spacing or [])
        }

    def _parse_font_size(self, value: str) -> int | None:
        """Parse font size to pixels."""
        value = value.strip().lower()
        if value.endswith("px"):
            try:
                return int(float(value[:-2]))
            except ValueError:
                return None
        elif value.endswith("rem"):
            try:
                # Assume 16px base
                return int(float(value[:-3]) * 16)
            except ValueError:
                return None
        elif value.endswith("em"):
            try:
                return int(float(value[:-2]) * 16)
            except ValueError:
                return None
        return None

    def _parse_color_to_rgb(self, color: str) -> tuple[int, int, int] | None:
        """Parse color string to RGB tuple."""
        color = color.strip().lower()

        # Handle hex colors
        if color.startswith("#"):
            hex_color = color[1:]
            if len(hex_color) == 3:
                hex_color = "".join(c * 2 for c in hex_color)
            if len(hex_color) == 6:
                try:
                    r = int(hex_color[0:2], 16)
                    g = int(hex_color[2:4], 16)
                    b = int(hex_color[4:6], 16)
                    return (r, g, b)
                except ValueError:
                    return None

        # Handle rgb/rgba
        if color.startswith("rgb"):
            try:
                # Extract numbers from rgb(r, g, b) or rgba(r, g, b, a)
                start = color.index("(") + 1
                end = color.index(")")
                parts = color[start:end].split(",")
                r = int(float(parts[0].strip()))
                g = int(float(parts[1].strip()))
                b = int(float(parts[2].strip()))
                return (r, g, b)
            except (ValueError, IndexError):
                return None

        return None

    def _relative_luminance(self, r: int, g: int, b: int) -> float:
        """Calculate relative luminance of RGB color."""

        def adjust(c: int) -> float:
            c_srgb = c / 255
            if c_srgb <= 0.03928:
                return c_srgb / 12.92
            return ((c_srgb + 0.055) / 1.055) ** 2.4

        r_adj = adjust(r)
        g_adj = adjust(g)
        b_adj = adjust(b)

        return 0.2126 * r_adj + 0.7152 * g_adj + 0.0722 * b_adj

    def _contrast_ratio(
        self, color1: tuple[int, int, int], color2: tuple[int, int, int]
    ) -> float:
        """Calculate contrast ratio between two colors."""
        l1 = self._relative_luminance(*color1)
        l2 = self._relative_luminance(*color2)

        lighter = max(l1, l2)
        darker = min(l1, l2)

        return (lighter + 0.05) / (darker + 0.05)

    def analyze_heading_scale(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> HeadingScaleMetrics:
        """Analyze heading typography scale consistency.

        Checks that heading sizes follow a consistent scale ratio.

        Args:
            fingerprints: Runtime element fingerprints.

        Returns:
            HeadingScaleMetrics with scale analysis.
        """
        metrics = HeadingScaleMetrics()

        # Collect heading font sizes by level
        heading_roles = {"heading"}
        for fp in fingerprints:
            if fp.role in heading_roles:
                font_size = fp.computed_style_subset.get("font-size")
                if font_size:
                    size_px = self._parse_font_size(font_size)
                    if size_px:
                        # Try to determine heading level from selector or source hint
                        level = "unknown"
                        selector_lower = fp.selector.lower()
                        for h in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                            if h in selector_lower:
                                level = h
                                break

                        if level not in metrics.heading_levels_found:
                            metrics.heading_levels_found[level] = []
                        metrics.heading_levels_found[level].append(size_px)

        # Analyze scale consistency
        if len(metrics.heading_levels_found) >= 2:
            # Get average sizes per level
            level_averages: dict[str, float] = {}
            for level, sizes in metrics.heading_levels_found.items():
                if sizes:
                    level_averages[level] = sum(sizes) / len(sizes)

            # Calculate ratios between adjacent levels
            sorted_levels = sorted(
                [level for level in level_averages if level.startswith("h")],
                key=lambda x: int(x[1]) if x[1].isdigit() else 0,
            )

            ratios: list[float] = []
            for i in range(len(sorted_levels) - 1):
                larger = level_averages[sorted_levels[i]]
                smaller = level_averages[sorted_levels[i + 1]]
                if smaller > 0:
                    ratio = larger / smaller
                    ratios.append(ratio)

            if ratios:
                avg_ratio = sum(ratios) / len(ratios)
                metrics.scale_ratio = avg_ratio

                # Check for consistency (all ratios within 20% of average)
                for i, ratio in enumerate(ratios):
                    deviation = abs(ratio - avg_ratio) / avg_ratio
                    if deviation > 0.2:
                        metrics.scale_consistent = False
                        metrics.inconsistencies.append(
                            {
                                "level_pair": f"{sorted_levels[i]}/{sorted_levels[i+1]}",
                                "ratio": ratio,
                                "expected": avg_ratio,
                                "deviation": deviation,
                            }
                        )

        return metrics

    def analyze_contrast(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> ContrastMetrics:
        """Analyze text contrast ratios.

        Checks text color against background for WCAG compliance.

        Args:
            fingerprints: Runtime element fingerprints.

        Returns:
            ContrastMetrics with contrast analysis.
        """
        metrics = ContrastMetrics()

        # Text roles to check
        text_roles = {"heading", "text", "link", "button"}

        for fp in fingerprints:
            if fp.role not in text_roles:
                continue

            text_color = fp.computed_style_subset.get("color")
            bg_color = fp.computed_style_subset.get("background-color")

            if not text_color or not bg_color:
                continue

            text_rgb = self._parse_color_to_rgb(text_color)
            bg_rgb = self._parse_color_to_rgb(bg_color)

            if not text_rgb or not bg_rgb:
                continue

            metrics.total_checks += 1
            ratio = self._contrast_ratio(text_rgb, bg_rgb)

            # Determine minimum required ratio
            font_size = fp.computed_style_subset.get("font-size", "16px")
            size_px = self._parse_font_size(font_size) or 16
            min_ratio = (
                self.MIN_CONTRAST_LARGE_TEXT
                if size_px >= self.LARGE_TEXT_SIZE_PX
                else self.MIN_CONTRAST_NORMAL_TEXT
            )

            if ratio >= min_ratio:
                metrics.passing_checks += 1
            else:
                metrics.failing_checks += 1
                metrics.failures.append(
                    {
                        "element": fp.selector,
                        "page": fp.page_id,
                        "text_color": text_color,
                        "background_color": bg_color,
                        "contrast_ratio": round(ratio, 2),
                        "required_ratio": min_ratio,
                    }
                )

        return metrics

    def analyze_spacing_rhythm(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> SpacingRhythmMetrics:
        """Analyze spacing rhythm consistency.

        Checks that spacing values follow the design scale.

        Args:
            fingerprints: Runtime element fingerprints.

        Returns:
            SpacingRhythmMetrics with rhythm analysis.
        """
        metrics = SpacingRhythmMetrics()
        spacing_counts: dict[str, int] = defaultdict(int)

        spacing_props = ["padding", "margin", "gap"]

        for fp in fingerprints:
            for prop in spacing_props:
                value = fp.computed_style_subset.get(prop)
                if not value:
                    continue

                # Parse numeric value
                value = value.strip().lower()
                for unit in ["px", "rem", "em"]:
                    if value.endswith(unit):
                        try:
                            num = int(float(value[: -len(unit)]))
                            metrics.total_spacings += 1
                            spacing_counts[str(num)] += 1

                            if num in self._spacing_scale or num == 0:
                                metrics.on_scale_spacings += 1
                            else:
                                metrics.irregular_spacings.append(
                                    {
                                        "element": fp.selector,
                                        "page": fp.page_id,
                                        "property": prop,
                                        "value": value,
                                        "numeric": num,
                                    }
                                )
                        except ValueError:
                            pass
                        break

        # Calculate rhythm adherence
        if metrics.total_spacings > 0:
            metrics.rhythm_adherence = (
                metrics.on_scale_spacings / metrics.total_spacings
            )

        # Record common spacings
        metrics.common_spacings = dict(
            sorted(spacing_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        )

        return metrics

    def generate_hierarchy_critiques(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        crawl_results: list["CrawlResult"] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate hierarchy critiques from analysis.

        Args:
            fingerprints: Runtime element fingerprints.
            crawl_results: Optional crawl results for screenshot paths.

        Returns:
            List of critique dictionaries ready for CritiqueItem creation.
        """
        critiques: list[dict[str, Any]] = []

        # 1. Heading scale critique
        heading_metrics = self.analyze_heading_scale(fingerprints)
        if not heading_metrics.scale_consistent and heading_metrics.inconsistencies:
            critiques.append(
                {
                    "category": "hierarchy",
                    "subcategory": "heading_scale",
                    "severity": Severity.WARN,
                    "title": "Inconsistent Heading Scale",
                    "description": (
                        f"Heading sizes don't follow a consistent scale ratio. "
                        f"Found {len(heading_metrics.inconsistencies)} inconsistencies. "
                        f"Current average ratio: {heading_metrics.scale_ratio:.2f}"
                    ),
                    "evidence": heading_metrics.inconsistencies,
                    "metrics": heading_metrics.to_dict(),
                }
            )

        # 2. Contrast critique
        contrast_metrics = self.analyze_contrast(fingerprints)
        if contrast_metrics.failing_checks > 0:
            severity = (
                Severity.FAIL if contrast_metrics.pass_rate < 0.8 else Severity.WARN
            )
            critiques.append(
                {
                    "category": "hierarchy",
                    "subcategory": "contrast",
                    "severity": severity,
                    "title": "Insufficient Text Contrast",
                    "description": (
                        f"{contrast_metrics.failing_checks} text elements have insufficient "
                        f"contrast ratio (WCAG 2.1 minimum: {self.MIN_CONTRAST_NORMAL_TEXT}:1). "
                        f"Pass rate: {contrast_metrics.pass_rate:.0%}"
                    ),
                    "evidence": contrast_metrics.failures[:10],  # Limit evidence
                    "metrics": contrast_metrics.to_dict(),
                }
            )

        # 3. Spacing rhythm critique
        rhythm_metrics = self.analyze_spacing_rhythm(fingerprints)
        if rhythm_metrics.rhythm_adherence < 0.8:
            critiques.append(
                {
                    "category": "hierarchy",
                    "subcategory": "spacing_rhythm",
                    "severity": Severity.INFO,
                    "title": "Irregular Spacing Rhythm",
                    "description": (
                        f"Only {rhythm_metrics.rhythm_adherence:.0%} of spacing values are on-scale. "
                        f"Found {len(rhythm_metrics.irregular_spacings)} irregular values."
                    ),
                    "evidence": rhythm_metrics.irregular_spacings[:10],
                    "metrics": rhythm_metrics.to_dict(),
                }
            )

        return critiques


__all__ = [
    "HierarchyAnalyzer",
    "HeadingScaleMetrics",
    "ContrastMetrics",
    "SpacingRhythmMetrics",
]
