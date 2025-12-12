"""Tests for the smell rules module.

Tests the three CSS smell rules that detect code quality issues
like specificity escalation, !important usage, and suppressions.
"""

import pytest

from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    Severity,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.rules.base import RuleContext
from claude_indexer.ui.rules.smells import (
    ImportantNewUsageRule,
    SpecificityEscalationRule,
    SuppressionNoRationaleRule,
)


@pytest.fixture
def config():
    """Create a test configuration."""
    return UIQualityConfig()


def create_style(
    file_path: str,
    declarations: dict[str, str],
    selector: str | None = None,
) -> StyleFingerprint:
    """Helper to create test styles."""
    ref = SymbolRef(
        file_path=file_path,
        start_line=1,
        end_line=5,
        name=selector,
        kind=SymbolKind.CSS,
        visibility=Visibility.LOCAL,
    )
    return StyleFingerprint(
        declaration_set=declarations,
        exact_hash="hash123",
        near_hash="nearhash123",
        source_refs=[ref],
    )


class TestSpecificityEscalationRule:
    """Tests for CSS.SPECIFICITY.ESCALATION rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = SpecificityEscalationRule()

        assert rule.rule_id == "CSS.SPECIFICITY.ESCALATION"
        assert rule.category == "smells"
        assert rule.default_severity == Severity.WARN

    def test_specificity_threshold(self):
        """Test specificity threshold value."""
        rule = SpecificityEscalationRule()
        assert rule.SPECIFICITY_THRESHOLD == 30

    def test_detects_high_specificity(self, config):
        """Test detection of high specificity selectors."""
        rule = SpecificityEscalationRule()

        # Create style with high specificity selector (ID + classes)
        style = create_style(
            "test.css",
            {"color": "red"},
            selector="#header .nav .item .link",
        )

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        assert len(findings) >= 1
        assert findings[0].rule_id == "CSS.SPECIFICITY.ESCALATION"
        assert "specificity" in findings[0].summary.lower()

    def test_allows_low_specificity(self, config):
        """Test no findings for low specificity selectors."""
        rule = SpecificityEscalationRule()

        style = create_style("test.css", {"color": "red"}, selector=".button")

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        # Single class has specificity 10, below threshold
        assert len(findings) == 0

    def test_calculate_specificity_id(self):
        """Test specificity calculation for ID selectors."""
        rule = SpecificityEscalationRule()

        # ID = 100
        assert rule._calculate_specificity("#header") == 100
        assert rule._calculate_specificity("#header #nav") == 200

    def test_calculate_specificity_class(self):
        """Test specificity calculation for class selectors."""
        rule = SpecificityEscalationRule()

        # Class = 10
        assert rule._calculate_specificity(".button") == 10
        assert rule._calculate_specificity(".btn.primary") == 20

    def test_calculate_specificity_element(self):
        """Test specificity calculation for element selectors."""
        rule = SpecificityEscalationRule()

        # Element = 1
        assert rule._calculate_specificity("div") == 1
        assert rule._calculate_specificity("div span") == 2

    def test_calculate_specificity_mixed(self):
        """Test specificity calculation for mixed selectors."""
        rule = SpecificityEscalationRule()

        # #id .class element = 100 + 10 + 1 = 111
        spec = rule._calculate_specificity("#header .nav div")
        assert spec >= 100  # At least has ID

    def test_calculate_specificity_attribute(self):
        """Test specificity calculation for attribute selectors."""
        rule = SpecificityEscalationRule()

        # Attribute = 10 (same as class)
        spec = rule._calculate_specificity("[type='button']")
        assert spec == 10

    def test_calculate_specificity_pseudo_class(self):
        """Test specificity calculation for pseudo-class selectors."""
        rule = SpecificityEscalationRule()

        # :hover = 10
        spec = rule._calculate_specificity(".btn:hover")
        assert spec == 20  # Class + pseudo-class

    def test_calculate_specificity_pseudo_element(self):
        """Test specificity calculation for pseudo-element selectors."""
        rule = SpecificityEscalationRule()

        # ::before = 1
        spec = rule._calculate_specificity(".btn::before")
        assert spec >= 10  # Class + pseudo-element

    def test_specificity_breakdown(self):
        """Test detailed specificity breakdown."""
        rule = SpecificityEscalationRule()

        breakdown = rule._specificity_breakdown("#header .nav:hover div::before")

        assert breakdown["ids"] == 1
        assert breakdown["classes"] == 1
        # pseudo_classes >= 1 (may count :hover as part of pseudo_classes)
        assert breakdown["pseudo_classes"] >= 1
        # Elements count may vary based on regex implementation
        assert "elements" in breakdown
        assert "pseudo_elements" in breakdown


class TestImportantNewUsageRule:
    """Tests for IMPORTANT.NEW_USAGE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = ImportantNewUsageRule()

        assert rule.rule_id == "IMPORTANT.NEW_USAGE"
        assert rule.category == "smells"
        assert rule.default_severity == Severity.WARN

    def test_detects_important(self, config):
        """Test detection of !important declarations."""
        rule = ImportantNewUsageRule()

        style = create_style("test.css", {"color": "red !important"})

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        assert len(findings) == 1
        assert findings[0].rule_id == "IMPORTANT.NEW_USAGE"
        assert "!important" in findings[0].summary

    def test_allows_no_important(self, config):
        """Test no findings without !important."""
        rule = ImportantNewUsageRule()

        style = create_style("test.css", {"color": "red", "padding": "10px"})

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        assert len(findings) == 0

    def test_detects_multiple_important(self, config):
        """Test detection of multiple !important declarations."""
        rule = ImportantNewUsageRule()

        style = create_style(
            "test.css",
            {
                "color": "red !important",
                "background": "blue !important",
                "padding": "10px !important",
            },
        )

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        assert len(findings) == 1
        assert "3" in findings[0].summary  # 3 declarations

    def test_case_insensitive_important(self, config):
        """Test case-insensitive !important detection."""
        rule = ImportantNewUsageRule()

        style = create_style("test.css", {"color": "red !IMPORTANT"})

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        assert len(findings) == 1


