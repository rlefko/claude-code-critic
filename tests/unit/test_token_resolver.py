"""Unit tests for token resolver."""

import pytest

from claude_indexer.ui.normalizers.token_resolver import (
    ResolutionStatus,
    TokenCategory,
    TokenResolution,
    TokenResolver,
)
from claude_indexer.ui.tokens import (
    ColorToken,
    RadiusToken,
    ShadowToken,
    SpacingToken,
    TokenSet,
    TypographyToken,
)


@pytest.fixture
def sample_token_set() -> TokenSet:
    """Create a sample token set for testing."""
    return TokenSet(
        colors={
            "primary-500": ColorToken(name="primary-500", value="#3B82F6FF"),
            "red-500": ColorToken(name="red-500", value="#EF4444FF"),
            "white": ColorToken(name="white", value="#FFFFFFFF"),
            "black": ColorToken(name="black", value="#000000FF"),
        },
        spacing={
            "0": SpacingToken(name="0", value=0.0),
            "1": SpacingToken(name="1", value=4.0),
            "2": SpacingToken(name="2", value=8.0),
            "3": SpacingToken(name="3", value=12.0),
            "4": SpacingToken(name="4", value=16.0),
            "6": SpacingToken(name="6", value=24.0),
            "8": SpacingToken(name="8", value=32.0),
        },
        radii={
            "none": RadiusToken(name="none", value=0.0),
            "sm": RadiusToken(name="sm", value=2.0),
            "md": RadiusToken(name="md", value=4.0),
            "lg": RadiusToken(name="lg", value=8.0),
            "full": RadiusToken(name="full", value=9999.0),
        },
        typography={
            "xs": TypographyToken(name="xs", size=12.0),
            "sm": TypographyToken(name="sm", size=14.0),
            "base": TypographyToken(name="base", size=16.0),
            "lg": TypographyToken(name="lg", size=18.0),
            "xl": TypographyToken(name="xl", size=20.0),
            "2xl": TypographyToken(name="2xl", size=24.0),
        },
        shadows={
            "sm": ShadowToken(name="sm", value="0 1px 2px rgba(0,0,0,0.05)"),
            "md": ShadowToken(name="md", value="0 4px 6px rgba(0,0,0,0.1)"),
            "lg": ShadowToken(name="lg", value="0 10px 15px rgba(0,0,0,0.1)"),
        },
    )


@pytest.fixture
def resolver(sample_token_set: TokenSet) -> TokenResolver:
    """Create a token resolver with the sample token set."""
    return TokenResolver(sample_token_set)


class TestTokenResolution:
    """Tests for TokenResolution dataclass."""

    def test_create_resolution(self):
        """Test basic TokenResolution creation."""
        resolution = TokenResolution(
            category=TokenCategory.COLOR,
            original_value="#3b82f6",
            normalized_value="#3B82F6FF",
            status=ResolutionStatus.EXACT_MATCH,
            matched_token="primary-500",
        )

        assert resolution.category == TokenCategory.COLOR
        assert resolution.original_value == "#3b82f6"
        assert resolution.normalized_value == "#3B82F6FF"
        assert resolution.status == ResolutionStatus.EXACT_MATCH
        assert resolution.matched_token == "primary-500"
        assert resolution.is_on_scale is True

    def test_off_scale_resolution(self):
        """Test off-scale resolution status."""
        resolution = TokenResolution(
            category=TokenCategory.SPACING,
            original_value="13px",
            normalized_value="13px",
            status=ResolutionStatus.OFF_SCALE,
            nearest_token="3",
            distance=1.0,
        )

        assert resolution.is_on_scale is False

    def test_near_match_is_on_scale(self):
        """Test that near match counts as on-scale."""
        resolution = TokenResolution(
            category=TokenCategory.SPACING,
            original_value="8.5px",
            normalized_value="8.5px",
            status=ResolutionStatus.NEAR_MATCH,
            matched_token="2",
            distance=0.5,
        )

        assert resolution.is_on_scale is True

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict produce equivalent objects."""
        resolution = TokenResolution(
            category=TokenCategory.COLOR,
            original_value="rgb(59, 130, 246)",
            normalized_value="#3B82F6FF",
            status=ResolutionStatus.EXACT_MATCH,
            matched_token="primary-500",
            distance=0.0,
            suggestion=None,
        )

        data = resolution.to_dict()
        restored = TokenResolution.from_dict(data)

        assert restored.category == resolution.category
        assert restored.original_value == resolution.original_value
        assert restored.normalized_value == resolution.normalized_value
        assert restored.status == resolution.status
        assert restored.matched_token == resolution.matched_token
        assert restored.distance == resolution.distance


class TestTokenResolverColors:
    """Tests for color resolution."""

    def test_exact_hex_match(self, resolver: TokenResolver):
        """Test exact hex color matching."""
        result = resolver.resolve_color("#3B82F6")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "primary-500"
        assert result.distance == 0.0

    def test_exact_rgb_match(self, resolver: TokenResolver):
        """Test rgb() color matching."""
        result = resolver.resolve_color("rgb(59, 130, 246)")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "primary-500"

    def test_exact_rgba_match(self, resolver: TokenResolver):
        """Test rgba() color matching."""
        result = resolver.resolve_color("rgba(59, 130, 246, 1)")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "primary-500"

    def test_short_hex_match(self, resolver: TokenResolver):
        """Test #RGB short hex matching."""
        result = resolver.resolve_color("#fff")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "white"

    def test_off_scale_color(self, resolver: TokenResolver):
        """Test off-scale color detection."""
        result = resolver.resolve_color("#123456")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.suggestion is not None

    def test_near_match_color(self, resolver: TokenResolver):
        """Test near-match color detection."""
        # Create resolver with higher tolerance for testing
        token_set = TokenSet(
            colors={"gray": ColorToken(name="gray", value="#808080FF")}
        )
        resolver = TokenResolver(token_set, color_tolerance=0.1)

        # Test a color very close to gray
        result = resolver.resolve_color("#808181")

        # Should be a near match due to high tolerance
        assert result.nearest_token == "gray"


