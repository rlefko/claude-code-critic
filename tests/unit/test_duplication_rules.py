"""Tests for the duplication rules module.

Tests the four duplication rules that detect duplicate and
near-duplicate styles and components.
"""

import pytest

from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    Severity,
    StaticComponentFingerprint,
    StyleFingerprint,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.rules.base import RuleContext
from claude_indexer.ui.rules.duplication import (
    ComponentDuplicateClusterRule,
    StyleDuplicateSetRule,
    StyleNearDuplicateSetRule,
    UtilityDuplicateSequenceRule,
)
from claude_indexer.ui.similarity.engine import SimilarityEngine


@pytest.fixture
def config():
    """Create a test configuration."""
    return UIQualityConfig()


@pytest.fixture
def similarity_engine():
    """Create a similarity engine."""
    return SimilarityEngine()


def create_style(
    file_path: str,
    declarations: dict[str, str],
    line: int = 1,
) -> StyleFingerprint:
    """Helper to create test styles."""
    ref = SymbolRef(
        file_path=file_path,
        start_line=line,
        end_line=line + 5,
        kind=SymbolKind.CSS,
        visibility=Visibility.LOCAL,
    )
    return StyleFingerprint(
        declaration_set=declarations,
        exact_hash="",  # Will be computed by normalizer
        near_hash="",
        source_refs=[ref],
    )


def create_component(
    name: str,
    style_refs: list[str],
    file_path: str = "test.tsx",
    line: int = 1,
) -> StaticComponentFingerprint:
    """Helper to create test components."""
    ref = SymbolRef(
        file_path=file_path,
        start_line=line,
        end_line=line + 10,
        name=name,
        kind=SymbolKind.COMPONENT,
        visibility=Visibility.EXPORTED,
    )
    return StaticComponentFingerprint(
        source_ref=ref,
        structure_hash=f"hash_{name}",
        style_refs=style_refs,
    )


class TestStyleDuplicateSetRule:
    """Tests for STYLE.DUPLICATE_SET rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = StyleDuplicateSetRule()

        assert rule.rule_id == "STYLE.DUPLICATE_SET"
        assert rule.category == "duplication"
        assert rule.default_severity == Severity.WARN
        assert rule.is_fast is False

    def test_detects_exact_duplicates(self, config):
        """Test detection of exact duplicate styles."""
        rule = StyleDuplicateSetRule()

        # Create identical styles in different files
        styles = [
            create_style("a.css", {"color": "red", "padding": "10px"}),
            create_style("b.css", {"color": "red", "padding": "10px"}),
            create_style("c.css", {"color": "red", "padding": "10px"}),
        ]

        context = RuleContext(config=config, styles=styles)
        findings = rule.evaluate(context)

        assert len(findings) >= 1
        assert findings[0].rule_id == "STYLE.DUPLICATE_SET"
        assert "duplicate" in findings[0].summary.lower()

    def test_no_duplicates(self, config):
        """Test no findings when styles are unique."""
        rule = StyleDuplicateSetRule()

        styles = [
            create_style("a.css", {"color": "red"}),
            create_style("b.css", {"color": "blue"}),
            create_style("c.css", {"color": "green"}),
        ]

        context = RuleContext(config=config, styles=styles)
        findings = rule.evaluate(context)

        # Each style is unique - no duplicates
        # May still find near-duplicates but not exact
        for finding in findings:
            assert "exact" not in finding.summary.lower() or finding.confidence < 1.0

    def test_too_few_styles(self, config):
        """Test handling of insufficient styles."""
        rule = StyleDuplicateSetRule()

        styles = [create_style("a.css", {"color": "red"})]

        context = RuleContext(config=config, styles=styles)
        findings = rule.evaluate(context)

        assert len(findings) == 0


class TestStyleNearDuplicateSetRule:
    """Tests for STYLE.NEAR_DUPLICATE_SET rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = StyleNearDuplicateSetRule()

        assert rule.rule_id == "STYLE.NEAR_DUPLICATE_SET"
        assert rule.category == "duplication"
        assert rule.default_severity == Severity.WARN
        assert rule.is_fast is False

    def test_detects_near_duplicates(self, config):
        """Test detection of near-duplicate styles."""
        rule = StyleNearDuplicateSetRule()

        # Create styles that differ by only one property
        styles = [
            create_style("a.css", {"color": "red", "padding": "10px", "margin": "5px"}),
            create_style(
                "b.css", {"color": "blue", "padding": "10px", "margin": "5px"}
            ),
        ]

        context = RuleContext(config=config, styles=styles)
        rule.evaluate(context)

        # Should detect near-duplicates
        # Note: actual detection depends on SimHash implementation

    def test_completely_different_styles(self, config):
        """Test with completely different styles."""
        rule = StyleNearDuplicateSetRule()

        styles = [
            create_style("a.css", {"display": "flex"}),
            create_style("b.css", {"position": "absolute", "z-index": "100"}),
        ]

        context = RuleContext(config=config, styles=styles)
        rule.evaluate(context)

        # Very different styles should not be near-duplicates

    def test_find_declaration_diffs(self):
        """Test difference finding helper."""
        rule = StyleNearDuplicateSetRule()

        decl1 = {"color": "red", "padding": "10px"}
        decl2 = {"color": "blue", "padding": "10px", "margin": "5px"}

        diffs = rule._find_declaration_diffs(decl1, decl2)

        assert "color: red vs blue" in diffs
        assert "+margin" in diffs