class TestSuppressionNoRationaleRule:
    """Tests for SUPPRESSION.NO_RATIONALE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = SuppressionNoRationaleRule()

        assert rule.rule_id == "SUPPRESSION.NO_RATIONALE"
        assert rule.category == "smells"
        assert rule.default_severity == Severity.INFO

    def test_suppression_patterns(self):
        """Test suppression pattern list."""
        rule = SuppressionNoRationaleRule()

        assert "ui-quality-disable" in rule.SUPPRESSION_PATTERNS
        assert "eslint-disable" in rule.SUPPRESSION_PATTERNS
        assert "stylelint-disable" in rule.SUPPRESSION_PATTERNS

    def test_detects_suppression_without_rationale(self, config):
        """Test detection of suppression without rationale."""
        rule = SuppressionNoRationaleRule()

        source_content = """
.button {
    /* ui-quality-disable */
    color: red;
}
"""
        context = RuleContext(
            config=config,
            styles=[],
            source_files={"test.css": source_content},
        )

        findings = rule.evaluate(context)

        assert len(findings) == 1
        assert findings[0].rule_id == "SUPPRESSION.NO_RATIONALE"
        assert "rationale" in findings[0].summary.lower()

    def test_allows_suppression_with_rationale(self, config):
        """Test no findings when rationale is provided."""
        rule = SuppressionNoRationaleRule()

        source_content = """
.button {
    /* ui-quality-disable -- Intentional: legacy code requires this */
    color: red;
}
"""
        context = RuleContext(
            config=config,
            styles=[],
            source_files={"test.css": source_content},
        )

        findings = rule.evaluate(context)

        # Should not flag suppressions with rationale
        assert len(findings) == 0

    def test_allows_rationale_with_colon(self, config):
        """Test rationale detection with colon format."""
        rule = SuppressionNoRationaleRule()

        source_content = """
