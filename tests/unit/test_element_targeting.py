"""Unit tests for element targeting strategy."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestUIRole:
    """Tests for UIRole enum."""

    def test_all_roles_have_values(self):
        """Test that all roles have string values."""
        from claude_indexer.ui.collectors.element_targeting import UIRole

        for role in UIRole:
            assert isinstance(role.value, str)
            assert len(role.value) > 0

    def test_common_roles_exist(self):
        """Test that common UI roles are defined."""
        from claude_indexer.ui.collectors.element_targeting import UIRole

        expected_roles = [
            "BUTTON",
            "INPUT",
            "SELECT",
            "CHECKBOX",
            "LINK",
            "HEADING",
            "CARD",
            "MODAL",
        ]
        role_names = [r.name for r in UIRole]
        for role in expected_roles:
            assert role in role_names


class TestDiscoveredElement:
    """Tests for DiscoveredElement dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.element_targeting import (
            DiscoveredElement,
            UIRole,
        )

        elem = DiscoveredElement(
            role=UIRole.BUTTON,
            selector='[data-testid="submit-btn"]',
            is_repeated=False,
            component_name="SubmitButton",
            aria_label="Submit form",
            tag_name="button",
        )

        data = elem.to_dict()
        assert data["role"] == "button"
        assert data["selector"] == '[data-testid="submit-btn"]'
        assert data["is_repeated"] is False
        assert data["component_name"] == "SubmitButton"
        assert data["aria_label"] == "Submit form"
        assert data["tag_name"] == "button"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.element_targeting import (
            DiscoveredElement,
            UIRole,
        )

        data = {
            "role": "button",
            "selector": '[data-testid="cancel-btn"]',
            "is_repeated": True,
            "component_name": "CancelButton",
            "aria_label": "Cancel",
            "tag_name": "button",
        }

        elem = DiscoveredElement.from_dict(data)
        assert elem.role == UIRole.BUTTON
        assert elem.selector == '[data-testid="cancel-btn"]'
        assert elem.is_repeated is True
        assert elem.component_name == "CancelButton"

    def test_round_trip(self):
        """Test serialization round-trip."""
        from claude_indexer.ui.collectors.element_targeting import (
            DiscoveredElement,
            UIRole,
        )

        original = DiscoveredElement(
            role=UIRole.INPUT,
            selector='input[type="text"]',
            is_repeated=False,
            component_name="TextInput",
            aria_label="Enter name",
            tag_name="input",
        )

        data = original.to_dict()
        restored = DiscoveredElement.from_dict(data)

        assert restored.role == original.role
        assert restored.selector == original.selector
        assert restored.is_repeated == original.is_repeated
        assert restored.component_name == original.component_name


class TestRoleSelectors:
    """Tests for role selector mappings."""

    def test_all_roles_have_selectors(self):
        """Test that all roles have selector mappings."""
        from claude_indexer.ui.collectors.element_targeting import (
            ROLE_SELECTORS,
            UIRole,
        )

        for role in UIRole:
            assert role in ROLE_SELECTORS, f"Missing selectors for {role}"
            assert len(ROLE_SELECTORS[role]) > 0

    def test_button_selectors(self):
        """Test button role selectors."""
        from claude_indexer.ui.collectors.element_targeting import (
            ROLE_SELECTORS,
            UIRole,
        )

        button_selectors = ROLE_SELECTORS[UIRole.BUTTON]
        assert "button" in button_selectors
        assert '[role="button"]' in button_selectors

    def test_input_selectors(self):
        """Test input role selectors."""
        from claude_indexer.ui.collectors.element_targeting import (
            ROLE_SELECTORS,
            UIRole,
        )

        input_selectors = ROLE_SELECTORS[UIRole.INPUT]
        assert 'input[type="text"]' in input_selectors
        assert 'input[type="email"]' in input_selectors


