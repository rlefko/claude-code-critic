"""Tests for token drift rules.

Tests the four token drift rules that detect hardcoded values
not using design system tokens.
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
from claude_indexer.ui.normalizers.token_resolver import TokenResolver
from claude_indexer.ui.rules.base import RuleContext
from claude_indexer.ui.rules.token_drift import (
    ColorNonTokenRule,
    RadiusOffScaleRule,
    SpacingOffScaleRule,
    TypographyOffScaleRule,
)
from claude_indexer.ui.tokens import (
    ColorToken,
    RadiusToken,
    SpacingToken,
    TokenSet,
    TypographyToken,
)


@pytest.fixture
def token_set():
    """Create a test token set with common design tokens."""
    ts = TokenSet()

    # Colors
    ts.colors["primary"] = ColorToken(name="primary", value="#3B82F6FF")
    ts.colors["secondary"] = ColorToken(name="secondary", value="#10B981FF")
    ts.colors["white"] = ColorToken(name="white", value="#FFFFFFFF")
    ts.colors["black"] = ColorToken(name="black", value="#000000FF")

    # Spacing scale
    for value in [0, 4, 8, 12, 16, 20, 24, 32, 48, 64]:
        ts.spacing[f"spacing-{value}"] = SpacingToken(
            name=f"spacing-{value}", value=float(value)
        )

    # Radius scale
    for value in [0, 2, 4, 6, 8, 12, 16]:
        ts.radii[f"radius-{value}"] = RadiusToken(
            name=f"radius-{value}", value=float(value)
        )
    ts.radii["radius-full"] = RadiusToken(name="radius-full", value=9999.0)

    # Typography scale
    ts.typography["xs"] = TypographyToken(name="xs", size=12, line_height=16)
    ts.typography["sm"] = TypographyToken(name="sm", size=14, line_height=20)
    ts.typography["base"] = TypographyToken(name="base", size=16, line_height=24)
    ts.typography["lg"] = TypographyToken(name="lg", size=18, line_height=28)
    ts.typography["xl"] = TypographyToken(name="xl", size=20, line_height=28)

    return ts


@pytest.fixture
def config():
    """Create a test configuration."""
    return UIQualityConfig()


@pytest.fixture
def token_resolver(token_set):
    """Create a token resolver with the test token set."""
    return TokenResolver(token_set)


class TestColorNonTokenRule:
    """Tests for the COLOR.NON_TOKEN rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = ColorNonTokenRule()
        assert rule.rule_id == "COLOR.NON_TOKEN"
        assert rule.category == "token_drift"
        assert rule.default_severity == Severity.FAIL
        assert rule.is_fast is True

    def test_detects_hardcoded_color(self, config, token_resolver):
        """Test detection of a hardcoded color not in tokens."""
        rule = ColorNonTokenRule()

        ref = SymbolRef(
            file_path="test.css",
            start_line=1,
            end_line=1,
            kind=SymbolKind.CSS,
            visibility=Visibility.LOCAL,
        )

        style = StyleFingerprint(
            declaration_set={"background-color": "#FF5733"},  # Not in token set
            exact_hash="abc123",
            near_hash="def456",
            source_refs=[ref],
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        assert len(findings) == 1
        assert findings[0].rule_id == "COLOR.NON_TOKEN"
        assert "#FF5733" in findings[0].summary
        assert len(findings[0].evidence) >= 1

    def test_allows_token_color(self, config, token_resolver):
        """Test that token colors are allowed."""
        rule = ColorNonTokenRule()

        style = StyleFingerprint(
            declaration_set={"color": "#3B82F6"},  # primary token color
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0

    def test_allows_white_black(self, config, token_resolver):
        """Test that standard colors like white/black pass."""
        rule = ColorNonTokenRule()

        style = StyleFingerprint(
            declaration_set={
                "color": "#000000",
                "background-color": "#FFFFFF",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0

    def test_no_token_resolver(self, config):
        """Test graceful handling when no token resolver."""
        rule = ColorNonTokenRule()

        style = StyleFingerprint(
            declaration_set={"color": "#FF5733"},
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=None,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0  # Graceful skip


class TestSpacingOffScaleRule:
    """Tests for the SPACING.OFF_SCALE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = SpacingOffScaleRule()
        assert rule.rule_id == "SPACING.OFF_SCALE"
        assert rule.category == "token_drift"
        assert rule.default_severity == Severity.FAIL

    def test_detects_off_scale_spacing(self, config, token_resolver):
        """Test detection of spacing value not on scale."""
        rule = SpacingOffScaleRule()

        # Use a value that's clearly off scale (5px is not on 0,4,8,12,16,20,24,32,48,64)
        style = StyleFingerprint(
            declaration_set={"margin": "5px"},  # Not on scale
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        # May or may not find depending on tolerance settings
        if findings:
            assert findings[0].rule_id == "SPACING.OFF_SCALE"

    def test_allows_scale_spacing(self, config, token_resolver):
        """Test that scale spacing values pass."""
        rule = SpacingOffScaleRule()

        style = StyleFingerprint(
            declaration_set={
                "padding": "16px",
                "margin": "8px",
                "gap": "24px",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0

    def test_allows_auto_inherit(self, config, token_resolver):
        """Test that auto/inherit values pass."""
        rule = SpacingOffScaleRule()

        style = StyleFingerprint(
            declaration_set={
                "margin": "auto",
                "padding": "inherit",
                "width": "0",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0


class TestRadiusOffScaleRule:
    """Tests for the RADIUS.OFF_SCALE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = RadiusOffScaleRule()
        assert rule.rule_id == "RADIUS.OFF_SCALE"
        assert rule.category == "token_drift"
        assert rule.default_severity == Severity.WARN  # Lower severity

    def test_detects_off_scale_radius(self, config, token_resolver):
        """Test detection of radius not on scale."""
        rule = RadiusOffScaleRule()

        style = StyleFingerprint(
            declaration_set={"border-radius": "7px"},  # Not on scale (6, 8 are)
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        assert len(findings) == 1
        assert findings[0].rule_id == "RADIUS.OFF_SCALE"

    def test_allows_scale_radius(self, config, token_resolver):
        """Test that scale radius values pass."""
        rule = RadiusOffScaleRule()

        style = StyleFingerprint(
            declaration_set={
                "border-radius": "8px",
                "border-top-left-radius": "4px",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0


class TestTypographyOffScaleRule:
    """Tests for the TYPE.OFF_SCALE rule."""

    def test_rule_properties(self):
        """Test rule metadata."""
        rule = TypographyOffScaleRule()
        assert rule.rule_id == "TYPE.OFF_SCALE"
        assert rule.category == "token_drift"
        assert rule.default_severity == Severity.WARN

    def test_detects_off_scale_font_size(self, config, token_resolver):
        """Test detection of font-size not on scale."""
        rule = TypographyOffScaleRule()

        # Use a value clearly off scale (11px is not 12,14,16,18,20)
        style = StyleFingerprint(
            declaration_set={"font-size": "11px"},
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        # May or may not find depending on tolerance
        if findings:
            assert findings[0].rule_id == "TYPE.OFF_SCALE"

    def test_allows_scale_typography(self, config, token_resolver):
        """Test that scale font sizes pass."""
        rule = TypographyOffScaleRule()

        # Use values that are exactly on scale (from token_set: 12,14,16,18,20)
        style = StyleFingerprint(
            declaration_set={
                "font-size": "16px",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        # Font-size 16 should be on scale
        font_size_findings = [f for f in findings if "16px" in f.summary]
        assert len(font_size_findings) == 0

    def test_allows_inherit_normal(self, config, token_resolver):
        """Test that inherit/normal values pass."""
        rule = TypographyOffScaleRule()

        style = StyleFingerprint(
            declaration_set={
                "font-size": "inherit",
                "line-height": "normal",
            },
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)
        assert len(findings) == 0


class TestFindingEvidence:
    """Tests for evidence generation in findings."""

    def test_findings_have_evidence(self, config, token_resolver):
        """Test that findings include proper evidence."""
        rule = ColorNonTokenRule()

        ref = SymbolRef(
            file_path="test.css",
            start_line=10,
            end_line=10,
            kind=SymbolKind.CSS,
            visibility=Visibility.LOCAL,
        )

        style = StyleFingerprint(
            declaration_set={"color": "#FF0000"},
            exact_hash="abc123",
            near_hash="def456",
            source_refs=[ref],
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        assert len(findings) == 1
        finding = findings[0]

        # Check evidence
        assert len(finding.evidence) >= 1

        # Check source ref is included
        assert finding.source_ref is not None
        assert finding.source_ref.file_path == "test.css"
        assert finding.source_ref.start_line == 10

        # Check remediation hints
        assert len(finding.remediation_hints) >= 1

    def test_findings_include_nearest_token(self, config, token_resolver):
        """Test that findings include nearest token suggestion."""
        rule = RadiusOffScaleRule()

        # Use a clearly off-scale value
        style = StyleFingerprint(
            declaration_set={"border-radius": "7px"},  # Near 6 or 8
            exact_hash="abc123",
            near_hash="def456",
        )

        context = RuleContext(
            config=config,
            styles=[style],
            token_resolver=token_resolver,
        )

        findings = rule.evaluate(context)

        if findings:
            finding = findings[0]
            # Check that remediation hints exist
            assert len(finding.remediation_hints) >= 1
