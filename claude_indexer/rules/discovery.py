"""
Rule discovery system for auto-loading rules from category directories.

This module provides automatic discovery and loading of rule classes
from the rules directory structure, enabling a plugin-like architecture
where new rules can be added by simply creating new files in the
appropriate category directories.
"""

import importlib
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseRule

logger = logging.getLogger(__name__)


class RuleDiscovery:
    """Auto-discovers rules from the rules directory structure.

    The discovery system scans category directories for Python modules
    containing BaseRule subclasses and loads them automatically.

    Directory structure:
        claude_indexer/rules/
        ├── security/
        │   ├── sql_injection.py
        │   └── xss_vulnerability.py
        ├── tech_debt/
        │   ├── todo_markers.py
        │   └── debug_statements.py
        └── ...
    """

    # Standard rule categories
    RULE_CATEGORIES = [
        "security",
        "tech_debt",
        "resilience",
        "documentation",
        "git",
    ]

    def __init__(self, rules_base_path: Path | None = None):
        """Initialize the rule discovery system.

        Args:
            rules_base_path: Base path for rules directory.
                           Defaults to the directory containing this file.
        """
        self.rules_base_path = rules_base_path or Path(__file__).parent
        self._discovered_rules: dict[str, type[BaseRule]] = {}
        self._discovery_errors: list[str] = []

    def discover_all(self) -> dict[str, type["BaseRule"]]:
        """Discover all rules from all category directories.

        Returns:
            Dictionary mapping rule_id to rule class
        """
        self._discovered_rules.clear()
        self._discovery_errors.clear()

        for category in self.RULE_CATEGORIES:
            self._discover_category(category)

        if self._discovery_errors:
            logger.warning(
                f"Rule discovery completed with {len(self._discovery_errors)} errors"
            )

        return self._discovered_rules

    def discover_category(self, category: str) -> dict[str, type["BaseRule"]]:
        """Discover rules from a specific category.

        Args:
            category: Category name (e.g., 'security', 'tech_debt')

        Returns:
            Dictionary mapping rule_id to rule class for this category
        """
        category_rules: dict[str, type[BaseRule]] = {}
        category_path = self.rules_base_path / category

        if not category_path.exists():
            return category_rules

        for module_file in category_path.glob("*.py"):
            if module_file.name.startswith("_"):
                continue

            rules = self._load_rules_from_module(category, module_file)
            for rule_id, rule_class in rules.items():
                category_rules[rule_id] = rule_class
                self._discovered_rules[rule_id] = rule_class

        return category_rules

    def _discover_category(self, category: str) -> None:
        """Internal method to discover rules from a category directory.

        Args:
            category: Category name
        """
        category_path = self.rules_base_path / category
        if not category_path.exists():
            logger.debug(f"Category directory not found: {category_path}")
            return

        if not category_path.is_dir():
            return

        for module_file in category_path.glob("*.py"):
            if module_file.name.startswith("_"):
                continue

            try:
                rules = self._load_rules_from_module(category, module_file)
                self._discovered_rules.update(rules)
            except Exception as e:
                error_msg = f"Error loading rules from {module_file}: {e}"
                logger.warning(error_msg)
                self._discovery_errors.append(error_msg)

    def _load_rules_from_module(
        self, category: str, module_file: Path
    ) -> dict[str, type["BaseRule"]]:
        """Load rule classes from a module file.

        Args:
            category: Category name
            module_file: Path to the Python module file

        Returns:
            Dictionary mapping rule_id to rule class
        """
        from .base import BaseRule

        rules: dict[str, type[BaseRule]] = {}

        # Build module name
        module_name = f"claude_indexer.rules.{category}.{module_file.stem}"

        try:
            # Load the module
            spec = importlib.util.spec_from_file_location(module_name, module_file)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for {module_file}")
                return rules

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find all BaseRule subclasses in the module
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Must be a subclass of BaseRule but not BaseRule itself
                if not issubclass(obj, BaseRule) or obj is BaseRule:
                    continue

                # Must be defined in this module (not imported)
                if obj.__module__ != module_name:
                    continue

                # Must not be abstract
                if inspect.isabstract(obj):
                    continue

                # Instantiate to get rule_id
                try:
                    instance = obj()
                    rule_id = instance.rule_id
                    rules[rule_id] = obj
                    logger.debug(f"Discovered rule: {rule_id} from {module_file}")
                except Exception as e:
                    logger.warning(
                        f"Could not instantiate rule {name} from {module_file}: {e}"
                    )

        except Exception as e:
            logger.warning(f"Error loading module {module_file}: {e}")

        return rules

    @property
    def discovery_errors(self) -> list[str]:
        """Get list of errors encountered during discovery.

        Returns:
            List of error messages
        """
        return self._discovery_errors.copy()

    @property
    def discovered_rule_ids(self) -> list[str]:
        """Get list of discovered rule IDs.

        Returns:
            List of rule IDs
        """
        return list(self._discovered_rules.keys())

    def get_rule_class(self, rule_id: str) -> type["BaseRule"] | None:
        """Get a specific rule class by ID.

        Args:
            rule_id: The rule identifier

        Returns:
            Rule class or None if not found
        """
        return self._discovered_rules.get(rule_id)

    def get_rules_by_category(self, category: str) -> dict[str, type["BaseRule"]]:
        """Get all rules for a specific category.

        Args:
            category: Category name

        Returns:
            Dictionary mapping rule_id to rule class
        """
        return {
            rule_id: rule_class
            for rule_id, rule_class in self._discovered_rules.items()
            if rule_id.split(".")[0].lower() == category.lower()
            or rule_class().category == category
        }


def discover_rules(
    rules_path: Path | None = None,
    categories: list[str] | None = None,
) -> dict[str, type["BaseRule"]]:
    """Convenience function to discover rules.

    Args:
        rules_path: Base path for rules directory
        categories: Optional list of categories to discover

    Returns:
        Dictionary mapping rule_id to rule class
    """
    discovery = RuleDiscovery(rules_path)

    if categories:
        rules: dict[str, type[BaseRule]] = {}
        for category in categories:
            rules.update(discovery.discover_category(category))
        return rules

    return discovery.discover_all()