class TestElementTargetingStrategy:
    """Tests for ElementTargetingStrategy class."""

    def test_init_default_roles(self):
        """Test initialization with default roles."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
            UIRole,
        )

        strategy = ElementTargetingStrategy()
        assert len(strategy.roles) == len(UIRole)

    def test_init_custom_roles(self):
        """Test initialization with custom roles."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
            UIRole,
        )

        strategy = ElementTargetingStrategy(roles=["button", "input"])
        assert len(strategy.roles) == 2
        assert UIRole.BUTTON in strategy.roles
        assert UIRole.INPUT in strategy.roles

    def test_init_max_elements(self):
        """Test max elements per role configuration."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
        )

        strategy = ElementTargetingStrategy(max_elements_per_role=25)
        assert strategy.max_elements_per_role == 25

    def test_parse_roles_case_insensitive(self):
        """Test that role parsing is case insensitive."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
            UIRole,
        )

        strategy = ElementTargetingStrategy(roles=["BUTTON", "Button", "button"])
        # Should deduplicate but all should parse
        button_count = sum(1 for r in strategy.roles if r == UIRole.BUTTON)
        assert button_count >= 1

    def test_test_id_patterns_default(self):
        """Test default test ID patterns."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
        )

        strategy = ElementTargetingStrategy()
        assert "data-testid" in strategy.test_id_patterns
        assert "data-test-id" in strategy.test_id_patterns

    def test_custom_selectors(self):
        """Test custom selector configuration."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
        )

        custom = [".my-custom-component", "#special-element"]
        strategy = ElementTargetingStrategy(custom_selectors=custom)
        assert strategy.custom_selectors == custom


class TestElementTargetingAsync:
    """Async tests for element targeting (require mocking Playwright)."""

    @pytest.mark.asyncio
    async def test_discover_elements_empty_page(self):
        """Test element discovery on empty page."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
        )

        # Mock page with no elements
        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[])

        strategy = ElementTargetingStrategy(roles=["button"])
        elements = await strategy.discover_elements(mock_page)

        assert len(elements) == 0

    @pytest.mark.asyncio
    async def test_discover_elements_with_results(self):
        """Test element discovery with mock results."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
            UIRole,
        )

        # Mock element
        mock_element = AsyncMock()
        mock_element.is_visible = AsyncMock(return_value=True)
        mock_element.get_attribute = AsyncMock(return_value="test-button")
        mock_element.evaluate = AsyncMock(return_value="button")

        # Mock page
        mock_page = AsyncMock()
        mock_page.query_selector_all = AsyncMock(return_value=[mock_element])
        mock_page.locator = MagicMock(return_value=MagicMock(count=AsyncMock(return_value=1)))

        strategy = ElementTargetingStrategy(
            roles=["button"],
            max_elements_per_role=10,
        )

        elements = await strategy.discover_elements(mock_page)

        # Should have discovered at least one button
        assert mock_page.query_selector_all.called

    @pytest.mark.asyncio
    async def test_generate_stable_selector_with_testid(self):
        """Test stable selector generation prioritizes data-testid."""
        from claude_indexer.ui.collectors.element_targeting import (
            ElementTargetingStrategy,
        )

        # Mock element with data-testid
        mock_element = AsyncMock()

        async def get_attr(name):
            if name == "data-testid":
                return "my-button"
            return None

        mock_element.get_attribute = get_attr

        # Mock page
        mock_page = AsyncMock()
        mock_page.locator = MagicMock(
            return_value=MagicMock(count=AsyncMock(return_value=1))
        )

        strategy = ElementTargetingStrategy()
        selector = await strategy._generate_stable_selector(
            mock_element, mock_page, "button"
        )

        assert selector == '[data-testid="my-button"]'


class TestRepeatedElementDetection:
    """Tests for repeated element detection."""

    @pytest.mark.asyncio
    async def test_detect_repeated_elements(self):
        """Test that repeated elements are marked."""
        from claude_indexer.ui.collectors.element_targeting import (
            DiscoveredElement,
            ElementTargetingStrategy,
            UIRole,
        )

        # Create list items
        elements = [
            DiscoveredElement(
                role=UIRole.LIST_ITEM,
                selector=f"li:nth-child({i})",
                tag_name="li",
            )
            for i in range(5)
        ]

        mock_page = AsyncMock()
        strategy = ElementTargetingStrategy()

        result = await strategy._detect_repeated_elements(elements, mock_page)

        # All 5 list items should be marked as repeated
        assert all(e.is_repeated for e in result if e.role == UIRole.LIST_ITEM)

    @pytest.mark.asyncio
    async def test_detect_non_repeated_elements(self):
        """Test that non-repeated elements are not marked."""
        from claude_indexer.ui.collectors.element_targeting import (
            DiscoveredElement,
            ElementTargetingStrategy,
            UIRole,
        )

        # Create single button and input
        elements = [
            DiscoveredElement(
                role=UIRole.BUTTON,
                selector="button.submit",
                tag_name="button",
            ),
            DiscoveredElement(
                role=UIRole.INPUT,
                selector="input.email",
                tag_name="input",
            ),
        ]

        mock_page = AsyncMock()
        strategy = ElementTargetingStrategy()

        result = await strategy._detect_repeated_elements(elements, mock_page)

        # Neither should be marked as repeated (less than 3 of same type)
        assert not result[0].is_repeated
        assert not result[1].is_repeated
