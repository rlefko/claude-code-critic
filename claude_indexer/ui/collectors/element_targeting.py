"""Element targeting strategy for runtime UI analysis.

Discovers UI elements by role with stable selector generation.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    from playwright.async_api import ElementHandle, Page

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    ElementHandle = None
    Page = None


class UIRole(Enum):
    """Standardized UI element roles."""

    BUTTON = "button"
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TOGGLE = "toggle"
    LINK = "link"
    HEADING = "heading"
    TEXT = "text"
    IMAGE = "image"
    CARD = "card"
    PANEL = "panel"
    NAV = "nav"
    MODAL = "modal"
    DIALOG = "dialog"
    TOAST = "toast"
    ALERT = "alert"
    LIST_ITEM = "listitem"
    TAB = "tab"
    MENU = "menu"
    MENUITEM = "menuitem"


@dataclass
class DiscoveredElement:
    """A discovered UI element with stable selector."""

    role: UIRole
    selector: str  # Stable CSS selector
    is_repeated: bool = False  # Part of a list/grid
    component_name: str | None = None  # From data-component or source map
    aria_label: str | None = None
    tag_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding locator)."""
        return {
            "role": self.role.value,
            "selector": self.selector,
            "is_repeated": self.is_repeated,
            "component_name": self.component_name,
            "aria_label": self.aria_label,
            "tag_name": self.tag_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiscoveredElement":
        """Create from dictionary."""
        return cls(
            role=UIRole(data["role"]),
            selector=data["selector"],
            is_repeated=data.get("is_repeated", False),
            component_name=data.get("component_name"),
            aria_label=data.get("aria_label"),
            tag_name=data.get("tag_name"),
        )


# Role to selector mappings for element discovery
ROLE_SELECTORS: dict[UIRole, list[str]] = {
    UIRole.BUTTON: [
        '[role="button"]',
        "button",
        '[type="submit"]',
        '[type="button"]',
        "a.btn",
        '[class*="button"]',
        '[class*="Button"]',
    ],
    UIRole.INPUT: [
        '[role="textbox"]',
        'input[type="text"]',
        'input[type="email"]',
        'input[type="password"]',
        'input[type="search"]',
        'input[type="tel"]',
        'input[type="url"]',
        'input[type="number"]',
        "input:not([type])",
    ],
    UIRole.TEXTAREA: [
        "textarea",
    ],
    UIRole.SELECT: [
        '[role="combobox"]',
        '[role="listbox"]',
        "select",
        '[class*="select"]',
        '[class*="Select"]',
    ],
    UIRole.CHECKBOX: [
        '[role="checkbox"]',
        'input[type="checkbox"]',
        '[class*="checkbox"]',
        '[class*="Checkbox"]',
    ],
    UIRole.RADIO: [
        '[role="radio"]',
        'input[type="radio"]',
    ],
    UIRole.TOGGLE: [
        '[role="switch"]',
        '[class*="toggle"]',
        '[class*="Toggle"]',
        '[class*="switch"]',
        '[class*="Switch"]',
    ],
    UIRole.LINK: [
        "a[href]",
        '[role="link"]',
    ],
    UIRole.HEADING: [
        '[role="heading"]',
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    ],
    UIRole.TEXT: [
        "p",
        "span.text",
        '[class*="text"]',
        '[class*="Text"]',
    ],
    UIRole.IMAGE: [
        "img",
        '[role="img"]',
        "svg",
        "picture",
    ],
    UIRole.CARD: [
        '[class*="card"]',
        '[class*="Card"]',
        "article",
        '[role="article"]',
    ],
    UIRole.PANEL: [
        '[class*="panel"]',
        '[class*="Panel"]',
        "section",
        "aside",
    ],
    UIRole.NAV: [
        '[role="navigation"]',
        "nav",
        '[class*="nav"]',
        '[class*="Nav"]',
        '[class*="sidebar"]',
        '[class*="Sidebar"]',
    ],
    UIRole.MODAL: [
        '[role="dialog"]',
        '[class*="modal"]',
        '[class*="Modal"]',
    ],
    UIRole.DIALOG: [
        "dialog",
        '[role="dialog"]',
        '[role="alertdialog"]',
    ],
    UIRole.TOAST: [
        '[class*="toast"]',
        '[class*="Toast"]',
        '[role="status"]',
        '[class*="notification"]',
        '[class*="Notification"]',
    ],
    UIRole.ALERT: [
        '[role="alert"]',
        '[class*="alert"]',
        '[class*="Alert"]',
    ],
    UIRole.LIST_ITEM: [
        '[role="listitem"]',
        "li",
        '[class*="list-item"]',
        '[class*="ListItem"]',
    ],
    UIRole.TAB: [
        '[role="tab"]',
        '[class*="tab"]',
        '[class*="Tab"]',
    ],
    UIRole.MENU: [
        '[role="menu"]',
        '[class*="menu"]',
        '[class*="Menu"]',
    ],
    UIRole.MENUITEM: [
        '[role="menuitem"]',
        '[class*="menu-item"]',
        '[class*="MenuItem"]',
    ],
}

# Selector priority for stability (highest to lowest)
SELECTOR_PRIORITY_ATTRS = [
    "data-testid",
    "data-test-id",
    "data-cy",
    "data-component",
    "data-ui",
    "id",
]


class ElementTargetingStrategy:
    """Strategy for discovering and targeting UI elements.

    Discovers elements using:
    1. ARIA roles (highest priority)
    2. data-testid attributes
    3. data-component attributes
    4. Semantic HTML elements
    5. Common component patterns
    """

    def __init__(
        self,
        roles: list[str] | None = None,
        custom_selectors: list[str] | None = None,
        test_id_patterns: list[str] | None = None,
        max_elements_per_role: int = 50,
    ):
        """Initialize targeting strategy.

        Args:
            roles: List of role names to discover (all if None).
            custom_selectors: Additional custom selectors to search.
            test_id_patterns: Attribute names to use for stable selectors.
            max_elements_per_role: Maximum elements to capture per role.
        """
        self.roles = self._parse_roles(roles)
        self.custom_selectors = custom_selectors or []
        self.test_id_patterns = test_id_patterns or list(SELECTOR_PRIORITY_ATTRS)
        self.max_elements_per_role = max_elements_per_role

    def _parse_roles(self, roles: list[str] | None) -> list[UIRole]:
        """Parse role strings to UIRole enum values."""
        if roles is None:
            return list(UIRole)

        result = []
        for role_str in roles:
            try:
                # Try exact match first
                result.append(UIRole(role_str.lower()))
            except ValueError:
                # Try name match
                for role in UIRole:
                    if role.name.lower() == role_str.lower():
                        result.append(role)
                        break
        return result

    async def discover_elements(
        self,
        page: "Page",
    ) -> list[DiscoveredElement]:
        """Discover all targetable UI elements on page.

        Args:
            page: Playwright Page instance.

        Returns:
            List of DiscoveredElement instances.
        """
        all_elements: list[DiscoveredElement] = []
        seen_selectors: set[str] = set()

        # Discover elements for each role
        for role in self.roles:
            role_elements = await self._discover_role(page, role)

            # Deduplicate and limit
            for elem in role_elements:
                if elem.selector not in seen_selectors:
                    seen_selectors.add(elem.selector)
                    all_elements.append(elem)

                    if (
                        len([e for e in all_elements if e.role == role])
                        >= self.max_elements_per_role
                    ):
                        break

        # Discover custom selectors
        for selector in self.custom_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for elem in elements:
                    stable_selector = await self._generate_stable_selector(
                        elem, page, selector
                    )
                    if stable_selector and stable_selector not in seen_selectors:
                        seen_selectors.add(stable_selector)
                        all_elements.append(
                            DiscoveredElement(
                                role=UIRole.PANEL,  # Default for custom
                                selector=stable_selector,
                                component_name=await self._get_component_name(elem),
                            )
                        )
            except Exception:
                pass

        # Detect repeated elements (lists/grids)
        all_elements = await self._detect_repeated_elements(all_elements, page)

        return all_elements

    async def _discover_role(
        self,
        page: "Page",
        role: UIRole,
    ) -> list[DiscoveredElement]:
        """Discover elements for a specific role.

        Args:
            page: Playwright Page instance.
            role: UIRole to discover.

        Returns:
            List of DiscoveredElement for this role.
        """
        elements: list[DiscoveredElement] = []
        selectors = ROLE_SELECTORS.get(role, [])

        for selector in selectors:
            try:
                matches = await page.query_selector_all(selector)
                for match in matches[: self.max_elements_per_role]:
                    try:
                        # Check if element is visible
                        is_visible = await match.is_visible()
                        if not is_visible:
                            continue

                        # Generate stable selector
                        stable_selector = await self._generate_stable_selector(
                            match, page, selector
                        )
                        if not stable_selector:
                            continue

                        # Get additional info
                        aria_label = await match.get_attribute("aria-label")
                        tag_name = await match.evaluate(
                            "el => el.tagName.toLowerCase()"
                        )
                        component_name = await self._get_component_name(match)

                        elements.append(
                            DiscoveredElement(
                                role=role,
                                selector=stable_selector,
                                component_name=component_name,
                                aria_label=aria_label,
                                tag_name=tag_name,
                            )
                        )

                        if len(elements) >= self.max_elements_per_role:
                            break

                    except Exception:
                        continue

            except Exception:
                continue

            if len(elements) >= self.max_elements_per_role:
                break

        return elements

    async def _generate_stable_selector(
        self,
        element: "ElementHandle",
        page: "Page",
        fallback_selector: str = "",
    ) -> str | None:
        """Generate the most stable selector for an element.

        Priority: data-testid > data-component > id > aria-label > CSS path

        Args:
            element: Playwright ElementHandle.
            page: Playwright Page.
            fallback_selector: Fallback selector to use.

        Returns:
            Stable CSS selector or None if not possible.
        """
        # Try priority attributes
        for attr in self.test_id_patterns:
            try:
                value = await element.get_attribute(attr)
                if value:
                    # Escape special characters in value
                    escaped_value = value.replace('"', '\\"')
                    selector = f'[{attr}="{escaped_value}"]'
                    # Verify selector works
                    count = await page.locator(selector).count()
                    if count == 1:
                        return selector
            except Exception:
                pass

        # Try id attribute
        try:
            elem_id = await element.get_attribute("id")
            if elem_id and not elem_id.startswith(":"):  # Skip React-generated IDs
                selector = f"#{elem_id}"
                count = await page.locator(selector).count()
                if count == 1:
                    return selector
        except Exception:
            pass

        # Try aria-label
        try:
            aria_label = await element.get_attribute("aria-label")
            if aria_label:
                escaped_label = aria_label.replace('"', '\\"')
                selector = f'[aria-label="{escaped_label}"]'
                count = await page.locator(selector).count()
                if count == 1:
                    return selector
        except Exception:
            pass

        # Generate CSS path as fallback
        try:
            selector = await element.evaluate(
                """(el) => {
                    const path = [];
                    let current = el;
                    while (current && current.nodeType === Node.ELEMENT_NODE) {
                        let selector = current.tagName.toLowerCase();

                        // Add nth-child if needed for uniqueness
                        if (current.parentElement) {
                            const siblings = Array.from(current.parentElement.children);
                            const sameTag = siblings.filter(s => s.tagName === current.tagName);
                            if (sameTag.length > 1) {
                                const index = sameTag.indexOf(current) + 1;
                                selector += `:nth-of-type(${index})`;
                            }
                        }

                        path.unshift(selector);
                        current = current.parentElement;

                        // Stop at reasonable depth
                        if (path.length > 5) break;
                    }
                    return path.join(' > ');
                }"""
            )
            if selector:
                return selector
        except Exception:
            pass

        return fallback_selector or None

    async def _detect_repeated_elements(
        self,
        elements: list[DiscoveredElement],
        page: "Page",
    ) -> list[DiscoveredElement]:
        """Detect elements that are part of repeated patterns (lists/grids).

        Args:
            elements: List of discovered elements.
            page: Playwright Page.

        Returns:
            Updated list with is_repeated flag set.
        """
        # Group elements by role and tag
        groups: dict[tuple[UIRole, str | None], list[DiscoveredElement]] = {}
        for elem in elements:
            key = (elem.role, elem.tag_name)
            if key not in groups:
                groups[key] = []
            groups[key].append(elem)

        # Mark groups with 3+ similar elements as repeated
        for _key, group in groups.items():
            if len(group) >= 3:
                for elem in group:
                    elem.is_repeated = True

        return elements

    async def _get_component_name(
        self,
        element: "ElementHandle",
    ) -> str | None:
        """Extract component name from data attributes or React devtools.

        Args:
            element: Playwright ElementHandle.

        Returns:
            Component name or None.
        """
        # Try data-component attribute
        try:
            name = await element.get_attribute("data-component")
            if name:
                return name
        except Exception:
            pass

        # Try data-testid as component hint
        try:
            test_id = await element.get_attribute("data-testid")
            if test_id:
                # Extract component-like names from testid
                parts = test_id.replace("-", "_").split("_")
                if parts:
                    return parts[0].title()
        except Exception:
            pass

        # Try React fiber (if available)
        try:
            name = await element.evaluate(
                """(el) => {
                    // Try React 18 fiber
                    for (const key in el) {
                        if (key.startsWith('__reactFiber$')) {
                            const fiber = el[key];
                            if (fiber && fiber.type && typeof fiber.type === 'function') {
                                return fiber.type.displayName || fiber.type.name || null;
                            }
                        }
                    }
                    return null;
                }"""
            )
            if name:
                return name
        except Exception:
            pass

        return None


__all__ = [
    "UIRole",
    "DiscoveredElement",
    "ElementTargetingStrategy",
    "ROLE_SELECTORS",
]
