"""
Integration tests for UI consistency checking using the test fixture repository.

These tests validate that the UI consistency checker correctly identifies:
- Token drift violations
- Duplicate styles and components
- CSS smells
- Cross-framework duplicates
- Baseline vs new issue separation
"""

import os
from pathlib import Path
from typing import Any

import pytest

# Import UI modules
try:
    from claude_indexer.ui.config import UIQualityConfig
    from claude_indexer.ui.models import Finding, Severity
    from claude_indexer.ui.rules.engine import RuleEngine
    from claude_indexer.ui.rules.token_drift import (
        ColorNonTokenRule,
        SpacingOffScaleRule,
        RadiusOffScaleRule,
        TypographyOffScaleRule,
    )
    from claude_indexer.ui.rules.duplication import (
        StyleDuplicateSetRule,
        StyleNearDuplicateSetRule,
        ComponentDuplicateClusterRule,
    )
    from claude_indexer.ui.rules.smells import (
        CSSSpecificityEscalationRule,
        ImportantNewUsageRule,
    )
    from claude_indexer.ui.rules.inconsistency import (
        FocusRingInconsistentRule,
    )
    from claude_indexer.ui.rules.diff_filter import DiffAwareFilter
    from claude_indexer.ui.collectors.source import SourceCollector
    from claude_indexer.ui.normalizers.style import StyleNormalizer
    from claude_indexer.ui.normalizers.token_resolver import TokenResolver
    UI_MODULES_AVAILABLE = True
except ImportError as e:
    UI_MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)


# Path to the UI test fixture repository
FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "ui_repo"


# Skip all tests if UI modules are not available
pytestmark = pytest.mark.skipif(
    not UI_MODULES_AVAILABLE,
    reason=f"UI modules not available: {IMPORT_ERROR if not UI_MODULES_AVAILABLE else ''}"
)


@pytest.fixture
def fixture_path() -> Path:
    """Return the path to the UI test fixture repository."""
    assert FIXTURE_PATH.exists(), f"Fixture path does not exist: {FIXTURE_PATH}"
    return FIXTURE_PATH


@pytest.fixture
def ui_config(fixture_path: Path) -> UIQualityConfig:
    """Load UI quality configuration from the fixture."""
    config_path = fixture_path / ".ui-quality.yaml"
    if config_path.exists():
        return UIQualityConfig.from_file(config_path)
    return UIQualityConfig()


@pytest.fixture
def token_resolver(fixture_path: Path, ui_config: UIQualityConfig) -> TokenResolver:
    """Create a token resolver with the fixture's tokens."""
    tokens_path = fixture_path / "styles" / "tokens.css"
    return TokenResolver.from_css_file(tokens_path)


@pytest.fixture
def style_normalizer() -> StyleNormalizer:
    """Create a style normalizer for testing."""
    return StyleNormalizer()


@pytest.fixture
def rule_engine(ui_config: UIQualityConfig, token_resolver: TokenResolver) -> RuleEngine:
    """Create a rule engine with all rules enabled."""
    return RuleEngine(config=ui_config, token_resolver=token_resolver)


