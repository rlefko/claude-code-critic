"""Token drift rules for UI consistency checking.

This module provides rules that detect hardcoded values that should
be using design system tokens instead.
"""

from ..models import (
    Finding,
    Severity,
)
from ..normalizers.token_resolver import ResolutionStatus, TokenCategory
from .base import BaseRule, RuleContext


class ColorNonTokenRule(BaseRule):
    """Detects hardcoded colors not in the design system.

    Finds color values that don't match any defined color token,
    indicating potential token drift.
    """

    @property
    def rule_id(self) -> str:
        return "COLOR.NON_TOKEN"

    @property
    def category(self) -> str:
        return "token_drift"

    @property
    def default_severity(self) -> Severity:
        return Severity.FAIL

    @property
    def description(self) -> str:
        return "Detects hardcoded colors that should use design tokens"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find colors that don't resolve to tokens."""
        if context.token_resolver is None:
            return []

        findings = []

        for style in context.styles:
            if not hasattr(style, "declaration_set"):
                continue

            for prop, value in style.declaration_set.items():
                category = context.token_resolver.categorize_property(prop)
                if category != TokenCategory.COLOR:
                    continue

                resolution = context.token_resolver.resolve_color(value)

                if resolution.status == ResolutionStatus.OFF_SCALE:
                    # Create source reference if available
                    source_ref = None
                    if hasattr(style, "source_refs") and style.source_refs:
                        source_ref = style.source_refs[0]

                    # Create evidence
                    evidence = [
                        self._create_static_evidence(
                            description=f"Hardcoded color '{value}' in property '{prop}'",
                            source_ref=source_ref,
                            data={
                                "property": prop,
                                "value": value,
                                "normalized": resolution.normalized_value,
                            },
                        ),
                    ]

                    # Add semantic evidence if there's a nearest token
                    if resolution.nearest_token:
                        evidence.append(
                            self._create_semantic_evidence(
                                description=f"Nearest token: '{resolution.nearest_token}'",
                                similarity_score=1.0 - resolution.distance,
                                data={
                                    "nearest_token": resolution.nearest_token,
                                    "distance": resolution.distance,
                                },
                            )
                        )

                    # Build remediation hints
                    hints = []
                    if resolution.suggestion:
                        hints.append(resolution.suggestion)
                    else:
                        hints.append(
                            f"Use a color token from your design system instead of '{value}'"
                        )

                    findings.append(
                        self._create_finding(
                            summary=f"Color '{value}' is not a design token",
                            evidence=evidence,
                            config=context.config,
                            source_ref=source_ref,
                            confidence=0.95,
                            remediation_hints=hints,
                        )
                    )

        return findings


class SpacingOffScaleRule(BaseRule):
    """Detects spacing values not on the design scale.

    Finds margin, padding, gap, and other spacing values that
    don't align with the defined spacing scale.
    """

    @property
    def rule_id(self) -> str:
        return "SPACING.OFF_SCALE"

    @property
    def category(self) -> str:
        return "token_drift"

    @property
    def default_severity(self) -> Severity:
        return Severity.FAIL

    @property
    def description(self) -> str:
        return "Detects spacing values not on the design scale"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find spacing values that don't match the scale."""
        if context.token_resolver is None:
            return []

        findings = []

        for style in context.styles:
            if not hasattr(style, "declaration_set"):
                continue

            for prop, value in style.declaration_set.items():
                category = context.token_resolver.categorize_property(prop)
                if category != TokenCategory.SPACING:
                    continue

                # Skip auto, inherit, etc.
                if value.lower() in ("auto", "inherit", "initial", "unset", "0"):
                    continue

                resolution = context.token_resolver.resolve_spacing(value)

                if resolution.status == ResolutionStatus.OFF_SCALE:
                    source_ref = None
                    if hasattr(style, "source_refs") and style.source_refs:
                        source_ref = style.source_refs[0]

                    evidence = [
                        self._create_static_evidence(
                            description=f"Off-scale spacing '{value}' in property '{prop}'",
                            source_ref=source_ref,
                            data={
                                "property": prop,
                                "value": value,
                                "normalized": resolution.normalized_value,
                            },
                        ),
                    ]

                    if resolution.nearest_token:
                        evidence.append(
                            self._create_semantic_evidence(
                                description=f"Nearest scale value: '{resolution.nearest_token}'",
                                similarity_score=max(0, 1.0 - resolution.distance / 10),
                                data={
                                    "nearest_token": resolution.nearest_token,
                                    "distance": resolution.distance,
                                },
                            )
                        )

                    hints = []
                    if resolution.suggestion:
                        hints.append(resolution.suggestion)
                    else:
                        hints.append(
                            f"Use a spacing value from your scale instead of '{value}'"
                        )

                    findings.append(
                        self._create_finding(
                            summary=f"Spacing '{value}' is not on the scale",
                            evidence=evidence,
                            config=context.config,
                            source_ref=source_ref,
                            confidence=0.9,
                            remediation_hints=hints,
                        )
                    )

        return findings


