"""
Configuration system for the code quality rule engine.

This module provides configuration dataclasses and loaders for
managing rule engine settings, including per-rule overrides,
category settings, and hierarchical configuration merging.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import Severity


@dataclass
class RuleConfig:
    """Configuration for a single rule."""

    enabled: bool = True
    severity_override: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleConfig":
        """Create RuleConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            severity_override=data.get("severity"),
            parameters=data.get("parameters", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"enabled": self.enabled}
        if self.severity_override:
            result["severity"] = self.severity_override
        if self.parameters:
            result["parameters"] = self.parameters
        return result


@dataclass
class CategoryConfig:
    """Configuration for a rule category."""

    enabled: bool = True
    default_severity: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryConfig":
        """Create CategoryConfig from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            default_severity=data.get("defaultSeverity"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {"enabled": self.enabled}
        if self.default_severity:
            result["defaultSeverity"] = self.default_severity
        return result


@dataclass
class PerformanceConfig:
    """Performance configuration for the rule engine."""

    fast_rule_timeout_ms: float = 50.0
    total_timeout_ms: float = 5000.0
    parallel_execution: bool = True
    max_parallel_workers: int = 4
    parallel_rule_timeout_ms: float = 30000.0  # 30 seconds per rule in parallel

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerformanceConfig":
        """Create PerformanceConfig from dictionary."""
        return cls(
            fast_rule_timeout_ms=data.get("fastRuleTimeoutMs", 50.0),
            total_timeout_ms=data.get("totalTimeoutMs", 5000.0),
            parallel_execution=data.get("parallelExecution", True),
            max_parallel_workers=data.get("maxParallelWorkers", 4),
            parallel_rule_timeout_ms=data.get("parallelRuleTimeoutMs", 30000.0),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "fastRuleTimeoutMs": self.fast_rule_timeout_ms,
            "totalTimeoutMs": self.total_timeout_ms,
            "parallelExecution": self.parallel_execution,
            "maxParallelWorkers": self.max_parallel_workers,
            "parallelRuleTimeoutMs": self.parallel_rule_timeout_ms,
        }


@dataclass
class RuleEngineConfig:
    """Configuration for the rule engine."""

    # Global settings
    enabled: bool = True
    fail_on_severity: Severity = field(default=Severity.HIGH)
    continue_on_error: bool = True

    # Performance settings
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)

    # Per-category settings
    categories: dict[str, CategoryConfig] = field(default_factory=dict)

    # Per-rule settings
    rules: dict[str, RuleConfig] = field(default_factory=dict)

    def is_rule_enabled(self, rule_id: str, category: str | None = None) -> bool:
        """Check if a rule is enabled.

        Args:
            rule_id: The rule identifier
            category: The rule's category (optional)

        Returns:
            True if the rule is enabled, False otherwise
        """
        if not self.enabled:
            return False

        # Check category-level setting
        if category and category in self.categories:
            if not self.categories[category].enabled:
                return False

        # Check rule-level setting
        if rule_id in self.rules:
            return self.rules[rule_id].enabled

        return True

    def get_rule_config(self, rule_id: str) -> RuleConfig:
        """Get configuration for a specific rule.

        Args:
            rule_id: The rule identifier

        Returns:
            RuleConfig for the rule (default if not configured)
        """
        return self.rules.get(rule_id, RuleConfig())

    def get_rule_parameter(
        self, rule_id: str, param_name: str, default: Any = None
    ) -> Any:
        """Get a specific parameter for a rule.

        Args:
            rule_id: The rule identifier
            param_name: The parameter name
            default: Default value if not configured

        Returns:
            The parameter value or default
        """
        config = self.get_rule_config(rule_id)
        return config.parameters.get(param_name, default)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleEngineConfig":
        """Create RuleEngineConfig from dictionary."""
        config = cls(
            enabled=data.get("enabled", True),
            continue_on_error=data.get("continueOnError", True),
        )

        # Parse fail_on_severity
        fail_on = data.get("failOnSeverity", "high")
        config.fail_on_severity = Severity(fail_on.lower())

        # Parse performance config
        if "performance" in data:
            config.performance = PerformanceConfig.from_dict(data["performance"])

        # Parse category configs
        if "categories" in data:
            for cat_name, cat_data in data["categories"].items():
                config.categories[cat_name] = CategoryConfig.from_dict(cat_data)

        # Parse rule configs
        if "rules" in data:
            for rule_id, rule_data in data["rules"].items():
                config.rules[rule_id] = RuleConfig.from_dict(rule_data)

        return config

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "enabled": self.enabled,
            "failOnSeverity": self.fail_on_severity.value,
            "continueOnError": self.continue_on_error,
            "performance": self.performance.to_dict(),
            "categories": {k: v.to_dict() for k, v in self.categories.items()},
            "rules": {k: v.to_dict() for k, v in self.rules.items()},
        }

    def merge(self, other: "RuleEngineConfig") -> "RuleEngineConfig":
        """Merge another config into this one (other takes precedence).

        Args:
            other: Configuration to merge in

        Returns:
            New RuleEngineConfig with merged settings
        """
        result = RuleEngineConfig(
            enabled=other.enabled,
            fail_on_severity=other.fail_on_severity,
            continue_on_error=other.continue_on_error,
            performance=PerformanceConfig(
                fast_rule_timeout_ms=other.performance.fast_rule_timeout_ms,
                total_timeout_ms=other.performance.total_timeout_ms,
                parallel_execution=other.performance.parallel_execution,
                max_parallel_workers=other.performance.max_parallel_workers,
                parallel_rule_timeout_ms=other.performance.parallel_rule_timeout_ms,
            ),
        )

        # Merge categories
        result.categories = dict(self.categories)
        result.categories.update(other.categories)

        # Merge rules
        result.rules = dict(self.rules)
        result.rules.update(other.rules)

        return result


class RuleEngineConfigLoader:
    """Loads rule engine configuration from guard.config.json."""

    CONFIG_FILENAME = "guard.config.json"
    LOCAL_CONFIG_FILENAME = "guard.config.local.json"
    GLOBAL_CONFIG_DIR = Path.home() / ".claude-indexer"

    def __init__(self, project_path: Path | None = None):
        """Initialize the config loader.

        Args:
            project_path: Path to the project root (defaults to CWD)
        """
        self.project_path = project_path or Path.cwd()

    def load(self) -> RuleEngineConfig:
        """Load configuration with hierarchical merging.

        Load order (later overrides earlier):
        1. Built-in defaults
        2. Global config (~/.claude-indexer/guard.config.json)
        3. Project config (<project>/.claude/guard.config.json)
        4. Local config (<project>/.claude/guard.config.local.json)

        Returns:
            Merged RuleEngineConfig
        """
        # Start with defaults
        config = RuleEngineConfig()

        # Load global config
        global_config_path = self.GLOBAL_CONFIG_DIR / self.CONFIG_FILENAME
        if global_config_path.exists():
            global_config = self._load_file(global_config_path)
            if global_config:
                config = config.merge(global_config)

        # Load project config
        project_config_path = self.project_path / ".claude" / self.CONFIG_FILENAME
        if project_config_path.exists():
            project_config = self._load_file(project_config_path)
            if project_config:
                config = config.merge(project_config)

        # Load local overrides
        local_config_path = self.project_path / ".claude" / self.LOCAL_CONFIG_FILENAME
        if local_config_path.exists():
            local_config = self._load_file(local_config_path)
            if local_config:
                config = config.merge(local_config)

        return config

    def _load_file(self, path: Path) -> RuleEngineConfig | None:
        """Load configuration from a file.

        Args:
            path: Path to the config file

        Returns:
            RuleEngineConfig or None if file couldn't be loaded
        """
        try:
            with open(path) as f:
                data = json.load(f)
            return RuleEngineConfig.from_dict(data)
        except (json.JSONDecodeError, OSError) as e:
            # Log warning but don't fail
            print(f"Warning: Could not load config from {path}: {e}")
            return None

    def save(self, config: RuleEngineConfig, local: bool = False) -> Path:
        """Save configuration to file.

        Args:
            config: Configuration to save
            local: If True, save to local config (git-ignored)

        Returns:
            Path to the saved config file
        """
        filename = self.LOCAL_CONFIG_FILENAME if local else self.CONFIG_FILENAME
        config_path = self.project_path / ".claude" / filename

        # Ensure directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

        return config_path


def get_default_config() -> RuleEngineConfig:
    """Get the default rule engine configuration.

    Returns:
        RuleEngineConfig with sensible defaults
    """
    return RuleEngineConfig(
        enabled=True,
        fail_on_severity=Severity.HIGH,
        continue_on_error=True,
        performance=PerformanceConfig(
            fast_rule_timeout_ms=50.0,
            total_timeout_ms=5000.0,
        ),
        categories={
            "security": CategoryConfig(enabled=True, default_severity="critical"),
            "tech_debt": CategoryConfig(enabled=True, default_severity="medium"),
            "resilience": CategoryConfig(enabled=True, default_severity="medium"),
            "documentation": CategoryConfig(enabled=True, default_severity="low"),
            "git": CategoryConfig(enabled=True, default_severity="critical"),
        },
    )
