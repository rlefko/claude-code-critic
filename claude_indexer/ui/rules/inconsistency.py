"""Inconsistency rules for UI consistency checking.

This module provides rules that detect outliers and inconsistencies
within UI element roles (buttons, inputs, cards, etc.).
"""

from abc import abstractmethod
from collections import Counter, defaultdict
from statistics import median
from typing import Any

from ..models import Finding, Severity
from .base import BaseRule, RuleContext


class RoleOutlierRule(BaseRule):
    """Base class for role-based outlier detection.

    Analyzes distributions of styles within a specific UI role
    and identifies outliers that deviate from the norm.
    """

    @property
    def category(self) -> str:
        return "inconsistency"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def is_fast(self) -> bool:
        return False  # Requires statistical analysis

    @property
    @abstractmethod
    def target_role(self) -> str:
        """The UI role to check (button, input, card, etc.)."""

    @property
    def min_samples(self) -> int:
        """Minimum samples needed for statistical analysis."""
        return 3

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find outliers within the target role."""
        # Filter components by role
        role_components = self._filter_by_role(context.components, self.target_role)

        if len(role_components) < self.min_samples:
            return []

        findings = []

        # Analyze distributions of key properties
        distributions = self._analyze_distributions(role_components)

        # Find statistical outliers
        for prop, dist in distributions.items():
            outliers = self._find_statistical_outliers(dist)

            for outlier_value, outlier_components in outliers.items():
                evidence = []

                # Add evidence for each outlier
                for comp in outlier_components[:3]:
                    ref = comp.source_ref if hasattr(comp, "source_ref") else None
                    evidence.append(
                        self._create_static_evidence(
                            description=f"Outlier {self.target_role} with {prop}: {outlier_value}",
                            source_ref=ref,
                            data={"property": prop, "value": outlier_value},
                        )
                    )

                # Add distribution info
                evidence.append(
                    self._create_semantic_evidence(
                        description=f"Distribution: mode={dist['mode']}, median={dist['median']}",
                        data={
                            "mode": dist["mode"],
                            "median": dist["median"],
                            "count": dist["count"],
                        },
                    )
                )

                hints = [
                    f"Most {self.target_role}s have {prop}: {dist['mode']}",
                    f"This {self.target_role} has {prop}: {outlier_value}",
                    "Consider standardizing for consistency",
                ]

                first_ref = None
                if outlier_components and hasattr(outlier_components[0], "source_ref"):
                    first_ref = outlier_components[0].source_ref

                findings.append(
                    self._create_finding(
                        summary=f"{self.target_role.title()} with outlier {prop}: {outlier_value}",
                        evidence=evidence,
                        config=context.config,
                        source_ref=first_ref,
                        confidence=0.8,
                        remediation_hints=hints,
                    )
                )

        return findings

    def _filter_by_role(self, components: list, role: str) -> list:
        """Filter components to those matching the target role."""
        filtered = []

        for comp in components:
            # Check source_ref name
            if hasattr(comp, "source_ref") and comp.source_ref:
                name = comp.source_ref.name or ""
                if role.lower() in name.lower():
                    filtered.append(comp)
                    continue

            # Check style refs for role-related classes
            if hasattr(comp, "style_refs"):
                for ref in comp.style_refs:
                    if role.lower() in ref.lower():
                        filtered.append(comp)
                        break

        return filtered

    def _analyze_distributions(
        self,
        components: list,
    ) -> dict[str, dict[str, Any]]:
        """Analyze distributions of key properties.

        Returns dict of property -> distribution info.
        """
        distributions = {}

        # Properties to analyze based on role
        props_to_check = self._get_props_to_analyze()

        for prop in props_to_check:
            values = []

            for comp in components:
                value = self._extract_property(comp, prop)
                if value is not None:
                    values.append((value, comp))

            if len(values) >= self.min_samples:
                value_counts = Counter(v for v, _ in values)
                mode = value_counts.most_common(1)[0][0] if value_counts else None

                # Try to compute numeric stats if values are numeric
                numeric_values = []
                for v, _ in values:
                    num = self._parse_numeric(v)
                    if num is not None:
                        numeric_values.append(num)

                distributions[prop] = {
                    "values": values,
                    "counts": value_counts,
                    "mode": mode,
                    "median": median(numeric_values) if numeric_values else mode,
                    "count": len(values),
                }

        return distributions

    def _get_props_to_analyze(self) -> list[str]:
        """Get properties to analyze for this role."""
        # Override in subclasses
        return ["border-radius", "padding", "font-size"]

    def _extract_property(self, component, prop: str) -> str | None:
        """Extract a property value from a component."""
        # Check style_refs for common patterns
        if hasattr(component, "style_refs"):
            for ref in component.style_refs:
                # Check for utility class patterns
                if prop == "border-radius" and "rounded" in ref:
                    return ref
                if prop == "padding" and ref.startswith(("p-", "px-", "py-")):
                    return ref
                if prop == "font-size" and ref.startswith("text-"):
                    return ref

        return None

    def _parse_numeric(self, value: str) -> float | None:
        """Try to parse a numeric value from a string."""
        import re

        # Try to extract numeric part
        match = re.search(r"[-+]?\d*\.?\d+", str(value))
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass
        return None

    def _find_statistical_outliers(
        self,
        dist: dict[str, Any],
    ) -> dict[str, list]:
        """Find values that are statistical outliers.

        Uses mode-based detection: values that appear significantly
        less frequently than the mode.
        """
        outliers = defaultdict(list)

        if not dist["counts"]:
            return dict(outliers)

        mode = dist["mode"]
        mode_count = dist["counts"].get(mode, 0)
        total = dist["count"]

        # Value is outlier if it appears much less than mode
        # and mode represents majority
        mode_ratio = mode_count / total if total > 0 else 0

        if mode_ratio < 0.5:
            # No clear consensus, don't report outliers
            return dict(outliers)

        for value, comp in dist["values"]:
            if value != mode:
                value_count = dist["counts"].get(value, 0)
                # Outlier if significantly rarer than mode
                if value_count <= total * 0.2:
                    outliers[value].append(comp)

        return dict(outliers)


class ButtonOutlierRule(RoleOutlierRule):
    """Detects outlier buttons that don't match the common pattern."""

    @property
    def rule_id(self) -> str:
        return "ROLE.OUTLIER.BUTTON"

    @property
    def target_role(self) -> str:
        return "button"

    @property
    def description(self) -> str:
        return "Detects buttons with inconsistent styling"

    def _get_props_to_analyze(self) -> list[str]:
        return ["border-radius", "padding", "font-size", "font-weight"]


