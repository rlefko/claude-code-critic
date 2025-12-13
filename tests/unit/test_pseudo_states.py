"""Unit tests for pseudo-state capture."""

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestPseudoState:
    """Tests for PseudoState enum."""

    def test_all_states_defined(self):
        """Test that all expected states are defined."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoState

        expected = ["DEFAULT", "HOVER", "FOCUS", "FOCUS_VISIBLE", "ACTIVE", "DISABLED"]
        state_names = [s.name for s in PseudoState]
        for state in expected:
            assert state in state_names

    def test_state_values(self):
        """Test state string values."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoState

        assert PseudoState.DEFAULT.value == "default"
        assert PseudoState.HOVER.value == "hover"
        assert PseudoState.FOCUS_VISIBLE.value == "focus-visible"


class TestPseudoStateStyles:
    """Tests for PseudoStateStyles dataclass."""

    def test_default_state_required(self):
        """Test that default state is always present."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles

        styles = PseudoStateStyles()
        assert styles.default is not None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(typography={"color": "#000"}),
            hover=CapturedStyles(typography={"color": "#00f"}),
        )

        data = styles.to_dict()

        assert "default" in data
        assert "hover" in data
        assert data["default"]["typography"]["color"] == "#000"
        assert data["hover"]["typography"]["color"] == "#00f"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles

        data = {
            "default": {"typography": {"color": "black"}},
            "hover": {"typography": {"color": "blue"}},
        }

        styles = PseudoStateStyles.from_dict(data)

        assert styles.default.typography["color"] == "black"
        assert styles.hover.typography["color"] == "blue"
        assert styles.focus is None

    def test_get_state_diff_no_change(self):
        """Test state diff when no changes."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateStyles,
        )
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        same_styles = CapturedStyles(typography={"color": "#000"})
        styles = PseudoStateStyles(default=same_styles, hover=same_styles)

        diff = styles.get_state_diff(PseudoState.HOVER)
        assert len(diff) == 0

    def test_get_state_diff_with_changes(self):
        """Test state diff with changes."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateStyles,
        )
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(
                typography={"color": "#000"},
                background={"background-color": "#fff"},
            ),
            hover=CapturedStyles(
                typography={"color": "#00f"},
                background={"background-color": "#eee"},
            ),
        )

        diff = styles.get_state_diff(PseudoState.HOVER)

        assert "color" in diff
        assert diff["color"] == ("#000", "#00f")
        assert "background-color" in diff

    def test_get_state_diff_missing_state(self):
        """Test state diff when state not captured."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateStyles,
        )
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(typography={"color": "#000"}),
        )

        diff = styles.get_state_diff(PseudoState.HOVER)
        assert len(diff) == 0

    def test_has_hover_styles_true(self):
        """Test hover style detection when meaningful changes exist."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(
                background={"background-color": "#fff"},
            ),
            hover=CapturedStyles(
                background={"background-color": "#eee"},
            ),
        )

        assert styles.has_hover_styles() is True

    def test_has_hover_styles_false(self):
        """Test hover style detection when no meaningful changes."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        same_styles = CapturedStyles(background={"background-color": "#fff"})
        styles = PseudoStateStyles(default=same_styles, hover=same_styles)

        assert styles.has_hover_styles() is False

    def test_has_hover_styles_no_hover(self):
        """Test hover style detection when hover not captured."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(background={"background-color": "#fff"}),
        )

        assert styles.has_hover_styles() is False

    def test_has_focus_ring_true(self):
        """Test focus ring detection when visible indicator present."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        styles = PseudoStateStyles(
            default=CapturedStyles(
                interaction={"outline-width": "0", "outline-style": "none"},
            ),
            focus_visible=CapturedStyles(
                interaction={"outline-width": "2px", "outline-style": "solid"},
            ),
        )

        assert styles.has_focus_ring() is True

    def test_has_focus_ring_false_no_change(self):
        """Test focus ring detection when no visible change."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles
        from claude_indexer.ui.collectors.style_capture import CapturedStyles

        same_styles = CapturedStyles(
            interaction={"outline-width": "0", "outline-style": "none"},
        )
        styles = PseudoStateStyles(default=same_styles, focus_visible=same_styles)

        assert styles.has_focus_ring() is False

    def test_is_visible_value(self):
        """Test visible value detection."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateStyles

        styles = PseudoStateStyles()

        # Invisible values
        assert styles._is_visible_value("none") is False
        assert styles._is_visible_value("0") is False
        assert styles._is_visible_value("0px") is False
        assert styles._is_visible_value("transparent") is False
        assert styles._is_visible_value("") is False

        # Visible values
        assert styles._is_visible_value("2px") is True
        assert styles._is_visible_value("solid") is True
        assert styles._is_visible_value("#000") is True


