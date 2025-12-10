"""Affordance analyzer for usability and accessibility analysis.

Analyzes UI elements for:
- Focus visibility and keyboard navigation cues
- Tappable target sizes (minimum 44x44px)
- Form layout clarity (labels, errors, hints)
- Feedback states presence (loading, disabled, error)
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..collectors.runtime import CrawlResult
    from ..collectors.pseudo_states import PseudoStateCapture
    from ..config import UIQualityConfig
    from ..models import RuntimeElementFingerprint

from ..models import Severity


@dataclass
class FocusVisibilityMetrics:
    """Metrics for focus visibility analysis."""

    total_interactive: int = 0
    with_visible_focus: int = 0
    without_visible_focus: int = 0
    inconsistent_focus_styles: list[dict[str, Any]] = field(default_factory=list)
    focus_ring_variations: dict[str, int] = field(default_factory=dict)

    @property
    def visibility_rate(self) -> float:
        """Calculate focus visibility rate."""
        if self.total_interactive == 0:
            return 1.0
        return self.with_visible_focus / self.total_interactive

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_interactive": self.total_interactive,
            "with_visible_focus": self.with_visible_focus,
            "without_visible_focus": self.without_visible_focus,
            "visibility_rate": self.visibility_rate,
            "inconsistent_focus_styles": self.inconsistent_focus_styles,
            "focus_ring_variations": self.focus_ring_variations,
        }


@dataclass
class TapTargetMetrics:
    """Metrics for tap target size analysis."""

    total_targets: int = 0
    adequate_size: int = 0
    undersized: int = 0
    undersized_elements: list[dict[str, Any]] = field(default_factory=list)

    @property
    def compliance_rate(self) -> float:
        """Calculate tap target compliance rate."""
        if self.total_targets == 0:
            return 1.0
        return self.adequate_size / self.total_targets

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_targets": self.total_targets,
            "adequate_size": self.adequate_size,
            "undersized": self.undersized,
            "compliance_rate": self.compliance_rate,
            "undersized_elements": self.undersized_elements,
        }


@dataclass
class FormLayoutMetrics:
    """Metrics for form layout analysis."""

    total_inputs: int = 0
    with_labels: int = 0
    with_placeholders_only: int = 0
    missing_labels: list[dict[str, Any]] = field(default_factory=list)
    error_patterns_found: dict[str, int] = field(default_factory=dict)

    @property
    def label_coverage(self) -> float:
        """Calculate label coverage rate."""
        if self.total_inputs == 0:
            return 1.0
        return self.with_labels / self.total_inputs

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_inputs": self.total_inputs,
            "with_labels": self.with_labels,
            "with_placeholders_only": self.with_placeholders_only,
            "label_coverage": self.label_coverage,
            "missing_labels": self.missing_labels,
            "error_patterns_found": self.error_patterns_found,
        }


@dataclass
class FeedbackStateMetrics:
    """Metrics for feedback state analysis."""

    components_analyzed: int = 0
    with_loading_state: int = 0
    with_disabled_state: int = 0
    with_error_state: int = 0
    missing_states: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "components_analyzed": self.components_analyzed,
            "with_loading_state": self.with_loading_state,
            "with_disabled_state": self.with_disabled_state,
            "with_error_state": self.with_error_state,
            "missing_states": self.missing_states,
        }


class AffordanceAnalyzer:
    """Analyzes UI elements for usability and accessibility.

    Checks focus indicators, touch targets, form layout,
    and state feedback to ensure good user experience.
    """

    # Minimum tap target size (WCAG 2.1 Level AAA)
    MIN_TAP_TARGET_SIZE = 44  # pixels

    # Interactive element roles
    INTERACTIVE_ROLES = {"button", "link", "input", "checkbox", "radio", "select"}

    # Form input roles
    FORM_ROLES = {"input", "textarea", "select", "checkbox", "radio"}

    def __init__(self, config: "UIQualityConfig"):
        """Initialize the affordance analyzer.

        Args:
            config: UI quality configuration.
        """
        self.config = config

    def _has_visible_focus_ring(
        self,
        default_styles: dict[str, str],
        focus_styles: dict[str, str] | None,
    ) -> bool:
        """Check if element has visible focus indication.

        Args:
            default_styles: Default computed styles.
            focus_styles: Focus state computed styles.

        Returns:
            True if element has visible focus indication.
        """
        if not focus_styles:
            return False

        # Check for outline changes
        default_outline = default_styles.get("outline", "none")
        focus_outline = focus_styles.get("outline", "none")

        if focus_outline != default_outline and focus_outline not in ["none", "0"]:
            return True

        # Check for box-shadow changes (common focus ring approach)
        default_shadow = default_styles.get("box-shadow", "none")
        focus_shadow = focus_styles.get("box-shadow", "none")

        if focus_shadow != default_shadow and focus_shadow not in ["none", ""]:
            return True

        # Check for border changes
        default_border = default_styles.get("border", "")
        focus_border = focus_styles.get("border", "")

        if focus_border != default_border:
            return True

        # Check for background changes (less ideal but still visible)
        default_bg = default_styles.get("background-color", "")
        focus_bg = focus_styles.get("background-color", "")

        if focus_bg != default_bg:
            return True

        return False

    def _get_focus_ring_signature(self, focus_styles: dict[str, str]) -> str:
        """Get a signature for focus ring style for consistency checking."""
        parts = []
        for prop in ["outline", "box-shadow", "border"]:
            if prop in focus_styles:
                parts.append(f"{prop}:{focus_styles[prop]}")
        return "|".join(sorted(parts)) or "none"

    def analyze_focus_visibility(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        pseudo_states: list["PseudoStateCapture"] | None = None,
    ) -> FocusVisibilityMetrics:
        """Analyze focus visibility for interactive elements.

        Args:
            fingerprints: Runtime element fingerprints.
            pseudo_states: Optional pseudo-state captures with focus states.

        Returns:
            FocusVisibilityMetrics with analysis results.
        """
        metrics = FocusVisibilityMetrics()

        # Build lookup for pseudo states by selector
        pseudo_by_selector: dict[str, "PseudoStateCapture"] = {}
        if pseudo_states:
            for ps in pseudo_states:
                pseudo_by_selector[ps.selector] = ps

        for fp in fingerprints:
            if fp.role not in self.INTERACTIVE_ROLES:
                continue

            metrics.total_interactive += 1

            # Get pseudo state for this element
            pseudo = pseudo_by_selector.get(fp.selector)
            if pseudo and pseudo.focus_styles:
                has_focus = self._has_visible_focus_ring(
                    fp.computed_style_subset,
                    pseudo.focus_styles,
                )
                if has_focus:
                    metrics.with_visible_focus += 1
                    # Track focus ring style for consistency
                    sig = self._get_focus_ring_signature(pseudo.focus_styles)
                    if sig not in metrics.focus_ring_variations:
                        metrics.focus_ring_variations[sig] = 0
                    metrics.focus_ring_variations[sig] += 1
                else:
                    metrics.without_visible_focus += 1
                    metrics.inconsistent_focus_styles.append({
                        "element": fp.selector,
                        "page": fp.page_id,
                        "role": fp.role,
                        "issue": "no_visible_focus",
                    })
            else:
                # No pseudo state captured - can't verify focus
                metrics.with_visible_focus += 1  # Assume good faith

        return metrics

    def analyze_tap_targets(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> TapTargetMetrics:
        """Analyze tap target sizes for touch accessibility.

        Args:
            fingerprints: Runtime element fingerprints with layout boxes.

        Returns:
            TapTargetMetrics with analysis results.
        """
        metrics = TapTargetMetrics()

        for fp in fingerprints:
            if fp.role not in self.INTERACTIVE_ROLES:
                continue

            metrics.total_targets += 1

            # Check layout box dimensions
            if fp.layout_box:
                width = fp.layout_box.width
                height = fp.layout_box.height

                if width >= self.MIN_TAP_TARGET_SIZE and height >= self.MIN_TAP_TARGET_SIZE:
                    metrics.adequate_size += 1
                else:
                    metrics.undersized += 1
                    metrics.undersized_elements.append({
                        "element": fp.selector,
                        "page": fp.page_id,
                        "role": fp.role,
                        "width": width,
                        "height": height,
                        "minimum": self.MIN_TAP_TARGET_SIZE,
                    })
            else:
                # No layout box - assume adequate
                metrics.adequate_size += 1

        return metrics

    def analyze_form_layout(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
    ) -> FormLayoutMetrics:
        """Analyze form layout for proper labeling.

        Args:
            fingerprints: Runtime element fingerprints.

        Returns:
            FormLayoutMetrics with analysis results.
        """
        metrics = FormLayoutMetrics()

        # Group elements by page for context analysis
        by_page: dict[str, list["RuntimeElementFingerprint"]] = defaultdict(list)
        for fp in fingerprints:
            by_page[fp.page_id].append(fp)

        for page_id, page_fps in by_page.items():
            # Find inputs and look for associated labels
            inputs = [fp for fp in page_fps if fp.role in self.FORM_ROLES]
            labels = [fp for fp in page_fps if "label" in fp.selector.lower()]

            for inp in inputs:
                metrics.total_inputs += 1

                # Check for label (simplified - real implementation would use aria-labelledby)
                has_label = any(
                    "for=" in label.selector or inp.selector in label.selector
                    for label in labels
                )

                # Check for aria-label or placeholder
                has_aria_label = "aria-label" in inp.selector.lower()
                has_placeholder = "placeholder" in str(inp.computed_style_subset)

                if has_label or has_aria_label:
                    metrics.with_labels += 1
                elif has_placeholder:
                    metrics.with_placeholders_only += 1
                    metrics.missing_labels.append({
                        "element": inp.selector,
                        "page": page_id,
                        "issue": "placeholder_only",
                    })
                else:
                    metrics.missing_labels.append({
                        "element": inp.selector,
                        "page": page_id,
                        "issue": "no_label",
                    })

        return metrics

    def analyze_feedback_states(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        pseudo_states: list["PseudoStateCapture"] | None = None,
    ) -> FeedbackStateMetrics:
        """Analyze presence of feedback states.

        Checks for loading, disabled, and error state handling.

        Args:
            fingerprints: Runtime element fingerprints.
            pseudo_states: Optional pseudo-state captures.

        Returns:
            FeedbackStateMetrics with analysis results.
        """
        metrics = FeedbackStateMetrics()

        # Build lookup for pseudo states
        pseudo_by_selector: dict[str, "PseudoStateCapture"] = {}
        if pseudo_states:
            for ps in pseudo_states:
                pseudo_by_selector[ps.selector] = ps

        # Analyze buttons and interactive elements
        analyzed_roles = {"button", "input", "select"}

        for fp in fingerprints:
            if fp.role not in analyzed_roles:
                continue

            metrics.components_analyzed += 1
            pseudo = pseudo_by_selector.get(fp.selector)

            # Check for disabled state
            has_disabled = False
            if pseudo and pseudo.disabled_styles:
                default_opacity = fp.computed_style_subset.get("opacity", "1")
                disabled_opacity = pseudo.disabled_styles.get("opacity", "1")
                default_cursor = fp.computed_style_subset.get("cursor", "")
                disabled_cursor = pseudo.disabled_styles.get("cursor", "")

                if (
                    disabled_opacity != default_opacity
                    or disabled_cursor == "not-allowed"
                    or "disabled" in pseudo.disabled_styles.get("pointer-events", "")
                ):
                    has_disabled = True

            if has_disabled:
                metrics.with_disabled_state += 1

            # Check for loading state indicators in styles
            # (This is a heuristic - real implementation might look for specific patterns)
            styles_str = str(fp.computed_style_subset)
            if "loading" in fp.selector.lower() or "spinner" in styles_str.lower():
                metrics.with_loading_state += 1

            # Check for error state patterns
            color = fp.computed_style_subset.get("color", "")
            border_color = fp.computed_style_subset.get("border-color", "")
            if "error" in fp.selector.lower() or "red" in color or "#f" in border_color.lower():
                metrics.with_error_state += 1

        return metrics

    def generate_affordance_critiques(
        self,
        fingerprints: list["RuntimeElementFingerprint"],
        crawl_results: list["CrawlResult"] | None = None,
        pseudo_states: list["PseudoStateCapture"] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate affordance critiques from analysis.

        Args:
            fingerprints: Runtime element fingerprints.
            crawl_results: Optional crawl results.
            pseudo_states: Optional pseudo-state captures.

        Returns:
            List of critique dictionaries ready for CritiqueItem creation.
        """
        critiques: list[dict[str, Any]] = []

        # 1. Focus visibility critique
        focus_metrics = self.analyze_focus_visibility(fingerprints, pseudo_states)
        if focus_metrics.visibility_rate < 0.9:
            severity = (
                Severity.FAIL
                if focus_metrics.visibility_rate < 0.7
                else Severity.WARN
            )
            critiques.append({
                "category": "affordance",
                "subcategory": "focus_visibility",
                "severity": severity,
                "title": "Missing Focus Indicators",
                "description": (
                    f"{focus_metrics.without_visible_focus} of "
                    f"{focus_metrics.total_interactive} interactive elements "
                    f"lack visible focus indicators. This impacts keyboard navigation."
                ),
                "evidence": focus_metrics.inconsistent_focus_styles[:10],
                "metrics": focus_metrics.to_dict(),
            })

        # Check focus ring consistency
        if len(focus_metrics.focus_ring_variations) > 3:
            critiques.append({
                "category": "affordance",
                "subcategory": "focus_consistency",
                "severity": Severity.INFO,
                "title": "Inconsistent Focus Ring Styles",
                "description": (
                    f"Found {len(focus_metrics.focus_ring_variations)} different focus ring styles. "
                    "Consider standardizing focus indicators for consistency."
                ),
                "evidence": [],
                "metrics": {"variations": focus_metrics.focus_ring_variations},
            })

        # 2. Tap target critique
        tap_metrics = self.analyze_tap_targets(fingerprints)
        if tap_metrics.undersized > 0:
            severity = (
                Severity.WARN
                if tap_metrics.compliance_rate >= 0.8
                else Severity.FAIL
            )
            critiques.append({
                "category": "affordance",
                "subcategory": "tap_targets",
                "severity": severity,
                "title": "Undersized Touch Targets",
                "description": (
                    f"{tap_metrics.undersized} interactive elements are smaller than "
                    f"the minimum recommended size of {self.MIN_TAP_TARGET_SIZE}x"
                    f"{self.MIN_TAP_TARGET_SIZE}px."
                ),
                "evidence": tap_metrics.undersized_elements[:10],
                "metrics": tap_metrics.to_dict(),
            })

        # 3. Form layout critique
        form_metrics = self.analyze_form_layout(fingerprints)
        if form_metrics.label_coverage < 0.9:
            severity = (
                Severity.FAIL
                if form_metrics.label_coverage < 0.7
                else Severity.WARN
            )
            critiques.append({
                "category": "affordance",
                "subcategory": "form_labels",
                "severity": severity,
                "title": "Missing Form Labels",
                "description": (
                    f"Only {form_metrics.label_coverage:.0%} of form inputs have proper labels. "
                    f"{form_metrics.with_placeholders_only} inputs rely only on placeholders."
                ),
                "evidence": form_metrics.missing_labels[:10],
                "metrics": form_metrics.to_dict(),
            })

        # 4. Feedback states critique
        feedback_metrics = self.analyze_feedback_states(fingerprints, pseudo_states)
        if feedback_metrics.components_analyzed > 0:
            disabled_coverage = (
                feedback_metrics.with_disabled_state / feedback_metrics.components_analyzed
            )
            if disabled_coverage < 0.5:
                critiques.append({
                    "category": "affordance",
                    "subcategory": "feedback_states",
                    "severity": Severity.INFO,
                    "title": "Limited Feedback States",
                    "description": (
                        f"Only {feedback_metrics.with_disabled_state} of "
                        f"{feedback_metrics.components_analyzed} components have visible "
                        "disabled states. Consider adding clear state feedback."
                    ),
                    "evidence": [],
                    "metrics": feedback_metrics.to_dict(),
                })

        return critiques


__all__ = [
    "AffordanceAnalyzer",
    "FocusVisibilityMetrics",
    "TapTargetMetrics",
    "FormLayoutMetrics",
    "FeedbackStateMetrics",
]
