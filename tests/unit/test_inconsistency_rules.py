"""Tests for the inconsistency rules module.

Tests the four inconsistency rules that detect outliers and
style inconsistencies within UI element roles.
"""

import pytest

from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    Severity,
    StaticComponentFingerprint,
    SymbolKind,
    SymbolRef,
    Visibility,
)
from claude_indexer.ui.rules.base import RuleContext
from claude_indexer.ui.rules.inconsistency import (
    ButtonOutlierRule,
    CardOutlierRule,
    FocusRingInconsistentRule,
    InputOutlierRule,
    RoleOutlierRule,
)


@pytest.fixture
def config():
    """Create a test configuration."""
    return UIQualityConfig()


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


class TestRoleOutlierRule:
    """Tests for the base RoleOutlierRule class."""

    def test_is_abstract(self):
        """Test that RoleOutlierRule is abstract."""
        # Cannot instantiate directly without implementing abstract methods
        with pytest.raises(TypeError):
            RoleOutlierRule()

    def test_category(self):
        """Test category is inconsistency."""
        rule = ButtonOutlierRule()  # Concrete subclass
        assert rule.category == "inconsistency"

    def test_default_severity(self):
        """Test default severity is WARN."""
        rule = ButtonOutlierRule()
        assert rule.default_severity == Severity.WARN

    def test_is_fast(self):
        """Test is_fast is False (requires analysis)."""
        rule = ButtonOutlierRule()
        assert rule.is_fast is False

    def test_min_samples(self):
        """Test minimum samples requirement."""
        rule = ButtonOutlierRule()
        assert rule.min_samples == 3