class RadiusOffScaleRule(BaseRule):
    """Detects border-radius values not on the design scale.

    Finds radius values that don't align with the defined radius scale.
    """

    @property
    def rule_id(self) -> str:
        return "RADIUS.OFF_SCALE"

    @property
    def category(self) -> str:
        return "token_drift"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def description(self) -> str:
        return "Detects border-radius values not on the design scale"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find radius values that don't match the scale."""
        if context.token_resolver is None:
            return []

        findings = []

        for style in context.styles:
            if not hasattr(style, "declaration_set"):
                continue

            for prop, value in style.declaration_set.items():
                category = context.token_resolver.categorize_property(prop)
                if category != TokenCategory.RADIUS:
                    continue

                # Skip 0, inherit, etc.
                if value.lower() in ("0", "inherit", "initial", "unset", "none"):
                    continue

                resolution = context.token_resolver.resolve_radius(value)

                if resolution.status == ResolutionStatus.OFF_SCALE:
                    source_ref = None
                    if hasattr(style, "source_refs") and style.source_refs:
                        source_ref = style.source_refs[0]

                    evidence = [
                        self._create_static_evidence(
                            description=f"Off-scale radius '{value}' in property '{prop}'",
                            source_ref=source_ref,
                            data={
                                "property": prop,
                                "value": value,
                                "normalized": resolution.normalized_value,
                            },
                        ),
                    ]

                    if resolution.nearest_token:
                        evidence.append(
                            self._create_semantic_evidence(
                                description=f"Nearest radius token: '{resolution.nearest_token}'",
                                similarity_score=max(0, 1.0 - resolution.distance / 5),
                                data={
                                    "nearest_token": resolution.nearest_token,
                                    "distance": resolution.distance,
                                },
                            )
                        )

                    hints = []
                    if resolution.suggestion:
                        hints.append(resolution.suggestion)
                    else:
                        hints.append(
                            f"Use a border-radius value from your scale instead of '{value}'"
                        )

                    findings.append(
                        self._create_finding(
                            summary=f"Border-radius '{value}' is not on the scale",
                            evidence=evidence,
                            config=context.config,
                            source_ref=source_ref,
                            confidence=0.85,
                            remediation_hints=hints,
                        )
                    )

        return findings


class TypographyOffScaleRule(BaseRule):
    """Detects typography values not on the design scale.

    Finds font-size and line-height values that don't align with
    the defined typography scale.
    """

    @property
    def rule_id(self) -> str:
        return "TYPE.OFF_SCALE"

    @property
    def category(self) -> str:
        return "token_drift"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def description(self) -> str:
        return "Detects typography values not on the design scale"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find typography values that don't match the scale."""
        if context.token_resolver is None:
            return []

        findings = []

        for style in context.styles:
            if not hasattr(style, "declaration_set"):
                continue

            for prop, value in style.declaration_set.items():
                category = context.token_resolver.categorize_property(prop)
                if category != TokenCategory.TYPOGRAPHY:
                    continue

                # Skip inherit, etc.
                if value.lower() in ("inherit", "initial", "unset", "normal"):
                    continue

                resolution = context.token_resolver.resolve_typography(value)

                if resolution.status == ResolutionStatus.OFF_SCALE:
                    source_ref = None
                    if hasattr(style, "source_refs") and style.source_refs:
                        source_ref = style.source_refs[0]

                    evidence = [
                        self._create_static_evidence(
                            description=f"Off-scale typography '{value}' in property '{prop}'",
                            source_ref=source_ref,
                            data={
                                "property": prop,
                                "value": value,
                                "normalized": resolution.normalized_value,
                            },
                        ),
                    ]

                    if resolution.nearest_token:
                        evidence.append(
                            self._create_semantic_evidence(
                                description=f"Nearest typography token: '{resolution.nearest_token}'",
                                similarity_score=max(0, 1.0 - resolution.distance / 5),
                                data={
                                    "nearest_token": resolution.nearest_token,
                                    "distance": resolution.distance,
                                },
                            )
                        )

                    hints = []
                    if resolution.suggestion:
                        hints.append(resolution.suggestion)
                    else:
                        hints.append(
                            f"Use a typography size from your scale instead of '{value}'"
                        )

                    findings.append(
                        self._create_finding(
                            summary=f"Typography value '{value}' is not on the scale",
                            evidence=evidence,
                            config=context.config,
                            source_ref=source_ref,
                            confidence=0.85,
                            remediation_hints=hints,
                        )
                    )

        return findings


# Export all rule classes
__all__ = [
    "ColorNonTokenRule",
    "SpacingOffScaleRule",
    "RadiusOffScaleRule",
    "TypographyOffScaleRule",
]
