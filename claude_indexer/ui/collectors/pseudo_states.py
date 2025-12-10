"""Pseudo-state style capture.

Simulates and captures styles for hover, focus-visible, and disabled states.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from playwright.async_api import ElementHandle, Page

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    ElementHandle = None
    Page = None

from .style_capture import CapturedStyles, ComputedStyleCapture


class PseudoState(Enum):
    """Supported pseudo-states."""

    DEFAULT = "default"
    HOVER = "hover"
    FOCUS = "focus"
    FOCUS_VISIBLE = "focus-visible"
    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass
class PseudoStateStyles:
    """Styles captured across multiple pseudo-states."""

    default: CapturedStyles = field(default_factory=CapturedStyles)
    hover: CapturedStyles | None = None
    focus: CapturedStyles | None = None
    focus_visible: CapturedStyles | None = None
    active: CapturedStyles | None = None
    disabled: CapturedStyles | None = None

    def get_state_diff(
        self,
        state: PseudoState,
    ) -> dict[str, tuple[str, str]]:
        """Get style differences between default and given state.

        Args:
            state: The pseudo-state to compare with default.

        Returns:
            Dict of property -> (default_value, state_value) for differences.
        """
        state_styles = self._get_state_styles(state)
        if state_styles is None:
            return {}

        return self.default.diff(state_styles)

    def _get_state_styles(self, state: PseudoState) -> CapturedStyles | None:
        """Get styles for a specific state.

        Args:
            state: The pseudo-state.

        Returns:
            CapturedStyles for that state or None.
        """
        state_map = {
            PseudoState.DEFAULT: self.default,
            PseudoState.HOVER: self.hover,
            PseudoState.FOCUS: self.focus,
            PseudoState.FOCUS_VISIBLE: self.focus_visible,
            PseudoState.ACTIVE: self.active,
            PseudoState.DISABLED: self.disabled,
        }
        return state_map.get(state)

    def has_hover_styles(self) -> bool:
        """Check if element has meaningful hover style changes."""
        if self.hover is None:
            return False

        diff = self.get_state_diff(PseudoState.HOVER)
        # Check for meaningful visual changes
        meaningful_props = {
            "color",
            "background-color",
            "border-color",
            "box-shadow",
            "transform",
            "opacity",
        }
        return any(prop in meaningful_props for prop in diff.keys())

    def has_focus_ring(self) -> bool:
        """Check if element shows visible focus indication.

        Checks for outline, box-shadow, or border changes on focus.
        """
        if self.focus_visible is None and self.focus is None:
            return False

        focus_styles = self.focus_visible or self.focus
        if focus_styles is None:
            return False

        diff = self.default.diff(focus_styles)

        # Check for visible focus indicators
        focus_indicators = {
            "outline-width",
            "outline-style",
            "outline-color",
            "box-shadow",
            "border-color",
            "border-width",
        }

        for prop in focus_indicators:
            if prop in diff:
                old_val, new_val = diff[prop]
                # Check if we gained a visible indicator
                if self._is_visible_value(new_val) and not self._is_visible_value(old_val):
                    return True

        return False

    def _is_visible_value(self, value: str) -> bool:
        """Check if a CSS value represents something visible.

        Args:
            value: CSS value string.

        Returns:
            True if the value is visible (not none/0/transparent).
        """
        if not value:
            return False
        value = value.strip().lower()
        invisible_values = {"none", "0", "0px", "transparent", "rgba(0, 0, 0, 0)"}
        return value not in invisible_values

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "default": self.default.to_dict(),
        }
        if self.hover:
            result["hover"] = self.hover.to_dict()
        if self.focus:
            result["focus"] = self.focus.to_dict()
        if self.focus_visible:
            result["focus_visible"] = self.focus_visible.to_dict()
        if self.active:
            result["active"] = self.active.to_dict()
        if self.disabled:
            result["disabled"] = self.disabled.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PseudoStateStyles":
        """Create from dictionary."""
        return cls(
            default=CapturedStyles.from_dict(data.get("default", {})),
            hover=CapturedStyles.from_dict(data["hover"]) if data.get("hover") else None,
            focus=CapturedStyles.from_dict(data["focus"]) if data.get("focus") else None,
            focus_visible=CapturedStyles.from_dict(data["focus_visible"])
            if data.get("focus_visible")
            else None,
            active=CapturedStyles.from_dict(data["active"])
            if data.get("active")
            else None,
            disabled=CapturedStyles.from_dict(data["disabled"])
            if data.get("disabled")
            else None,
        )


class PseudoStateCapture:
    """Captures styles for different pseudo-states.

    Uses Playwright to simulate states and capture resulting styles:
    - Hover: mouse enter simulation
    - Focus: focus() call with keyboard flag
    - Focus-visible: Tab key simulation
    - Active: mousedown simulation
    - Disabled: Check disabled attribute and capture styles
    """

    def __init__(
        self,
        style_capture: ComputedStyleCapture | None = None,
        capture_states: list[PseudoState] | None = None,
    ):
        """Initialize pseudo-state capture.

        Args:
            style_capture: ComputedStyleCapture instance for style capture.
            capture_states: List of states to capture (defaults to common set).
        """
        self.style_capture = style_capture or ComputedStyleCapture()
        self.capture_states = capture_states or [
            PseudoState.DEFAULT,
            PseudoState.HOVER,
            PseudoState.FOCUS_VISIBLE,
        ]

    async def capture_all_states(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> PseudoStateStyles:
        """Capture styles for all configured pseudo-states.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            PseudoStateStyles with all captured states.
        """
        result = PseudoStateStyles()

        # Always capture default state first
        result.default = await self.style_capture.capture(element, page)

        # Capture each configured state
        for state in self.capture_states:
            if state == PseudoState.DEFAULT:
                continue

            try:
                if state == PseudoState.HOVER:
                    result.hover = await self.capture_hover(element, page)
                elif state == PseudoState.FOCUS:
                    result.focus = await self.capture_focus(element, page)
                elif state == PseudoState.FOCUS_VISIBLE:
                    result.focus_visible = await self.capture_focus_visible(element, page)
                elif state == PseudoState.ACTIVE:
                    result.active = await self.capture_active(element, page)
                elif state == PseudoState.DISABLED:
                    result.disabled = await self.capture_disabled(element, page)

                # Reset state after capture
                await self._reset_state(element, page)

            except Exception:
                # State capture failed, leave as None
                pass

        return result

    async def capture_hover(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles:
        """Simulate hover and capture styles.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            CapturedStyles while hovering.
        """
        # Get element bounding box for hover position
        box = await element.bounding_box()
        if box:
            # Move mouse to center of element
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await page.mouse.move(x, y)

        # Brief wait for hover styles to apply
        await page.wait_for_timeout(50)

        # Capture styles
        return await self.style_capture.capture(element, page)

    async def capture_focus(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles:
        """Simulate focus and capture styles.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            CapturedStyles while focused.
        """
        # Focus the element
        await element.focus()

        # Brief wait for focus styles to apply
        await page.wait_for_timeout(50)

        # Capture styles
        return await self.style_capture.capture(element, page)

    async def capture_focus_visible(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles:
        """Simulate keyboard focus (focus-visible) and capture styles.

        Uses Tab key to trigger focus-visible state (keyboard navigation).

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            CapturedStyles with focus-visible state.
        """
        # First blur any currently focused element
        await page.evaluate("document.activeElement?.blur()")

        # Click elsewhere first to ensure clean state
        await page.mouse.click(0, 0)

        # Tab to the element (may need multiple tabs)
        # First, try to find element's position in tab order
        max_tabs = 20
        for _ in range(max_tabs):
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(20)

            # Check if our element is now focused
            is_focused = await element.evaluate("el => el === document.activeElement")
            if is_focused:
                break

        # Capture styles
        return await self.style_capture.capture(element, page)

    async def capture_active(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles:
        """Simulate active (mousedown) state and capture styles.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            CapturedStyles while active.
        """
        # Get element bounding box
        box = await element.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            # Press mouse down (don't release)
            await page.mouse.move(x, y)
            await page.mouse.down()

        # Brief wait for active styles
        await page.wait_for_timeout(50)

        # Capture styles
        styles = await self.style_capture.capture(element, page)

        # Release mouse
        await page.mouse.up()

        return styles

    async def capture_disabled(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> CapturedStyles | None:
        """Capture disabled state styles if element supports it.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.

        Returns:
            CapturedStyles for disabled state, or None if not applicable.
        """
        # Check if element is or can be disabled
        is_disabled = await self._is_disabled(element)
        if is_disabled:
            # Element is already disabled, capture current styles
            return await self.style_capture.capture(element, page)

        # Check if element supports disabled attribute
        can_disable = await element.evaluate(
            """el => {
                const tag = el.tagName.toLowerCase();
                return ['button', 'input', 'select', 'textarea', 'fieldset'].includes(tag);
            }"""
        )

        if not can_disable:
            return None

        # Temporarily disable element to capture styles
        original_disabled = await element.get_attribute("disabled")
        await element.evaluate("el => el.disabled = true")

        # Brief wait for styles to update
        await page.wait_for_timeout(50)

        # Capture disabled styles
        styles = await self.style_capture.capture(element, page)

        # Restore original state
        if original_disabled is None:
            await element.evaluate("el => el.removeAttribute('disabled')")
        else:
            await element.evaluate(
                "(el, val) => el.setAttribute('disabled', val)", original_disabled
            )

        return styles

    async def _is_disabled(
        self,
        element: "ElementHandle",
    ) -> bool:
        """Check if element is disabled.

        Args:
            element: Playwright ElementHandle.

        Returns:
            True if element is disabled.
        """
        try:
            return await element.evaluate(
                """el => {
                    if (el.disabled !== undefined) return el.disabled;
                    if (el.hasAttribute('disabled')) return true;
                    if (el.hasAttribute('aria-disabled')) return el.getAttribute('aria-disabled') === 'true';
                    return false;
                }"""
            )
        except Exception:
            return False

    async def _reset_state(
        self,
        element: "ElementHandle",
        page: "Page",
    ) -> None:
        """Reset element to default state.

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.
        """
        try:
            # Move mouse away
            await page.mouse.move(0, 0)

            # Release any pressed buttons
            await page.mouse.up()

            # Blur if focused
            await page.evaluate("document.activeElement?.blur()")

            # Brief wait for styles to reset
            await page.wait_for_timeout(50)

        except Exception:
            # Best effort reset
            pass


__all__ = [
    "PseudoState",
    "PseudoStateStyles",
    "PseudoStateCapture",
]