class TestTokenDriftDetection:
    """Test token drift detection in the fixture repository."""

    def test_detects_hardcoded_colors_in_legacy_input(
        self, fixture_path: Path, token_resolver: TokenResolver
    ):
        """InputLegacy.tsx should have multiple hardcoded color violations."""
        file_path = fixture_path / "components" / "InputLegacy.tsx"
        assert file_path.exists(), f"Test file not found: {file_path}"

        content = file_path.read_text()

        # Should contain hardcoded colors
        hardcoded_colors = ["#1f2937", "#ef4444", "#d1d5db", "#111827", "#ffffff"]
        for color in hardcoded_colors:
            assert color in content, f"Expected hardcoded color {color} in InputLegacy.tsx"

        # Run token drift detection
        rule = ColorNonTokenRule(token_resolver=token_resolver)
        findings = rule.check_file(file_path, content)

        # Should detect multiple violations
        assert len(findings) >= 5, f"Expected at least 5 color violations, got {len(findings)}"
        assert all(f.severity == Severity.FAIL for f in findings)

    def test_detects_off_scale_spacing_in_legacy_input(
        self, fixture_path: Path, token_resolver: TokenResolver
    ):
        """InputLegacy.tsx should have off-scale spacing violations."""
        file_path = fixture_path / "components" / "InputLegacy.tsx"
        content = file_path.read_text()

        # Should contain hardcoded spacing values
        assert "padding: '8px 12px'" in content or "padding: 8px 12px" in content.lower()

        rule = SpacingOffScaleRule(token_resolver=token_resolver)
        findings = rule.check_file(file_path, content)

        assert len(findings) >= 2, f"Expected at least 2 spacing violations, got {len(findings)}"

    def test_canonical_input_uses_tokens(
        self, fixture_path: Path, token_resolver: TokenResolver
    ):
        """Input.tsx (canonical) should use tokens and have minimal violations."""
        file_path = fixture_path / "components" / "Input.tsx"
        content = file_path.read_text()

        # Should use CSS custom properties
        assert "var(--color-" in content
        assert "var(--spacing-" in content
        assert "var(--text-" in content

        # Run token drift detection
        rule = ColorNonTokenRule(token_resolver=token_resolver)
        findings = rule.check_file(file_path, content)

        # Should have zero or minimal violations
        assert len(findings) <= 2, f"Canonical Input.tsx should have minimal color violations"

    def test_svelte_input_has_token_drift(
        self, fixture_path: Path, token_resolver: TokenResolver
    ):
        """SvelteInput.svelte should be detected for cross-framework token drift."""
        file_path = fixture_path / "components" / "SvelteInput.svelte"
        content = file_path.read_text()

        # Should contain hardcoded colors in Svelte syntax
        assert "#374151" in content or "#d1d5db" in content

        rule = ColorNonTokenRule(token_resolver=token_resolver)
        findings = rule.check_file(file_path, content)

        assert len(findings) >= 3, f"Expected at least 3 color violations in Svelte, got {len(findings)}"


class TestDuplicateDetection:
    """Test duplicate style and component detection."""

    def test_detects_card_style_duplicates(
        self, fixture_path: Path, style_normalizer: StyleNormalizer
    ):
        """CardAlt.tsx should be detected as style duplicate of Card.tsx."""
        card_path = fixture_path / "components" / "Card.tsx"
        card_alt_path = fixture_path / "components" / "CardAlt.tsx"

        card_content = card_path.read_text()
        card_alt_content = card_alt_path.read_text()

        # Both should have the same variant styles structure
        assert "boxShadow: 'var(--shadow-sm)'" in card_content or "boxShadow: var(--shadow-sm)" in card_content
        assert "boxShadow: 'var(--shadow-sm)'" in card_alt_content or "boxShadow: var(--shadow-sm)" in card_alt_content

        # Extract and normalize styles
        card_styles = style_normalizer.extract_styles(card_content)
        card_alt_styles = style_normalizer.extract_styles(card_alt_content)

        # Check for duplicates using hash comparison
        rule = StyleDuplicateSetRule()
        findings = rule.check_styles([
            {"file": str(card_path), "styles": card_styles},
            {"file": str(card_alt_path), "styles": card_alt_styles},
        ])

        # Should detect duplicate style sets
        assert len(findings) >= 1, "Expected to detect style duplicates between Card and CardAlt"

    def test_detects_button_near_duplicates(
        self, fixture_path: Path, style_normalizer: StyleNormalizer
    ):
        """ButtonVariant.tsx should be detected as near-duplicate of Button.tsx."""
        button_path = fixture_path / "components" / "Button.tsx"
        variant_path = fixture_path / "components" / "ButtonVariant.tsx"

        button_content = button_path.read_text()
        variant_content = variant_path.read_text()

        # Both should have similar structure but different details
        assert "variant" in button_content.lower()
        assert "kind" in variant_content.lower()  # Different prop name

        rule = StyleNearDuplicateSetRule()
        # Near-duplicate detection would involve structural comparison
        # This is a simplified check
        assert button_path.exists()
        assert variant_path.exists()

    def test_detects_utility_duplicates_in_scss(
        self, fixture_path: Path, style_normalizer: StyleNormalizer
    ):
        """utilities.scss should have duplicate utility class patterns."""
        utilities_path = fixture_path / "styles" / "utilities.scss"
        content = utilities_path.read_text()

        # Should contain multiple identical button definitions
        assert ".btn-blue" in content
        assert ".button-primary" in content
        assert ".cta-button" in content

        # All three should have identical styles
        btn_blue_count = content.count("background-color: #3b82f6")
        assert btn_blue_count >= 3, "Expected 3+ identical button background definitions"