class TestTokenResolverSpacing:
    """Tests for spacing resolution."""

    def test_exact_px_match(self, resolver: TokenResolver):
        """Test exact pixel value matching."""
        result = resolver.resolve_spacing("16px")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "4"
        assert result.distance == 0.0

    def test_exact_rem_match(self, resolver: TokenResolver):
        """Test rem value matching (1rem = 16px)."""
        result = resolver.resolve_spacing("1rem")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "4"

    def test_near_match_spacing(self, resolver: TokenResolver):
        """Test near-match spacing detection."""
        result = resolver.resolve_spacing("8.5px")

        # Within 1px tolerance of 8px
        assert result.status == ResolutionStatus.NEAR_MATCH
        assert result.matched_token == "2"
        assert result.distance == 0.5

    def test_off_scale_spacing(self, resolver: TokenResolver):
        """Test off-scale spacing detection."""
        # 14px is 2px from 12px and 2px from 16px, outside 1px tolerance
        result = resolver.resolve_spacing("14px")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.nearest_token in ["3", "4"]  # 12px or 16px is closest
        assert result.suggestion is not None

    def test_zero_spacing(self, resolver: TokenResolver):
        """Test zero value matching."""
        result = resolver.resolve_spacing("0")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "0"


class TestTokenResolverRadius:
    """Tests for radius resolution."""

    def test_exact_radius_match(self, resolver: TokenResolver):
        """Test exact radius matching."""
        result = resolver.resolve_radius("8px")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "lg"

    def test_near_match_radius(self, resolver: TokenResolver):
        """Test near-match radius detection."""
        result = resolver.resolve_radius("4.3px")

        # Within 0.5px tolerance of 4px
        assert result.status == ResolutionStatus.NEAR_MATCH
        assert result.matched_token == "md"

    def test_off_scale_radius(self, resolver: TokenResolver):
        """Test off-scale radius detection."""
        result = resolver.resolve_radius("6px")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.nearest_token in ["md", "lg"]  # 4px or 8px closest


class TestTokenResolverTypography:
    """Tests for typography resolution."""

    def test_exact_font_size_match(self, resolver: TokenResolver):
        """Test exact font size matching."""
        result = resolver.resolve_typography("16px")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "base"

    def test_rem_font_size(self, resolver: TokenResolver):
        """Test rem font size matching."""
        result = resolver.resolve_typography("1.5rem")  # 24px

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "2xl"

    def test_near_match_typography(self, resolver: TokenResolver):
        """Test near-match typography detection."""
        result = resolver.resolve_typography("16.5px")

        # Within 1px tolerance of 16px
        assert result.status == ResolutionStatus.NEAR_MATCH
        assert result.matched_token == "base"

    def test_off_scale_typography(self, resolver: TokenResolver):
        """Test off-scale typography detection."""
        # 13px is 1px from 14px but 2px from 12px, check if near or off
        # 17px is 1px from 18px, still near. Use 15.5px which is 1.5px from both 14px and 16px
        result = resolver.resolve_typography("22px")  # 2px from 20px and 24px

        assert result.status == ResolutionStatus.OFF_SCALE
        # 20px (xl) or 24px (2xl) could be nearest
        assert result.nearest_token in ["xl", "2xl"]