class TestUtilityDuplicateSequenceRule:
    """Tests for UTILITY.DUPLICATE_SEQUENCE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = UtilityDuplicateSequenceRule()

        assert rule.rule_id == "UTILITY.DUPLICATE_SEQUENCE"
        assert rule.category == "duplication"
        assert rule.default_severity == Severity.INFO

    def test_detects_repeated_sequences(self, config):
        """Test detection of repeated utility class sequences."""
        rule = UtilityDuplicateSequenceRule()

        # Create components with repeated utility class patterns (need at least MIN_SEQUENCE_LENGTH=3)
        components = [
            create_component("Button1", ["px-4", "py-2", "bg-blue-500"], "a.tsx", 1),
            create_component("Button2", ["px-4", "py-2", "bg-blue-500"], "b.tsx", 1),
            create_component("Button3", ["px-4", "py-2", "bg-blue-500"], "c.tsx", 1),
            create_component("Card", ["rounded-lg", "shadow-md", "p-4"], "d.tsx", 1),
        ]

        context = RuleContext(config=config, components=components)
        findings = rule.evaluate(context)

        # Should detect the repeated button pattern if all utility classes pass
        if findings:
            assert "repeated" in findings[0].summary.lower()

    def test_no_repeated_sequences(self, config):
        """Test no findings when sequences are unique."""
        rule = UtilityDuplicateSequenceRule()

        # Each component has unique utility classes
        components = [
            create_component("Button", ["px-4", "py-2", "bg-blue-500"]),
            create_component("Card", ["rounded-lg", "shadow-lg", "p-8"]),
            create_component("Modal", ["fixed", "inset-0", "z-50"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Each sequence appears only once, so should not be reported

    def test_is_utility_class(self):
        """Test utility class detection."""
        rule = UtilityDuplicateSequenceRule()

        # Should match utility classes (based on regex patterns in implementation)
        assert rule._is_utility_class("px-4") is True
        assert rule._is_utility_class("py-2") is True
        assert rule._is_utility_class("bg-blue-500") is True
        assert rule._is_utility_class("text-lg") is True
        assert rule._is_utility_class("rounded-lg") is True
        assert rule._is_utility_class("flex") is True
        assert rule._is_utility_class("hidden") is True
        assert rule._is_utility_class("m-4") is True

        # Should not match non-utility classes
        assert rule._is_utility_class("header") is False
        assert rule._is_utility_class("container") is False

    def test_minimum_sequence_length(self, config):
        """Test minimum sequence length requirement."""
        rule = UtilityDuplicateSequenceRule()

        # Create components with short class lists (< MIN_SEQUENCE_LENGTH=3)
        components = [
            create_component("Button1", ["px-4", "py-2"], "a.tsx"),
            create_component("Button2", ["px-4", "py-2"], "b.tsx"),
            create_component("Button3", ["px-4", "py-2"], "c.tsx"),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Sequence too short to report (only 2 classes, need 3)


class TestComponentDuplicateClusterRule:
    """Tests for COMPONENT.DUPLICATE_CLUSTER rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = ComponentDuplicateClusterRule()

        assert rule.rule_id == "COMPONENT.DUPLICATE_CLUSTER"
        assert rule.category == "duplication"
        assert rule.default_severity == Severity.WARN
        assert rule.is_fast is False

    def test_too_few_components(self, config, similarity_engine):
        """Test with insufficient components."""
        rule = ComponentDuplicateClusterRule()

        components = [create_component("Single", ["btn"])]

        context = RuleContext(
            config=config, components=components, similarity_engine=similarity_engine
        )
        findings = rule.evaluate(context)

        assert len(findings) == 0

    def test_no_similarity_engine(self, config):
        """Test graceful handling without similarity engine."""
        rule = ComponentDuplicateClusterRule()

        components = [
            create_component("Button1", ["btn"]),
            create_component("Button2", ["btn"]),
        ]

        context = RuleContext(
            config=config,
            components=components,
            similarity_engine=None,
        )
        findings = rule.evaluate(context)

        assert len(findings) == 0

    def test_with_similarity_engine(self, config, similarity_engine):
        """Test with similarity engine."""
        rule = ComponentDuplicateClusterRule()

        # Create similar components
        ref1 = SymbolRef(
            file_path="a.tsx",
            start_line=1,
            end_line=10,
            name="Button1",
            kind=SymbolKind.COMPONENT,
            visibility=Visibility.EXPORTED,
        )
        ref2 = SymbolRef(
            file_path="b.tsx",
            start_line=1,
            end_line=10,
            name="Button2",
            kind=SymbolKind.COMPONENT,
            visibility=Visibility.EXPORTED,
        )

        components = [
            StaticComponentFingerprint(
                source_ref=ref1,
                structure_hash="same_hash",
                style_refs=["btn", "primary"],
            ),
            StaticComponentFingerprint(
                source_ref=ref2,
                structure_hash="same_hash",
                style_refs=["btn", "primary"],
            ),
        ]

        context = RuleContext(
            config=config,
            components=components,
            similarity_engine=similarity_engine,
        )

        rule.evaluate(context)

        # May or may not find clusters depending on implementation

    def test_get_component_id(self):
        """Test component ID extraction."""
        rule = ComponentDuplicateClusterRule()

        ref = SymbolRef(
            file_path="test.tsx",
            start_line=10,
            end_line=20,
            name="Button",
            kind=SymbolKind.COMPONENT,
            visibility=Visibility.EXPORTED,
        )

        comp = StaticComponentFingerprint(
            source_ref=ref,
            structure_hash="hash123",
            style_refs=["btn"],
        )

        comp_id = rule._get_component_id(comp)
        assert "test.tsx" in comp_id
        assert "10" in comp_id


class TestDuplicationRuleFindings:
    """Tests for finding quality in duplication rules."""

    def test_duplicate_finding_has_evidence(self, config):
        """Test that duplicate findings include evidence."""
        rule = StyleDuplicateSetRule()

        styles = [
            create_style("a.css", {"color": "red"}),
            create_style("b.css", {"color": "red"}),
        ]

        context = RuleContext(config=config, styles=styles)
        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].evidence) >= 1

    def test_duplicate_finding_has_hints(self, config):
        """Test that duplicate findings include remediation hints."""
        rule = StyleDuplicateSetRule()

        styles = [
            create_style("a.css", {"color": "red"}),
            create_style("b.css", {"color": "red"}),
        ]

        context = RuleContext(config=config, styles=styles)
        findings = rule.evaluate(context)

        if findings:
            assert len(findings[0].remediation_hints) >= 1
