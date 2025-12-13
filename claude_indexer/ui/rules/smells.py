"""CSS smell rules for UI consistency checking.

This module provides rules that detect CSS code smells like
specificity escalation, !important usage, and suppressions
without rationale.
"""

import re
from typing import Any

from ..models import Finding, Severity
from .base import BaseRule, RuleContext


class SpecificityEscalationRule(BaseRule):
    """Detects CSS specificity escalation patterns.

    Finds selectors with unnecessarily high specificity that may
    indicate CSS architecture issues.
    """

    @property
    def rule_id(self) -> str:
        return "CSS.SPECIFICITY.ESCALATION"

    @property
    def category(self) -> str:
        return "smells"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def description(self) -> str:
        return "Detects CSS selectors with high specificity"

    # Specificity threshold (id=100, class=10, element=1)
    # Threshold of 30 = 3 classes or 1 ID + 2 classes
    SPECIFICITY_THRESHOLD = 30

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find selectors with high specificity."""
        findings = []

        for style in context.styles:
            # Check if style has selector info
            selector = self._get_selector(style)
            if not selector:
                continue

            specificity = self._calculate_specificity(selector)

            if specificity > self.SPECIFICITY_THRESHOLD:
                ref = None
                if hasattr(style, "source_refs") and style.source_refs:
                    ref = style.source_refs[0]

                evidence = [
                    self._create_static_evidence(
                        description=f"Selector '{selector}' has specificity {specificity}",
                        source_ref=ref,
                        data={
                            "selector": selector,
                            "specificity": specificity,
                            "breakdown": self._specificity_breakdown(selector),
                        },
                    ),
                ]

                hints = [
                    f"Specificity {specificity} exceeds threshold {self.SPECIFICITY_THRESHOLD}",
                    "Consider using fewer nested selectors or IDs",
                    "High specificity makes styles harder to override",
                ]

                findings.append(
                    self._create_finding(
                        summary=f"High specificity selector (score: {specificity})",
                        evidence=evidence,
                        config=context.config,
                        source_ref=ref,
                        confidence=0.9,
                        remediation_hints=hints,
                    )
                )

        return findings

    def _get_selector(self, style) -> str | None:
        """Get selector from style if available."""
        # Check for selector attribute
        if hasattr(style, "selector"):
            return style.selector

        # Check source_refs for name that might be selector
        if hasattr(style, "source_refs") and style.source_refs:
            name = style.source_refs[0].name
            if name and ("." in name or "#" in name):
                return name

        return None

    def _calculate_specificity(self, selector: str) -> int:
        """Calculate CSS specificity score.

        Scoring: ID = 100, class/attribute/pseudo-class = 10, element/pseudo-element = 1

        Args:
            selector: CSS selector string.

        Returns:
            Specificity score.
        """
        # Count IDs (#id)
        id_count = len(re.findall(r"#[\w-]+", selector))

        # Count classes (.class), attributes ([attr]), pseudo-classes (:pseudo)
        class_count = len(re.findall(r"\.[\w-]+", selector))
        attr_count = len(re.findall(r"\[[\w-]+", selector))
        pseudo_class_count = len(re.findall(r":(?!:)[\w-]+", selector))

        # Count elements (tag names) and pseudo-elements (::pseudo)
        # This is simplified - just count word boundaries that aren't prefixed
        element_count = len(re.findall(r"(?:^|[\s>+~])[a-zA-Z][\w-]*", selector))
        pseudo_element_count = len(re.findall(r"::[\w-]+", selector))

        return (
            id_count * 100
            + (class_count + attr_count + pseudo_class_count) * 10
            + (element_count + pseudo_element_count)
        )

    def _specificity_breakdown(self, selector: str) -> dict[str, int]:
        """Get detailed specificity breakdown."""
        return {
            "ids": len(re.findall(r"#[\w-]+", selector)),
            "classes": len(re.findall(r"\.[\w-]+", selector)),
            "attributes": len(re.findall(r"\[[\w-]+", selector)),
            "pseudo_classes": len(re.findall(r":(?!:)[\w-]+", selector)),
            "elements": len(re.findall(r"(?:^|[\s>+~])[a-zA-Z][\w-]*", selector)),
            "pseudo_elements": len(re.findall(r"::[\w-]+", selector)),
        }


class ImportantNewUsageRule(BaseRule):
    """Detects new usage of !important.

    Flags !important declarations as they often indicate CSS
    architecture problems.
    """

    @property
    def rule_id(self) -> str:
        return "IMPORTANT.NEW_USAGE"

    @property
    def category(self) -> str:
        return "smells"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def description(self) -> str:
        return "Detects usage of !important"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find !important declarations."""
        findings = []

        for style in context.styles:
            if not hasattr(style, "declaration_set"):
                continue

            important_props = []
            for prop, value in style.declaration_set.items():
                if "!important" in str(value).lower():
                    important_props.append((prop, value))

            if important_props:
                ref = None
                if hasattr(style, "source_refs") and style.source_refs:
                    ref = style.source_refs[0]

                # Check if this is in new code
                is_new = True
                if context.diff_result and ref:
                    is_new = context.is_line_in_diff(ref.file_path, ref.start_line)

                if not is_new:
                    continue  # Skip baseline !important

                evidence = []
                for prop, value in important_props[:5]:
                    evidence.append(
                        self._create_static_evidence(
                            description=f"!important in {prop}: {value}",
                            source_ref=ref,
                            data={"property": prop, "value": value},
                        )
                    )

                hints = [
                    f"Found {len(important_props)} !important declaration(s)",
                    "!important often indicates specificity problems",
                    "Consider fixing the underlying specificity issue instead",
                ]

                findings.append(
                    self._create_finding(
                        summary=f"Found !important in {len(important_props)} declaration(s)",
                        evidence=evidence,
                        config=context.config,
                        source_ref=ref,
                        confidence=0.95,
                        remediation_hints=hints,
                    )
                )

        return findings