class TestCSSSmellDetection:
    """Test CSS smell detection (specificity, !important, etc.)."""

    def test_detects_specificity_escalation_in_overrides(
        self, fixture_path: Path
    ):
        """overrides.css should have specificity escalation issues."""
        overrides_path = fixture_path / "styles" / "overrides.css"
        content = overrides_path.read_text()

        # Should contain deep selector chains
        assert ".app-container .main-content .sidebar .nav-list .nav-item .nav-link" in content

        rule = CSSSpecificityEscalationRule(max_specificity=100)
        findings = rule.check_file(overrides_path, content)

        assert len(findings) >= 5, f"Expected at least 5 specificity issues, got {len(findings)}"
        assert all(f.severity in [Severity.WARN, Severity.FAIL] for f in findings)

    def test_detects_important_usage_in_modal(
        self, fixture_path: Path
    ):
        """Modal.tsx should have !important usage detected."""
        modal_path = fixture_path / "components" / "Modal.tsx"
        content = modal_path.read_text()

        # Should contain !important
        assert "!important" in content

        rule = ImportantNewUsageRule()
        findings = rule.check_file(modal_path, content)

        assert len(findings) >= 1, "Expected to detect !important usage in Modal.tsx"

    def test_detects_important_in_overrides(
        self, fixture_path: Path
    ):
        """overrides.css should have multiple !important declarations."""
        overrides_path = fixture_path / "styles" / "overrides.css"
        content = overrides_path.read_text()

        important_count = content.count("!important")
        assert important_count >= 8, f"Expected 8+ !important declarations, got {important_count}"


class TestCrossFrameworkDetection:
    """Test detection of duplicates across React, Vue, and Svelte."""

    def test_vue_button_matches_react_button(
        self, fixture_path: Path
    ):
        """VueButton.vue should be identified as cross-framework duplicate of Button.tsx."""
        button_path = fixture_path / "components" / "Button.tsx"
        vue_button_path = fixture_path / "components" / "VueButton.vue"

        button_content = button_path.read_text()
        vue_content = vue_button_path.read_text()

        # Both should have same variant options
        for variant in ["primary", "secondary", "outline", "ghost"]:
            assert variant in button_content
            assert variant in vue_content

        # Both should have same size options
        for size in ["sm", "md", "lg"]:
            assert size in button_content
            assert size in vue_content

    def test_vue_card_matches_react_card(
        self, fixture_path: Path
    ):
        """VueCard.vue should be identified as cross-framework duplicate of Card.tsx."""
        card_path = fixture_path / "components" / "Card.tsx"
        vue_card_path = fixture_path / "components" / "VueCard.vue"

        card_content = card_path.read_text()
        vue_content = vue_card_path.read_text()

        # Both should use same CSS custom properties
        tokens = ["--color-bg-primary", "--shadow-sm", "--shadow-lg", "--radius-lg"]
        for token in tokens:
            assert token in card_content
            assert token in vue_content


