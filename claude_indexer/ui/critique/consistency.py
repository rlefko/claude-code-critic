"""Consistency analyzer for token adherence and role variant detection.

Analyzes UI elements for:
- Token adherence rates (colors, spacing, typography, radius)
- Number of distinct variants per role (buttons, cards, inputs)
- Outlier detection (elements that differ from the majority)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..collectors.runtime import CrawlResult
    from ..collectors.screenshots import VisualClusteringResult
    from ..config import UIQualityConfig
    from ..models import RuntimeElementFingerprint

from ..models import Severity


@dataclass
class TokenAdherenceMetrics:
    """Metrics for token adherence analysis."""

    total_values: int = 0
    on_scale_values: int = 0
    off_scale_values: int = 0
    adherence_rate: float = 1.0
    off_scale_by_property: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_values": self.total_values,
            "on_scale_values": self.on_scale_values,
            "off_scale_values": self.off_scale_values,
            "adherence_rate": self.adherence_rate,
            "off_scale_by_property": self.off_scale_by_property,
        }


@dataclass
class RoleVariantMetrics:
    """Metrics for role variant analysis."""

    role: str
    variant_count: int
    elements_per_variant: dict[str, int] = field(default_factory=dict)
    representative_screenshots: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "variant_count": self.variant_count,
            "elements_per_variant": self.elements_per_variant,
            "representative_screenshots": self.representative_screenshots,
        }


@dataclass
class OutlierMetrics:
    """Metrics for outlier detection."""

    property_name: str
    majority_value: str
    outlier_value: str
    outlier_count: int
    total_count: int
    z_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "property_name": self.property_name,
            "majority_value": self.majority_value,
            "outlier_value": self.outlier_value,
            "outlier_count": self.outlier_count,
            "total_count": self.total_count,
            "z_score": self.z_score,
        }


class ConsistencyAnalyzer:
    """Analyzes UI elements for design consistency.

    Detects token drift, excess variants, and style outliers
    across the analyzed UI elements.
    """

    # Properties to check for token adherence
    COLOR_PROPERTIES = {"color", "background-color", "border-color"}
    SPACING_PROPERTIES = {"padding", "margin", "gap"}
    TYPOGRAPHY_PROPERTIES = {"font-size", "line-height", "font-weight"}
    RADIUS_PROPERTIES = {"border-radius"}

    # Roles to analyze for variants
    ANALYZED_ROLES = {"button", "input", "card", "link", "heading"}

    # Z-score threshold for outlier detection
    OUTLIER_Z_THRESHOLD = 2.0

    def __init__(self, config: "UIQualityConfig"):
        """Initialize the consistency analyzer.

        Args:
            config: UI quality configuration with token scales.
        """
        self.config = config
        self._color_tokens: set[str] = set()
        self._spacing_scale: set[int] = set()
        self._typography_scale: set[int] = set()
        self._radius_scale: set[int] = set()
        self._load_token_scales()

    def _load_token_scales(self) -> None:
        """Load token scales from configuration."""
        scales = self.config.design_system.allowed_scales

        # Load spacing scale
        if scales.spacing:
            self._spacing_scale = {int(s) for s in scales.spacing}

        # Load radius scale
        if scales.radius:
            self._radius_scale = {int(r) for r in scales.radius}

        # Load typography scale - extract font sizes from TypographyToken objects
        if scales.typography:
            self._typography_scale = {int(t.size) for t in scales.typography}

    def _normalize_color(self, color: str) -> str:
        """Normalize color value to lowercase hex."""
        color = color.strip().lower()
        # Convert rgb() to hex if needed (simplified)
        if color.startswith("rgb"):
            # Basic rgb extraction - real implementation would be more robust
            return color
        return color

    def _parse_numeric_value(self, value: str) -> int | None:
        """Parse numeric value from CSS value string."""
        value = value.strip().lower()
        # Extract number from px, rem, em values
        for unit in ["px", "rem", "em", "%"]:
            if value.endswith(unit):
                try:
                    return int(float(value[: -len(unit)]))
                except ValueError:
                    return None
        # Try parsing as plain number
        try:
            return int(float(value))
        except ValueError:
            return None

    def analyze_token_adherence(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> tuple[TokenAdherenceMetrics, list[dict[str, Any]]]:
        """Analyze token adherence across all elements.

        Args:
            fingerprints: Runtime element fingerprints with computed styles.

        Returns:
            Tuple of (metrics, list of evidence items for off-scale values).
        """
        metrics = TokenAdherenceMetrics()
        evidence_items: list[dict[str, Any]] = []

        for fp in fingerprints:
            styles = fp.computed_style_subset

            # Check color properties
            for prop in self.COLOR_PROPERTIES:
                if prop in styles:
                    value = styles[prop]
                    metrics.total_values += 1
                    normalized = self._normalize_color(value)
                    if normalized not in self._color_tokens:
                        metrics.off_scale_values += 1
                        if prop not in metrics.off_scale_by_property:
                            metrics.off_scale_by_property[prop] = []
                        metrics.off_scale_by_property[prop].append(value)
                        evidence_items.append(
                            {
                                "property": prop,
                                "value": value,
                                "element": fp.selector,
                                "page": fp.page_id,
                            }
                        )
                    else:
                        metrics.on_scale_values += 1

            # Check spacing properties
            for prop in self.SPACING_PROPERTIES:
                if prop in styles:
                    value = styles[prop]
                    metrics.total_values += 1
                    numeric = self._parse_numeric_value(value)
                    if numeric is not None and numeric not in self._spacing_scale:
                        metrics.off_scale_values += 1
                        if prop not in metrics.off_scale_by_property:
                            metrics.off_scale_by_property[prop] = []
                        metrics.off_scale_by_property[prop].append(value)
                        evidence_items.append(
                            {
                                "property": prop,
                                "value": value,
                                "element": fp.selector,
                                "page": fp.page_id,
                            }
                        )
                    else:
                        metrics.on_scale_values += 1

            # Check typography properties
            for prop in self.TYPOGRAPHY_PROPERTIES:
                if prop in styles:
                    value = styles[prop]
                    metrics.total_values += 1
                    numeric = self._parse_numeric_value(value)
                    if numeric is not None and numeric not in self._typography_scale:
                        metrics.off_scale_values += 1
                        if prop not in metrics.off_scale_by_property:
                            metrics.off_scale_by_property[prop] = []
                        metrics.off_scale_by_property[prop].append(value)
                        evidence_items.append(
                            {
                                "property": prop,
                                "value": value,
                                "element": fp.selector,
                                "page": fp.page_id,
                            }
                        )
                    else:
                        metrics.on_scale_values += 1

            # Check radius properties
            for prop in self.RADIUS_PROPERTIES:
                if prop in styles:
                    value = styles[prop]
                    metrics.total_values += 1
                    numeric = self._parse_numeric_value(value)
                    if numeric is not None and numeric not in self._radius_scale:
                        metrics.off_scale_values += 1
                        if prop not in metrics.off_scale_by_property:
                            metrics.off_scale_by_property[prop] = []
                        metrics.off_scale_by_property[prop].append(value)
                        evidence_items.append(
                            {
                                "property": prop,
                                "value": value,
                                "element": fp.selector,
                                "page": fp.page_id,
                            }
                        )
                    else:
                        metrics.on_scale_values += 1

        # Calculate adherence rate
        if metrics.total_values > 0:
            metrics.adherence_rate = metrics.on_scale_values / metrics.total_values

        return metrics, evidence_items

    def analyze_role_variants(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        visual_clusters: "VisualClusteringResult | None" = None,
    ) -> dict[str, RoleVariantMetrics]:
        """Analyze variant counts per UI role.

        Groups elements by role and identifies distinct variants
        based on visual clustering or style signatures.

        Args:
            fingerprints: Runtime element fingerprints.
            visual_clusters: Optional visual clustering results.

        Returns:
            Dict mapping role to variant metrics.
        """
        role_metrics: dict[str, RoleVariantMetrics] = {}

        # Group fingerprints by role
        by_role: dict[str, list[RuntimeElementFingerprint]] = defaultdict(list)
        for fp in fingerprints:
            if fp.role in self.ANALYZED_ROLES:
                by_role[fp.role].append(fp)

        for role, fps in by_role.items():
            # Create style signatures for variant detection
            signatures: dict[str, list[RuntimeElementFingerprint]] = defaultdict(list)

            for fp in fps:
                # Create a signature from key style properties
                sig_parts = []
                for prop in [
                    "background-color",
                    "border-radius",
                    "padding",
                    "font-size",
                ]:
                    if prop in fp.computed_style_subset:
                        sig_parts.append(f"{prop}:{fp.computed_style_subset[prop]}")
                signature = "|".join(sorted(sig_parts)) or "default"
                signatures[signature].append(fp)

            # Build metrics
            metrics = RoleVariantMetrics(
                role=role,
                variant_count=len(signatures),
                elements_per_variant={
                    f"variant_{i}": len(fps)
                    for i, (_, fps) in enumerate(signatures.items())
                },
            )

            # Add representative screenshots if visual clusters available
            if visual_clusters:
                for cluster in visual_clusters.clusters:
                    if any(fp.role == role for fp in cluster.members):
                        if cluster.representative_screenshot:
                            metrics.representative_screenshots.append(
                                cluster.representative_screenshot
                            )

            role_metrics[role] = metrics

        return role_metrics

    def detect_outliers(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> list[OutlierMetrics]:
        """Detect style outliers within each role.

        Finds elements that differ significantly from the majority
        of elements with the same role.

        Args:
            fingerprints: Runtime element fingerprints.

        Returns:
            List of outlier metrics.
        """
        outliers: list[OutlierMetrics] = []

        # Group by role
        by_role: dict[str, list[RuntimeElementFingerprint]] = defaultdict(list)
        for fp in fingerprints:
            if fp.role in self.ANALYZED_ROLES:
                by_role[fp.role].append(fp)

        # Check key properties for outliers within each role
        properties_to_check = ["border-radius", "padding", "font-size", "font-weight"]

        for _role, fps in by_role.items():
            if len(fps) < 3:
                continue  # Need at least 3 elements for meaningful outlier detection

            for prop in properties_to_check:
                values: dict[str, int] = defaultdict(int)
                for fp in fps:
                    if prop in fp.computed_style_subset:
                        values[fp.computed_style_subset[prop]] += 1

                if len(values) < 2:
                    continue

                # Find majority value
                sorted_values = sorted(values.items(), key=lambda x: x[1], reverse=True)
                majority_value, majority_count = sorted_values[0]
                total = sum(values.values())

                # Check for outliers (values that appear much less frequently)
                for value, count in sorted_values[1:]:
                    # Calculate rough z-score based on frequency
                    expected_freq = total / len(values)
                    if expected_freq > 0:
                        z_score = abs(count - expected_freq) / (expected_freq**0.5 + 1)
                        if (
                            z_score > self.OUTLIER_Z_THRESHOLD
                            and count < majority_count * 0.25
                        ):
                            outliers.append(
                                OutlierMetrics(
                                    property_name=prop,
                                    majority_value=majority_value,
                                    outlier_value=value,
                                    outlier_count=count,
                                    total_count=total,
                                    z_score=z_score,
                                )
                            )

        return outliers

    def generate_consistency_critiques(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        crawl_results: list["CrawlResult"] | None = None,
        visual_clusters: "VisualClusteringResult | None" = None,
    ) -> list[dict[str, Any]]:
        """Generate consistency critiques from analysis.

        Args:
            fingerprints: Runtime element fingerprints.
            crawl_results: Optional crawl results for screenshot paths.
            visual_clusters: Optional visual clustering results.

        Returns:
            List of critique dictionaries ready for CritiqueItem creation.
        """
        critiques: list[dict[str, Any]] = []

        # 1. Token adherence critique
        token_metrics, token_evidence = self.analyze_token_adherence(fingerprints)
        if token_metrics.adherence_rate < 0.9:  # Less than 90% adherence
            severity = (
                Severity.FAIL if token_metrics.adherence_rate < 0.7 else Severity.WARN
            )
            critiques.append(
                {
                    "category": "consistency",
                    "subcategory": "token_adherence",
                    "severity": severity,
                    "title": "Low Token Adherence Rate",
                    "description": (
                        f"Only {token_metrics.adherence_rate:.0%} of style values use design tokens. "
                        f"{token_metrics.off_scale_values} values are off-scale."
                    ),
                    "evidence": token_evidence[:10],  # Limit evidence items
                    "metrics": token_metrics.to_dict(),
                }
            )

        # 2. Role variant critiques
        variant_metrics = self.analyze_role_variants(fingerprints, visual_clusters)
        # Default max variants per role is 4 (e.g., primary, secondary, tertiary, destructive)
        max_variants = getattr(self.config.gating, "max_variants_per_role", None) or 4

        for role, metrics in variant_metrics.items():
            if metrics.variant_count > max_variants:
                critiques.append(
                    {
                        "category": "consistency",
                        "subcategory": "role_variants",
                        "severity": Severity.WARN,
                        "title": f"Excessive {role.title()} Variants",
                        "description": (
                            f"Found {metrics.variant_count} distinct {role} styles. "
                            f"Consider consolidating to {max_variants} or fewer variants."
                        ),
                        "evidence": [],
                        "screenshots": metrics.representative_screenshots,
                        "metrics": metrics.to_dict(),
                    }
                )

        # 3. Outlier critiques
        outliers = self.detect_outliers(fingerprints)
        for outlier in outliers:
            critiques.append(
                {
                    "category": "consistency",
                    "subcategory": "outlier",
                    "severity": Severity.INFO,
                    "title": f"Style Outlier: {outlier.property_name}",
                    "description": (
                        f"Found {outlier.outlier_count} elements with {outlier.property_name}: "
                        f"{outlier.outlier_value} while most ({outlier.total_count - outlier.outlier_count}) "
                        f"use {outlier.majority_value}"
                    ),
                    "evidence": [],
                    "metrics": outlier.to_dict(),
                }
            )

        return critiques


__all__ = [
    "ConsistencyAnalyzer",
    "TokenAdherenceMetrics",
    "RoleVariantMetrics",
    "OutlierMetrics",
]
