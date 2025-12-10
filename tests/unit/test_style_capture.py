"""Unit tests for computed style capture."""

import pytest
from unittest.mock import AsyncMock, MagicMock


class TestCapturedStyles:
    """Tests for CapturedStyles dataclass."""

    def test_to_flat_dict(self):
        """Test flattening style categories."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = CapturedStyles(
            typography={"font-size": "16px", "color": "#000"},
            spacing={"padding-top": "8px"},
            shape={"border-top-left-radius": "4px"},
            elevation={"box-shadow": "none"},
            background={"background-color": "#fff"},
            interaction={"cursor": "pointer"},
            layout={"display": "flex"},
        )

        flat = styles.to_flat_dict()

        assert flat["font-size"] == "16px"
        assert flat["color"] == "#000"
        assert flat["padding-top"] == "8px"
        assert flat["border-top-left-radius"] == "4px"
        assert flat["display"] == "flex"
        assert len(flat) == 8

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = CapturedStyles(
            typography={"font-size": "14px"},
            spacing={"margin-top": "16px"},
        )

        data = styles.to_dict()

        assert "typography" in data
        assert "spacing" in data
        assert data["typography"]["font-size"] == "14px"
        assert data["spacing"]["margin-top"] == "16px"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        data = {
            "typography": {"font-weight": "bold"},
            "spacing": {"padding-left": "12px"},
            "shape": {},
            "elevation": {},
            "background": {},
            "interaction": {},
            "layout": {},
        }

        styles = CapturedStyles.from_dict(data)

        assert styles.typography["font-weight"] == "bold"
        assert styles.spacing["padding-left"] == "12px"

    def test_round_trip(self):
        """Test serialization round-trip."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        original = CapturedStyles(
            typography={"font-family": "Arial", "font-size": "16px"},
            spacing={"padding-top": "8px"},
            shape={"border-top-left-radius": "8px"},
            elevation={"box-shadow": "0 2px 4px rgba(0,0,0,0.1)"},
            background={"background-color": "rgb(255, 255, 255)"},
            interaction={"cursor": "default"},
            layout={"display": "block"},
        )

        data = original.to_dict()
        restored = CapturedStyles.from_dict(data)

        assert restored.typography == original.typography
        assert restored.spacing == original.spacing
        assert restored.shape == original.shape

    def test_diff_identical(self):
        """Test diff between identical styles."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles1 = CapturedStyles(
            typography={"font-size": "16px"},
            spacing={"padding": "8px"},
        )
        styles2 = CapturedStyles(
            typography={"font-size": "16px"},
            spacing={"padding": "8px"},
        )

        diff = styles1.diff(styles2)
        assert len(diff) == 0

    def test_diff_different(self):
        """Test diff between different styles."""
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles1 = CapturedStyles(
            typography={"font-size": "16px", "color": "#000"},
        )
        styles2 = CapturedStyles(
            typography={"font-size": "14px", "color": "#000"},
        )

        diff = styles1.diff(styles2)

        assert "font-size" in diff
        assert diff["font-size"] == ("16px", "14px")
        assert "color" not in diff


class TestComputedStyleCapture:
    """Tests for ComputedStyleCapture class."""

    def test_init_default(self):
        """Test default initialization."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        capture = ComputedStyleCapture()

        assert capture.normalizer is not None
        assert capture.normalize_values is True
        assert len(capture._all_props) > 0

    def test_init_custom_normalizer(self):
        """Test initialization with custom normalizer."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture
        from claude_indexer.ui.normalizers.style import StyleNormalizer

        normalizer = StyleNormalizer(base_font_size=14.0)
        capture = ComputedStyleCapture(normalizer=normalizer)

        assert capture.normalizer.base_font_size == 14.0

    def test_all_property_categories(self):
        """Test that all property categories are defined."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        assert len(ComputedStyleCapture.TYPOGRAPHY_PROPS) > 0
        assert len(ComputedStyleCapture.SPACING_PROPS) > 0
        assert len(ComputedStyleCapture.SHAPE_PROPS) > 0
        assert len(ComputedStyleCapture.ELEVATION_PROPS) > 0
        assert len(ComputedStyleCapture.BACKGROUND_PROPS) > 0
        assert len(ComputedStyleCapture.INTERACTION_PROPS) > 0
        assert len(ComputedStyleCapture.LAYOUT_PROPS) > 0

    def test_typography_props(self):
        """Test typography property list."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        props = ComputedStyleCapture.TYPOGRAPHY_PROPS
        assert "font-family" in props
        assert "font-size" in props
        assert "font-weight" in props
        assert "line-height" in props
        assert "color" in props

    def test_spacing_props(self):
        """Test spacing property list."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        props = ComputedStyleCapture.SPACING_PROPS
        assert "padding-top" in props
        assert "margin-left" in props
        assert "gap" in props

    def test_categorize_styles(self):
        """Test style categorization."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        capture = ComputedStyleCapture(normalize_values=False)

        raw_styles = {
            "font-size": "16px",
            "padding-top": "8px",
            "border-top-left-radius": "4px",
            "box-shadow": "none",
            "background-color": "#fff",
            "cursor": "pointer",
            "display": "flex",
        }

        result = capture._categorize_styles(raw_styles)

        assert result.typography["font-size"] == "16px"
        assert result.spacing["padding-top"] == "8px"
        assert result.shape["border-top-left-radius"] == "4px"
        assert result.elevation["box-shadow"] == "none"
        assert result.background["background-color"] == "#fff"
        assert result.interaction["cursor"] == "pointer"
        assert result.layout["display"] == "flex"

    def test_compute_similarity_identical(self):
        """Test similarity computation for identical styles."""
        from claude_indexer.ui.collectors.style_capture import (
            CapturedStyles,
            ComputedStyleCapture,
        )

        styles = CapturedStyles(
            typography={"font-size": "16px"},
            spacing={"padding": "8px"},
        )

        capture = ComputedStyleCapture()
        similarity = capture.compute_similarity(styles, styles)

        assert similarity == 1.0

    def test_compute_similarity_different(self):
        """Test similarity computation for different styles."""
        from claude_indexer.ui.collectors.style_capture import (
            CapturedStyles,
            ComputedStyleCapture,
        )

        styles1 = CapturedStyles(
            typography={"font-size": "16px"},
            spacing={"padding": "8px"},
        )
        styles2 = CapturedStyles(
            typography={"font-size": "14px"},
            spacing={"padding": "16px"},
        )

        capture = ComputedStyleCapture()
        similarity = capture.compute_similarity(styles1, styles2)

        assert 0.0 <= similarity < 1.0

    def test_compute_similarity_empty(self):
        """Test similarity computation for empty styles."""
        from claude_indexer.ui.collectors.style_capture import (
            CapturedStyles,
            ComputedStyleCapture,
        )

        styles1 = CapturedStyles()
        styles2 = CapturedStyles()

        capture = ComputedStyleCapture()
        similarity = capture.compute_similarity(styles1, styles2)

        assert similarity == 1.0


class TestComputedStyleCaptureAsync:
    """Async tests for style capture (require mocking Playwright)."""

    @pytest.mark.asyncio
    async def test_capture_element_styles(self):
        """Test capturing styles from element."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        # Mock element with computed styles
        mock_element = AsyncMock()
        mock_element.evaluate = AsyncMock(
            return_value={
                "font-size": "16px",
                "font-weight": "400",
                "color": "rgb(0, 0, 0)",
                "padding-top": "8px",
                "padding-right": "16px",
                "padding-bottom": "8px",
                "padding-left": "16px",
                "border-top-left-radius": "4px",
                "background-color": "rgb(255, 255, 255)",
                "cursor": "pointer",
                "display": "inline-flex",
            }
        )

        mock_page = AsyncMock()

        capture = ComputedStyleCapture(normalize_values=False)
        styles = await capture.capture(mock_element, mock_page)

        assert styles.typography["font-size"] == "16px"
        assert styles.spacing["padding-top"] == "8px"
        assert styles.layout["display"] == "inline-flex"

    @pytest.mark.asyncio
    async def test_capture_batch(self):
        """Test batch capture of multiple elements."""
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        # Create mock elements
        mock_elements = []
        for i in range(3):
            mock_elem = AsyncMock()
            mock_elem.evaluate = AsyncMock(
                return_value={
                    "font-size": f"{14 + i * 2}px",
                    "padding-top": f"{4 + i * 4}px",
                }
            )
            mock_page = AsyncMock()
            mock_elements.append((mock_elem, mock_page))

        capture = ComputedStyleCapture(normalize_values=False)
        results = await capture.capture_batch(mock_elements)

        assert len(results) == 3
        assert results[0].typography["font-size"] == "14px"
        assert results[1].typography["font-size"] == "16px"
        assert results[2].typography["font-size"] == "18px"