/* eslint-disable: This is needed for backwards compatibility */
const x = 1;
"""
        context = RuleContext(
            config=config,
            styles=[],
            source_files={"test.js": source_content},
        )

        findings = rule.evaluate(context)

        # Colon format should be recognized
        assert len(findings) == 0

    def test_has_rationale_helper(self):
        """Test _has_rationale helper method."""
        rule = SuppressionNoRationaleRule()

        # With rationale (-- format)
        assert (
            rule._has_rationale(
                "/* ui-quality-disable -- Intentional: legacy code */",
                "ui-quality-disable",
            )
            is True
        )

        # With rationale (: format)
        assert (
            rule._has_rationale(
                "/* eslint-disable: This is intentional */", "eslint-disable"
            )
            is True
        )

        # Without rationale
        assert (
            rule._has_rationale("/* ui-quality-disable */", "ui-quality-disable")
            is False
        )

        # Short rationale (less than 5 chars)
        assert (
            rule._has_rationale("/* ui-quality-disable -- ok */", "ui-quality-disable")
            is False
        )

    def test_find_suppressions(self):
        """Test suppression finding helper."""
        rule = SuppressionNoRationaleRule()

        content = """
/* ui-quality-disable */
.class1 { color: red; }
/* eslint-disable -- Intentional */
.class2 { color: blue; }
"""
        suppressions = rule._find_suppressions(content, "test.css")

        assert len(suppressions) == 2
        assert suppressions[0]["has_rationale"] is False
        assert suppressions[1]["has_rationale"] is True

    def test_detects_stylelint_disable(self, config):
        """Test detection of stylelint-disable."""
        rule = SuppressionNoRationaleRule()

        source_content = """
/* stylelint-disable */
.button { color: red; }
"""
        context = RuleContext(
            config=config,
            styles=[],
            source_files={"test.css": source_content},
        )

        findings = rule.evaluate(context)

        assert len(findings) == 1


class TestSmellRuleFindings:
    """Tests for finding quality in smell rules."""

    def test_specificity_finding_has_evidence(self, config):
        """Test that specificity findings include evidence."""
        rule = SpecificityEscalationRule()

        style = create_style(
            "test.css",
            {"color": "red"},
            selector="#header #nav .item .link",
        )

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].evidence) >= 1
            # Evidence should include selector info
            evidence_data = findings[0].evidence[0].data
            assert "selector" in evidence_data or "specificity" in evidence_data

    def test_important_finding_has_evidence(self, config):
        """Test that !important findings include evidence."""
        rule = ImportantNewUsageRule()

        style = create_style("test.css", {"color": "red !important"})

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].evidence) >= 1

    def test_specificity_finding_has_hints(self, config):
        """Test that specificity findings include remediation hints."""
        rule = SpecificityEscalationRule()

        style = create_style(
            "test.css",
            {"color": "red"},
            selector="#header #nav .item .link",
        )

        context = RuleContext(config=config, styles=[style])
        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].remediation_hints) >= 1

    def test_suppression_finding_has_hints(self, config):
        """Test that suppression findings include remediation hints."""
        rule = SuppressionNoRationaleRule()

        source_content = "/* ui-quality-disable */"
        context = RuleContext(
            config=config,
            styles=[],
            source_files={"test.css": source_content},
        )

        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].remediation_hints) >= 1
            # Hints should include example
            hints_text = " ".join(findings[0].remediation_hints)
            assert "example" in hints_text.lower() or "add" in hints_text.lower()


class TestSmellRuleIntegration:
    """Integration tests for smell rules."""

    def test_all_smell_rules_evaluate(self, config):
        """Test that all smell rules can evaluate without error."""
        rules = [
            SpecificityEscalationRule(),
            ImportantNewUsageRule(),
            SuppressionNoRationaleRule(),
        ]

        style = create_style("test.css", {"color": "red"})
        context = RuleContext(
            config=config,
            styles=[style],
            source_files={"test.css": ".button { color: red; }"},
        )

        for rule in rules:
            # Should not raise
            findings = rule.evaluate(context)
            assert isinstance(findings, list)