class InputOutlierRule(RoleOutlierRule):
    """Detects outlier inputs that don't match the common pattern."""

    @property
    def rule_id(self) -> str:
        return "ROLE.OUTLIER.INPUT"

    @property
    def target_role(self) -> str:
        return "input"

    @property
    def description(self) -> str:
        return "Detects inputs with inconsistent styling"

    def _get_props_to_analyze(self) -> list[str]:
        return ["border-radius", "padding", "border-width", "height"]


class CardOutlierRule(RoleOutlierRule):
    """Detects outlier cards that don't match the common pattern."""

    @property
    def rule_id(self) -> str:
        return "ROLE.OUTLIER.CARD"

    @property
    def target_role(self) -> str:
        return "card"

    @property
    def description(self) -> str:
        return "Detects cards with inconsistent styling"

    def _get_props_to_analyze(self) -> list[str]:
        return ["border-radius", "padding", "box-shadow"]


class FocusRingInconsistentRule(BaseRule):
    """Detects inconsistent focus ring styling.

    Ensures interactive elements have consistent focus indicators
    for accessibility.
    """

    @property
    def rule_id(self) -> str:
        return "FOCUS.RING.INCONSISTENT"

    @property
    def category(self) -> str:
        return "inconsistency"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def is_fast(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return "Detects inconsistent focus ring styling"

    # Interactive element indicators
    INTERACTIVE_PATTERNS = [
        "button",
        "btn",
        "input",
        "select",
        "checkbox",
        "radio",
        "link",
        "clickable",
        "interactive",
    ]

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find interactive elements with inconsistent focus styling."""
        findings = []

        # Filter to interactive components
        interactive = []
        for comp in context.components:
            if self._is_interactive(comp):
                interactive.append(comp)

        if len(interactive) < 2:
            return []

        # Analyze focus-related styling
        focus_styles = []
        for comp in interactive:
            focus_style = self._extract_focus_style(comp)
            if focus_style:
                focus_styles.append((focus_style, comp))

        if len(focus_styles) < 2:
            return []

        # Group by focus style
        style_groups = defaultdict(list)
        for style, comp in focus_styles:
            style_groups[style].append(comp)

        # If there's no clear majority, report inconsistency
        if len(style_groups) > 1:
            total = len(focus_styles)
            largest_group = max(len(comps) for comps in style_groups.values())

            # If largest group is less than 60% of total, report
            if largest_group / total < 0.6:
                evidence = []

                for style, comps in list(style_groups.items())[:3]:
                    ref = (
                        comps[0].source_ref if hasattr(comps[0], "source_ref") else None
                    )
                    evidence.append(
                        self._create_static_evidence(
                            description=f"{len(comps)} elements with focus style: {style}",
                            source_ref=ref,
                            data={"focus_style": style, "count": len(comps)},
                        )
                    )

                hints = [
                    f"Found {len(style_groups)} different focus ring styles",
                    "Standardize focus indicators for better accessibility",
                ]

                findings.append(
                    self._create_finding(
                        summary=f"Inconsistent focus ring styling ({len(style_groups)} variants)",
                        evidence=evidence,
                        config=context.config,
                        confidence=0.75,
                        remediation_hints=hints,
                    )
                )

        return findings

    def _is_interactive(self, component) -> bool:
        """Check if component is interactive."""
        # Check name
        if hasattr(component, "source_ref") and component.source_ref:
            name = (component.source_ref.name or "").lower()
            if any(p in name for p in self.INTERACTIVE_PATTERNS):
                return True

        # Check style refs
        if hasattr(component, "style_refs"):
            for ref in component.style_refs:
                if any(p in ref.lower() for p in self.INTERACTIVE_PATTERNS):
                    return True

        return False

    def _extract_focus_style(self, component) -> str | None:
        """Extract focus-related styling from component."""
        if not hasattr(component, "style_refs"):
            return None

        focus_classes = []
        for ref in component.style_refs:
            ref_lower = ref.lower()
            if "focus" in ref_lower or "ring" in ref_lower or "outline" in ref_lower:
                focus_classes.append(ref)

        if focus_classes:
            return " ".join(sorted(focus_classes))

        return None


__all__ = [
    "RoleOutlierRule",
    "ButtonOutlierRule",
    "InputOutlierRule",
    "CardOutlierRule",
    "FocusRingInconsistentRule",
]