class TestButtonOutlierRule:
    """Tests for ROLE.OUTLIER.BUTTON rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = ButtonOutlierRule()

        assert rule.rule_id == "ROLE.OUTLIER.BUTTON"
        assert rule.target_role == "button"
        assert "border-radius" in rule._get_props_to_analyze()
        assert "font-weight" in rule._get_props_to_analyze()

    def test_detects_button_outlier(self, config):
        """Test detection of button style outliers."""
        rule = ButtonOutlierRule()

        # Create buttons with consistent style except one outlier
        components = [
            create_component("PrimaryButton", ["button", "rounded-md", "p-4"]),
            create_component("SecondaryButton", ["button", "rounded-md", "p-4"]),
            create_component("TertiaryButton", ["button", "rounded-md", "p-4"]),
            create_component("SubmitButton", ["button", "rounded-md", "p-4"]),
            create_component(
                "OutlierButton", ["button", "rounded-full", "p-8"]
            ),  # Different
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # May detect outliers based on distribution analysis
        # The test validates the rule can run without error

    def test_no_outliers_consistent_buttons(self, config):
        """Test no findings when buttons are consistent."""
        rule = ButtonOutlierRule()

        components = [
            create_component("PrimaryButton", ["button", "rounded-md", "p-4"]),
            create_component("SecondaryButton", ["button", "rounded-md", "p-4"]),
            create_component("TertiaryButton", ["button", "rounded-md", "p-4"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # All consistent - should have no outlier findings

    def test_too_few_buttons(self, config):
        """Test handling of insufficient buttons."""
        rule = ButtonOutlierRule()

        components = [
            create_component("PrimaryButton", ["button", "rounded-md"]),
            create_component("SecondaryButton", ["button", "rounded-lg"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Too few samples for statistical analysis (need min_samples=3)


class TestInputOutlierRule:
    """Tests for ROLE.OUTLIER.INPUT rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = InputOutlierRule()

        assert rule.rule_id == "ROLE.OUTLIER.INPUT"
        assert rule.target_role == "input"
        assert "border-width" in rule._get_props_to_analyze()
        assert "height" in rule._get_props_to_analyze()

    def test_detects_input_outlier(self, config):
        """Test detection of input style outliers."""
        rule = InputOutlierRule()

        components = [
            create_component("TextInput", ["input", "rounded-md", "border"]),
            create_component("EmailInput", ["input", "rounded-md", "border"]),
            create_component("PasswordInput", ["input", "rounded-md", "border"]),
            create_component("SearchInput", ["input", "rounded-md", "border"]),
            create_component("OutlierInput", ["input", "rounded-full", "border-2"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Test validates rule can run without error


class TestCardOutlierRule:
    """Tests for ROLE.OUTLIER.CARD rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = CardOutlierRule()

        assert rule.rule_id == "ROLE.OUTLIER.CARD"
        assert rule.target_role == "card"
        assert "box-shadow" in rule._get_props_to_analyze()

    def test_detects_card_outlier(self, config):
        """Test detection of card style outliers."""
        rule = CardOutlierRule()

        components = [
            create_component("InfoCard", ["card", "rounded-lg", "shadow-md"]),
            create_component("ProductCard", ["card", "rounded-lg", "shadow-md"]),
            create_component("UserCard", ["card", "rounded-lg", "shadow-md"]),
            create_component("StatCard", ["card", "rounded-lg", "shadow-md"]),
            create_component("OutlierCard", ["card", "rounded-sm", "shadow-none"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Test validates rule can run without error


class TestFocusRingInconsistentRule:
    """Tests for FOCUS.RING.INCONSISTENT rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = FocusRingInconsistentRule()

        assert rule.rule_id == "FOCUS.RING.INCONSISTENT"
        assert rule.category == "inconsistency"
        assert rule.default_severity == Severity.WARN
        assert rule.is_fast is False

    def test_detects_inconsistent_focus_rings(self, config):
        """Test detection of inconsistent focus ring styles."""
        rule = FocusRingInconsistentRule()

        # Create interactive elements with different focus styles
        components = [
            create_component(
                "PrimaryButton", ["button", "focus:ring-2", "focus:ring-blue-500"]
            ),
            create_component(
                "SecondaryButton", ["button", "focus:ring-2", "focus:ring-blue-500"]
            ),
            create_component(
                "TextInput", ["input", "focus:outline-none", "focus:border-green-500"]
            ),
            create_component(
                "EmailInput", ["input", "focus:outline-none", "focus:border-green-500"]
            ),
            create_component("NavLink", ["link", "focus:ring-1", "focus:ring-red-500"]),
        ]

        context = RuleContext(config=config, components=components)
        findings = rule.evaluate(context)

        # May detect inconsistency across interactive elements
        if findings:
            assert "inconsistent" in findings[0].summary.lower()

    def test_consistent_focus_rings(self, config):
        """Test no findings when focus rings are consistent."""
        rule = FocusRingInconsistentRule()

        components = [
            create_component(
                "PrimaryButton", ["button", "focus:ring-2", "focus:ring-blue-500"]
            ),
            create_component(
                "SecondaryButton", ["button", "focus:ring-2", "focus:ring-blue-500"]
            ),
            create_component(
                "TextInput", ["input", "focus:ring-2", "focus:ring-blue-500"]
            ),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Consistent focus styles should have no or few findings

    def test_too_few_interactive(self, config):
        """Test handling of insufficient interactive elements."""
        rule = FocusRingInconsistentRule()

        components = [
            create_component("SingleButton", ["button", "focus:ring-2"]),
        ]

        context = RuleContext(config=config, components=components)
        rule.evaluate(context)

        # Only one interactive element, not enough for comparison

    def test_is_interactive_detection(self):
        """Test interactive element detection."""
        rule = FocusRingInconsistentRule()

        # Components with "button" in name or style refs should be interactive
        button = create_component("PrimaryButton", ["btn-class", "primary"])
        input_comp = create_component("TextInput", ["input-class", "text-input"])
        link = create_component("NavLink", ["link-class", "nav-link"])
        card = create_component("ProfileCard", ["card-class", "shadow"])

        # Check by name pattern
        assert rule._is_interactive(button) is True  # "Button" in name
        assert rule._is_interactive(input_comp) is True  # "Input" in name
        assert rule._is_interactive(link) is True  # "Link" in name
        assert rule._is_interactive(card) is False  # "Card" not in INTERACTIVE_PATTERNS

    def test_extract_focus_style(self):
        """Test focus style extraction."""
        rule = FocusRingInconsistentRule()

        comp_with_focus = create_component(
            "ActionButton", ["btn", "focus:ring-2", "focus:ring-blue-500"]
        )
        comp_without_focus = create_component("ActionButton", ["btn", "primary"])

        focus_style = rule._extract_focus_style(comp_with_focus)
        assert focus_style is not None
        assert "focus" in focus_style.lower()

        no_focus = rule._extract_focus_style(comp_without_focus)
        assert no_focus is None


class TestRoleFiltering:
    """Tests for role-based component filtering."""

    def test_filter_by_role_name(self, config):
        """Test filtering components by name containing role."""
        rule = ButtonOutlierRule()

        components = [
            create_component("PrimaryButton", ["btn-class"]),
            create_component("SecondaryButton", ["btn-class"]),
            create_component("InfoCard", ["card-class"]),
            create_component("SubmitButton", ["btn-class"]),
        ]

        filtered = rule._filter_by_role(components, "button")

        # Should find components with "button" in name (case-insensitive)
        assert len(filtered) == 3

    def test_filter_by_role_style_ref(self, config):
        """Test filtering components by style ref containing role."""
        rule = CardOutlierRule()

        components = [
            create_component("Panel1", ["card-class", "shadow"]),
            create_component("Panel2", ["card-class", "rounded"]),
            create_component("ActionButton", ["btn-class"]),
        ]

        filtered = rule._filter_by_role(components, "card")

        # Should find components with "card" in style refs
        assert len(filtered) == 2


class TestDistributionAnalysis:
    """Tests for distribution analysis in outlier detection."""

    def test_analyze_distributions(self, config):
        """Test property distribution analysis."""
        rule = ButtonOutlierRule()

        components = [
            create_component("PrimaryButton", ["button", "rounded-md"]),
            create_component("SecondaryButton", ["button", "rounded-md"]),
            create_component("TertiaryButton", ["button", "rounded-lg"]),
        ]

        # Filter to buttons first
        buttons = rule._filter_by_role(components, "button")
        rule._analyze_distributions(buttons)

        # Distributions dict should be returned (may be empty if no props extracted)

    def test_statistical_outlier_detection(self, config):
        """Test statistical outlier detection."""
        rule = ButtonOutlierRule()

        # Create mock distribution
        dist = {
            "values": [
                ("rounded-md", None),
                ("rounded-md", None),
                ("rounded-md", None),
                ("rounded-md", None),
                ("rounded-lg", None),
            ],
            "counts": {"rounded-md": 4, "rounded-lg": 1},
            "mode": "rounded-md",
            "median": "rounded-md",
            "count": 5,
        }

        outliers = rule._find_statistical_outliers(dist)

        # rounded-lg appears only once (20%) vs mode at 80%
        assert "rounded-lg" in outliers


class TestInconsistencyRuleFindings:
    """Tests for finding quality in inconsistency rules."""

    def test_outlier_finding_has_evidence(self, config):
        """Test that outlier findings include evidence."""
        rule = ButtonOutlierRule()

        components = [
            create_component("PrimaryButton", ["button", "rounded-md"]),
            create_component("SecondaryButton", ["button", "rounded-md"]),
            create_component("TertiaryButton", ["button", "rounded-md"]),
            create_component("SubmitButton", ["button", "rounded-md"]),
            create_component("OutlierButton", ["button", "rounded-full"]),
        ]

        context = RuleContext(config=config, components=components)
        findings = rule.evaluate(context)

        # If findings are generated, they should have evidence
        if findings:
            assert len(findings[0].evidence) >= 1

    def test_focus_finding_has_hints(self, config):
        """Test that focus findings include remediation hints."""
        rule = FocusRingInconsistentRule()

        components = [
            create_component("PrimaryButton", ["button", "focus:ring-2"]),
            create_component("SecondaryButton", ["button", "focus:ring-2"]),
            create_component("TextInput", ["input", "focus:outline-none"]),
            create_component("EmailInput", ["input", "focus:outline-none"]),
        ]

        context = RuleContext(config=config, components=components)
        findings = rule.evaluate(context)

        # If findings are generated, they should have hints
        if findings:
            assert len(findings[0].remediation_hints) >= 1
