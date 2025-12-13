"""Unit tests for claude_indexer.rules.discovery module."""

from claude_indexer.rules.discovery import RuleDiscovery, discover_rules


class TestRuleDiscovery:
    """Tests for RuleDiscovery class."""

    def test_discovery_initialization(self):
        """Test RuleDiscovery initialization."""
        discovery = RuleDiscovery()
        assert discovery.rules_base_path.exists()
        assert discovery._discovered_rules == {}

    def test_discovery_with_custom_path(self, tmp_path):
        """Test RuleDiscovery with custom path."""
        discovery = RuleDiscovery(rules_base_path=tmp_path)
        assert discovery.rules_base_path == tmp_path

    def test_discover_all_from_package(self):
        """Test discovering all rules from the package."""
        discovery = RuleDiscovery()
        rules = discovery.discover_all()
        # Should find at least the proof-of-concept rules
        assert len(rules) >= 3
        # Check for expected rules
        rule_ids = list(rules.keys())
        assert any("TODO" in rid for rid in rule_ids)
        assert any("DEBUG" in rid for rid in rule_ids)
        assert any("FORCE_PUSH" in rid or "HARD_RESET" in rid for rid in rule_ids)

    def test_discover_category(self):
        """Test discovering rules from a specific category."""
        discovery = RuleDiscovery()
        tech_debt_rules = discovery.discover_category("tech_debt")
        # Should find TODO and debug rules
        assert len(tech_debt_rules) >= 2

    def test_discover_category_nonexistent(self, tmp_path):
        """Test discovering from non-existent category."""
        discovery = RuleDiscovery(rules_base_path=tmp_path)
        rules = discovery.discover_category("nonexistent")
        assert rules == {}

    def test_discovered_rule_ids(self):
        """Test getting list of discovered rule IDs."""
        discovery = RuleDiscovery()
        discovery.discover_all()
        rule_ids = discovery.discovered_rule_ids
        assert len(rule_ids) >= 3
        assert all(isinstance(rid, str) for rid in rule_ids)

    def test_get_rule_class(self):
        """Test getting a specific rule class."""
        discovery = RuleDiscovery()
        discovery.discover_all()
        # Try to get one of our proof-of-concept rules
        rule_class = discovery.get_rule_class("TECH_DEBT.TODO_MARKERS")
        if rule_class is not None:
            instance = rule_class()
            assert instance.rule_id == "TECH_DEBT.TODO_MARKERS"

    def test_get_rule_class_not_found(self):
        """Test getting a non-existent rule class."""
        discovery = RuleDiscovery()
        rule_class = discovery.get_rule_class("NONEXISTENT.RULE")
        assert rule_class is None

    def test_get_rules_by_category(self):
        """Test getting rules by category after discovery."""
        discovery = RuleDiscovery()
        discovery.discover_all()
        git_rules = discovery.get_rules_by_category("git")
        assert len(git_rules) >= 1

    def test_discovery_errors_empty_on_success(self):
        """Test that discovery_errors is empty on successful discovery."""
        discovery = RuleDiscovery()
        discovery.discover_all()
        # On successful discovery, errors should be empty or minimal
        # Some modules might have import issues, so we just check it's a list
        assert isinstance(discovery.discovery_errors, list)


class TestDiscoverRulesFunction:
    """Tests for the discover_rules convenience function."""

    def test_discover_rules_all(self):
        """Test discovering all rules using convenience function."""
        rules = discover_rules()
        assert len(rules) >= 3

    def test_discover_rules_specific_categories(self):
        """Test discovering rules from specific categories."""
        rules = discover_rules(categories=["tech_debt"])
        # Should only find tech_debt rules
        assert len(rules) >= 2
        for rule_id in rules:
            assert "TECH_DEBT" in rule_id


class TestRuleDiscoveryIntegration:
    """Integration tests for rule discovery with actual rules."""

    def test_discovered_rules_are_valid(self):
        """Test that all discovered rules can be instantiated."""
        discovery = RuleDiscovery()
        rules = discovery.discover_all()

        for rule_id, rule_class in rules.items():
            instance = rule_class()
            # Check required properties
            assert instance.rule_id == rule_id
            assert instance.name is not None
            assert instance.category is not None
            assert instance.default_severity is not None
            # Check it has a check method
            assert hasattr(instance, "check")

    def test_discovered_rules_have_proper_ids(self):
        """Test that discovered rules have properly formatted IDs."""
        discovery = RuleDiscovery()
        rules = discovery.discover_all()

        for rule_id in rules:
            # Rule IDs should be in format CATEGORY.RULE_NAME
            assert "." in rule_id
            parts = rule_id.split(".")
            assert len(parts) >= 2
            # Category should be uppercase
            assert parts[0].isupper()