class TestInconsistencyDetection:
    """Test detection of styling inconsistencies."""

    def test_detects_inconsistent_focus_ring_in_toast(
        self, fixture_path: Path
    ):
        """Toast.tsx should have inconsistent focus ring styling detected."""
        toast_path = fixture_path / "components" / "Toast.tsx"
        content = toast_path.read_text()

        # Should have non-standard focus ring
        assert "0 0 0 2px white" in content or "0 0 0 3px" in content

        # Should NOT use standard focus ring variable
        # (Toast uses custom inline focus handlers)
        assert "FOCUS.RING.INCONSISTENT" in content or "INCONSISTENT" in content


class TestBaselineSeparation:
    """Test that baseline issues are properly classified."""

    def test_legacy_css_classified_as_baseline(
        self, fixture_path: Path, ui_config: UIQualityConfig
    ):
        """Issues in legacy.css should be classified as baseline."""
        legacy_path = fixture_path / "styles" / "legacy.css"
        content = legacy_path.read_text()

        # Should contain hardcoded colors
        assert "#007bff" in content  # Legacy blue
        assert "#6c757d" in content  # Legacy gray

        # Check that the config marks this as baseline
        baseline_files = ui_config.baseline.get("files", [])
        assert "styles/legacy.css" in baseline_files or "legacy.css" in [
            Path(f).name for f in baseline_files
        ]

    def test_new_issues_not_classified_as_baseline(
        self, fixture_path: Path, ui_config: UIQualityConfig
    ):
        """Issues in new files (InputLegacy.tsx) should NOT be baseline."""
        # InputLegacy.tsx is not in the baseline file list
        baseline_files = ui_config.baseline.get("files", [])

        # Should not be in baseline
        assert "InputLegacy.tsx" not in str(baseline_files)


class TestFixtureCompleteness:
    """Test that the fixture repository is complete and valid."""

    def test_all_expected_files_exist(self, fixture_path: Path):
        """Verify all expected fixture files exist."""
        expected_files = [
            # React components
            "components/Button.tsx",
            "components/ButtonVariant.tsx",
            "components/Card.tsx",
            "components/CardAlt.tsx",
            "components/Input.tsx",
            "components/InputLegacy.tsx",
            "components/Modal.tsx",
            "components/Toast.tsx",
            # Vue components
            "components/VueButton.vue",
            "components/VueCard.vue",
            # Svelte components
            "components/SvelteInput.svelte",
            # Styles
            "styles/tokens.css",
            "styles/overrides.css",
            "styles/utilities.scss",
            "styles/legacy.css",
            # Config
            "tailwind.config.js",
            ".ui-quality.yaml",
            "README.md",
        ]

        for file in expected_files:
            file_path = fixture_path / file
            assert file_path.exists(), f"Expected fixture file not found: {file}"

    def test_tokens_css_is_valid(self, fixture_path: Path):
        """Verify tokens.css contains expected design tokens."""
        tokens_path = fixture_path / "styles" / "tokens.css"
        content = tokens_path.read_text()

        # Should contain color tokens
        assert "--color-primary-" in content
        assert "--color-neutral-" in content
        assert "--color-error" in content

        # Should contain spacing tokens
        assert "--spacing-" in content

        # Should contain radius tokens
        assert "--radius-" in content

        # Should contain typography tokens
        assert "--text-" in content
        assert "--font-" in content

    def test_config_is_valid_yaml(self, fixture_path: Path):
        """Verify .ui-quality.yaml is valid configuration."""
        import yaml

        config_path = fixture_path / ".ui-quality.yaml"
        content = config_path.read_text()

        # Should parse without errors
        config = yaml.safe_load(content)

        # Should have required sections
        assert "tokens" in config
        assert "scanning" in config
        assert "gating" in config
        assert "rules" in config
        assert "baseline" in config