class SuppressionNoRationaleRule(BaseRule):
    """Detects ui-quality-disable comments without rationale.

    Ensures all rule suppressions include a reason for future
    maintainability.
    """

    @property
    def rule_id(self) -> str:
        return "SUPPRESSION.NO_RATIONALE"

    @property
    def category(self) -> str:
        return "smells"

    @property
    def default_severity(self) -> Severity:
        return Severity.INFO

    @property
    def description(self) -> str:
        return "Detects suppression comments without rationale"

    # Patterns for suppression comments
    SUPPRESSION_PATTERNS = [
        r"ui-quality-disable",
        r"ui-check-disable",
        r"@ui-ignore",
        r"stylelint-disable",
        r"eslint-disable",
    ]

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find suppression comments missing rationale."""
        findings = []

        # Check source files for suppression comments
        for file_path, content in context.source_files.items():
            suppressions = self._find_suppressions(content, file_path)

            for suppression in suppressions:
                if not suppression["has_rationale"]:
                    from ..models import SymbolKind, SymbolRef, Visibility

                    ref = SymbolRef(
                        file_path=file_path,
                        start_line=suppression["line"],
                        end_line=suppression["line"],
                        kind=SymbolKind.CSS,
                        visibility=Visibility.LOCAL,
                    )

                    evidence = [
                        self._create_static_evidence(
                            description=f"Suppression without rationale: {suppression['comment'][:50]}...",
                            source_ref=ref,
                            data={
                                "pattern": suppression["pattern"],
                                "comment": suppression["comment"],
                            },
                        ),
                    ]

                    hints = [
                        "Add a rationale explaining why this rule is suppressed",
                        f"Example: {suppression['pattern']} -- Intentional: legacy code migration",
                    ]

                    findings.append(
                        self._create_finding(
                            summary="Suppression comment missing rationale",
                            evidence=evidence,
                            config=context.config,
                            source_ref=ref,
                            confidence=0.9,
                            remediation_hints=hints,
                        )
                    )

        return findings

    def _find_suppressions(
        self,
        content: str,
        file_path: str,
    ) -> list[dict[str, Any]]:
        """Find suppression comments in source content.

        Args:
            content: File content.
            file_path: Path to file.

        Returns:
            List of suppression info dicts.
        """
        suppressions = []
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            for pattern in self.SUPPRESSION_PATTERNS:
                if pattern in line.lower():
                    # Check if there's a rationale (text after -- or :)
                    has_rationale = self._has_rationale(line, pattern)

                    suppressions.append(
                        {
                            "line": line_num,
                            "pattern": pattern,
                            "comment": line.strip(),
                            "has_rationale": has_rationale,
                        }
                    )
                    break  # Only count once per line

        return suppressions

    def _has_rationale(self, line: str, pattern: str) -> bool:
        """Check if suppression comment has a rationale.

        Rationale is expected after -- or : following the pattern.
        """
        # Find position of pattern
        idx = line.lower().find(pattern)
        if idx == -1:
            return False

        # Get text after pattern
        after = line[idx + len(pattern) :]

        # Check for rationale markers
        if "--" in after:
            rationale = after.split("--", 1)[1].strip()
            return len(rationale) > 5  # Non-trivial rationale

        if ":" in after:
            parts = after.split(":", 1)
            if len(parts) > 1:
                rationale = parts[1].strip()
                return len(rationale) > 5

        return False


__all__ = [
    "SpecificityEscalationRule",
    "ImportantNewUsageRule",
    "SuppressionNoRationaleRule",
]