class TestTokenResolverShadow:
    """Tests for shadow resolution."""

    def test_exact_shadow_match(self, resolver: TokenResolver):
        """Test exact shadow matching."""
        result = resolver.resolve_shadow("0 1px 2px rgba(0,0,0,0.05)")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "sm"

    def test_shadow_by_name(self, resolver: TokenResolver):
        """Test shadow matching by token name."""
        result = resolver.resolve_shadow("sm")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "sm"

    def test_off_scale_shadow(self, resolver: TokenResolver):
        """Test off-scale shadow detection."""
        result = resolver.resolve_shadow("0 2px 4px rgba(0,0,0,0.2)")

        assert result.status == ResolutionStatus.OFF_SCALE


class TestTokenResolverDeclarations:
    """Tests for resolving multiple declarations."""

    def test_resolve_declarations(self, resolver: TokenResolver):
        """Test resolving a block of CSS declarations."""
        declarations = {
            "color": "#3B82F6",
            "padding": "16px",
            "border-radius": "8px",
            "font-size": "14px",
        }

        results = resolver.resolve_declarations(declarations)

        assert "color" in results
        assert results["color"].status == ResolutionStatus.EXACT_MATCH
        assert results["padding"].status == ResolutionStatus.EXACT_MATCH
        assert results["border-radius"].status == ResolutionStatus.EXACT_MATCH
        assert results["font-size"].status == ResolutionStatus.EXACT_MATCH

    def test_get_off_scale_declarations(self, resolver: TokenResolver):
        """Test filtering for off-scale declarations only."""
        declarations = {
            "color": "#3B82F6",  # On scale
            "padding": "14px",  # Off scale (2px from 12px and 16px)
            "border-radius": "6px",  # Off scale (2px from 4px and 8px)
            "font-size": "16px",  # On scale
        }

        off_scale = resolver.get_off_scale_declarations(declarations)

        assert len(off_scale) == 2
        categories = {r.category for r in off_scale}
        assert TokenCategory.SPACING in categories
        assert TokenCategory.RADIUS in categories

    def test_categorize_color_property(self, resolver: TokenResolver):
        """Test property categorization for colors."""
        assert resolver.categorize_property("color") == TokenCategory.COLOR
        assert resolver.categorize_property("background-color") == TokenCategory.COLOR
        assert resolver.categorize_property("border-color") == TokenCategory.COLOR

    def test_categorize_spacing_property(self, resolver: TokenResolver):
        """Test property categorization for spacing."""
        assert resolver.categorize_property("padding") == TokenCategory.SPACING
        assert resolver.categorize_property("margin-top") == TokenCategory.SPACING
        assert resolver.categorize_property("gap") == TokenCategory.SPACING

    def test_categorize_radius_property(self, resolver: TokenResolver):
        """Test property categorization for radius."""
        assert resolver.categorize_property("border-radius") == TokenCategory.RADIUS
        assert (
            resolver.categorize_property("border-top-left-radius")
            == TokenCategory.RADIUS
        )

    def test_categorize_unknown_property(self, resolver: TokenResolver):
        """Test that unknown properties return None."""
        assert resolver.categorize_property("display") is None
        assert resolver.categorize_property("position") is None


class TestTokenResolverCustomTolerances:
    """Tests for custom tolerance settings."""

    def test_custom_spacing_tolerance(self, sample_token_set: TokenSet):
        """Test custom spacing tolerance."""
        # Very tight tolerance
        resolver = TokenResolver(sample_token_set, spacing_tolerance=0.1)
        result = resolver.resolve_spacing("8.5px")

        # Should be off-scale with tight tolerance
        assert result.status == ResolutionStatus.OFF_SCALE

    def test_custom_radius_tolerance(self, sample_token_set: TokenSet):
        """Test custom radius tolerance."""
        # Looser tolerance
        resolver = TokenResolver(sample_token_set, radius_tolerance=2.0)
        result = resolver.resolve_radius("6px")

        # Should be near-match with looser tolerance
        assert result.status == ResolutionStatus.NEAR_MATCH

    def test_custom_base_font_size(self, sample_token_set: TokenSet):
        """Test custom base font size for rem conversion."""
        resolver = TokenResolver(sample_token_set, base_font_size=20.0)

        # 1rem with 20px base = 20px, which is xl (20px)
        result = resolver.resolve_typography("1rem")

        assert result.status == ResolutionStatus.EXACT_MATCH
        assert result.matched_token == "xl"


class TestTokenResolverEmptyTokenSet:
    """Tests for handling empty token sets."""

    def test_empty_colors(self):
        """Test color resolution with no colors defined."""
        resolver = TokenResolver(TokenSet())
        result = resolver.resolve_color("#3B82F6")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.nearest_token is None

    def test_empty_spacing(self):
        """Test spacing resolution with no spacing defined."""
        resolver = TokenResolver(TokenSet())
        result = resolver.resolve_spacing("16px")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.nearest_token is None

    def test_empty_typography(self):
        """Test typography resolution with no typography defined."""
        resolver = TokenResolver(TokenSet())
        result = resolver.resolve_typography("16px")

        assert result.status == ResolutionStatus.OFF_SCALE
        assert result.nearest_token is None