class TestPseudoStateCapture:
    """Tests for PseudoStateCapture class."""

    def test_init_default_states(self):
        """Test default state capture configuration."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateCapture,
        )

        capture = PseudoStateCapture()

        assert PseudoState.DEFAULT in capture.capture_states
        assert PseudoState.HOVER in capture.capture_states
        assert PseudoState.FOCUS_VISIBLE in capture.capture_states

    def test_init_custom_states(self):
        """Test custom state capture configuration."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateCapture,
        )

        states = [PseudoState.DEFAULT, PseudoState.HOVER]
        capture = PseudoStateCapture(capture_states=states)

        assert capture.capture_states == states

    def test_init_custom_style_capture(self):
        """Test custom style capture instance."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateCapture
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        style_capture = ComputedStyleCapture(normalize_values=False)
        capture = PseudoStateCapture(style_capture=style_capture)

        assert capture.style_capture.normalize_values is False


class TestPseudoStateCaptureAsync:
    """Async tests for pseudo-state capture."""

    @pytest.mark.asyncio
    async def test_capture_all_states(self):
        """Test capturing all configured states."""
        from claude_indexer.ui.collectors.pseudo_states import (
            PseudoState,
            PseudoStateCapture,
        )
        from claude_indexer.ui.collectors.style_capture import ComputedStyleCapture

        # Mock style capture
        mock_style_capture = MagicMock(spec=ComputedStyleCapture)
        mock_style_capture.capture = AsyncMock(
            return_value=MagicMock(to_flat_dict=lambda: {"font-size": "16px"})
        )

        capture = PseudoStateCapture(
            style_capture=mock_style_capture,
            capture_states=[PseudoState.DEFAULT],
        )

        # Mock element and page
        mock_element = AsyncMock()
        mock_page = AsyncMock()

        result = await capture.capture_all_states(mock_element, mock_page)

        assert result.default is not None
        mock_style_capture.capture.assert_called()

    @pytest.mark.asyncio
    async def test_capture_hover(self):
        """Test hover state capture."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateCapture
        from claude_indexer.ui.collectors.style_capture import (
            CapturedStyles,
            ComputedStyleCapture,
        )

        # Mock style capture
        mock_style_capture = MagicMock(spec=ComputedStyleCapture)
        mock_style_capture.capture = AsyncMock(
            return_value=CapturedStyles(background={"background-color": "#eee"})
        )

        capture = PseudoStateCapture(style_capture=mock_style_capture)

        # Mock element with bounding box
        mock_element = AsyncMock()
        mock_element.bounding_box = AsyncMock(
            return_value={"x": 100, "y": 100, "width": 100, "height": 40}
        )

        # Mock page
        mock_page = AsyncMock()
        mock_page.mouse = MagicMock()
        mock_page.mouse.move = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        result = await capture.capture_hover(mock_element, mock_page)

        assert result.background["background-color"] == "#eee"
        mock_page.mouse.move.assert_called()

    @pytest.mark.asyncio
    async def test_capture_focus(self):
        """Test focus state capture."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateCapture
        from claude_indexer.ui.collectors.style_capture import (
            CapturedStyles,
            ComputedStyleCapture,
        )

        # Mock style capture
        mock_style_capture = MagicMock(spec=ComputedStyleCapture)
        mock_style_capture.capture = AsyncMock(
            return_value=CapturedStyles(
                interaction={"outline-width": "2px", "outline-style": "solid"}
            )
        )

        capture = PseudoStateCapture(style_capture=mock_style_capture)

        # Mock element
        mock_element = AsyncMock()
        mock_element.focus = AsyncMock()

        # Mock page
        mock_page = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        result = await capture.capture_focus(mock_element, mock_page)

        mock_element.focus.assert_called()
        assert result.interaction["outline-width"] == "2px"

    @pytest.mark.asyncio
    async def test_is_disabled(self):
        """Test disabled state detection."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateCapture

        capture = PseudoStateCapture()

        # Test disabled element
        mock_disabled = AsyncMock()
        mock_disabled.evaluate = AsyncMock(return_value=True)
        assert await capture._is_disabled(mock_disabled) is True

        # Test enabled element
        mock_enabled = AsyncMock()
        mock_enabled.evaluate = AsyncMock(return_value=False)
        assert await capture._is_disabled(mock_enabled) is False

    @pytest.mark.asyncio
    async def test_reset_state(self):
        """Test state reset after capture."""
        from claude_indexer.ui.collectors.pseudo_states import PseudoStateCapture

        capture = PseudoStateCapture()

        mock_element = AsyncMock()
        mock_page = AsyncMock()
        mock_page.mouse = MagicMock()
        mock_page.mouse.move = AsyncMock()
        mock_page.mouse.up = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()

        await capture._reset_state(mock_element, mock_page)

        mock_page.mouse.move.assert_called_with(0, 0)
        mock_page.mouse.up.assert_called()
