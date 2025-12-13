"""Unit tests for claude_indexer.rules.config module."""

import json

from claude_indexer.rules.base import Severity
from claude_indexer.rules.config import (
    CategoryConfig,
    PerformanceConfig,
    RuleConfig,
    RuleEngineConfig,
    RuleEngineConfigLoader,
    get_default_config,
)


class TestRuleConfig:
    """Tests for RuleConfig dataclass."""

    def test_rule_config_defaults(self):
        """Test default RuleConfig values."""
        config = RuleConfig()
        assert config.enabled is True
        assert config.severity_override is None
        assert config.parameters == {}

    def test_rule_config_from_dict(self):
        """Test creating RuleConfig from dictionary."""
        data = {
            "enabled": False,
            "severity": "critical",
            "parameters": {"max_length": 100},
        }
        config = RuleConfig.from_dict(data)
        assert config.enabled is False
        assert config.severity_override == "critical"
        assert config.parameters["max_length"] == 100

    def test_rule_config_from_dict_minimal(self):
        """Test creating RuleConfig with minimal data."""
        config = RuleConfig.from_dict({})
        assert config.enabled is True
        assert config.severity_override is None
        assert config.parameters == {}

    def test_rule_config_to_dict(self):
        """Test RuleConfig serialization."""
        config = RuleConfig(
            enabled=False,
            severity_override="high",
            parameters={"threshold": 10},
        )
        d = config.to_dict()
        assert d["enabled"] is False
        assert d["severity"] == "high"
        assert d["parameters"]["threshold"] == 10

    def test_rule_config_to_dict_minimal(self):
        """Test RuleConfig serialization with defaults."""
        config = RuleConfig()
        d = config.to_dict()
        assert d["enabled"] is True
        assert "severity" not in d  # None values excluded
        assert "parameters" not in d  # Empty dict excluded


class TestCategoryConfig:
    """Tests for CategoryConfig dataclass."""

    def test_category_config_defaults(self):
        """Test default CategoryConfig values."""
        config = CategoryConfig()
        assert config.enabled is True
        assert config.default_severity is None

    def test_category_config_from_dict(self):
        """Test creating CategoryConfig from dictionary."""
        data = {
            "enabled": False,
            "defaultSeverity": "high",
        }
        config = CategoryConfig.from_dict(data)
        assert config.enabled is False
        assert config.default_severity == "high"

    def test_category_config_to_dict(self):
        """Test CategoryConfig serialization."""
        config = CategoryConfig(enabled=True, default_severity="critical")
        d = config.to_dict()
        assert d["enabled"] is True
        assert d["defaultSeverity"] == "critical"


class TestPerformanceConfig:
    """Tests for PerformanceConfig dataclass."""

    def test_performance_config_defaults(self):
        """Test default PerformanceConfig values."""
        config = PerformanceConfig()
        assert config.fast_rule_timeout_ms == 50.0
        assert config.total_timeout_ms == 5000.0

    def test_performance_config_from_dict(self):
        """Test creating PerformanceConfig from dictionary."""
        data = {
            "fastRuleTimeoutMs": 100.0,
            "totalTimeoutMs": 10000.0,
        }
        config = PerformanceConfig.from_dict(data)
        assert config.fast_rule_timeout_ms == 100.0
        assert config.total_timeout_ms == 10000.0

    def test_performance_config_to_dict(self):
        """Test PerformanceConfig serialization."""
        config = PerformanceConfig(
            fast_rule_timeout_ms=75.0,
            total_timeout_ms=3000.0,
        )
        d = config.to_dict()
        assert d["fastRuleTimeoutMs"] == 75.0
        assert d["totalTimeoutMs"] == 3000.0


class TestRuleEngineConfig:
    """Tests for RuleEngineConfig dataclass."""

    def test_engine_config_defaults(self):
        """Test default RuleEngineConfig values."""
        config = RuleEngineConfig()
        assert config.enabled is True
        assert config.fail_on_severity == Severity.HIGH
        assert config.continue_on_error is True
        assert config.categories == {}
        assert config.rules == {}

    def test_engine_config_from_dict(self):
        """Test creating RuleEngineConfig from dictionary."""
        data = {
            "enabled": True,
            "failOnSeverity": "critical",
            "continueOnError": False,
            "performance": {
                "fastRuleTimeoutMs": 100.0,
                "totalTimeoutMs": 10000.0,
            },
            "categories": {
                "security": {
                    "enabled": True,
                    "defaultSeverity": "critical",
                }
            },
            "rules": {
                "TEST.RULE": {
                    "enabled": False,
                    "severity": "low",
                }
            },
        }
        config = RuleEngineConfig.from_dict(data)
        assert config.enabled is True
        assert config.fail_on_severity == Severity.CRITICAL
        assert config.continue_on_error is False
        assert config.performance.fast_rule_timeout_ms == 100.0
        assert "security" in config.categories
        assert config.categories["security"].default_severity == "critical"
        assert "TEST.RULE" in config.rules
        assert config.rules["TEST.RULE"].enabled is False

    def test_engine_config_is_rule_enabled(self):
        """Test checking if a rule is enabled."""
        config = RuleEngineConfig()
        config.rules["TEST.DISABLED"] = RuleConfig(enabled=False)

        assert config.is_rule_enabled("TEST.ENABLED") is True
        assert config.is_rule_enabled("TEST.DISABLED") is False

    def test_engine_config_is_rule_enabled_global_disable(self):
        """Test that global disable affects all rules."""
        config = RuleEngineConfig(enabled=False)
        assert config.is_rule_enabled("ANY.RULE") is False

    def test_engine_config_is_rule_enabled_category_disable(self):
        """Test that category disable affects rules in category."""
        config = RuleEngineConfig()
        config.categories["security"] = CategoryConfig(enabled=False)

        assert config.is_rule_enabled("TEST.RULE", "security") is False
        assert config.is_rule_enabled("TEST.RULE", "tech_debt") is True

    def test_engine_config_get_rule_config(self):
        """Test getting rule configuration."""
        config = RuleEngineConfig()
        config.rules["TEST.CONFIGURED"] = RuleConfig(
            enabled=True,
            severity_override="critical",
            parameters={"key": "value"},
        )

        configured = config.get_rule_config("TEST.CONFIGURED")
        assert configured.severity_override == "critical"
        assert configured.parameters["key"] == "value"

        # Non-configured rule gets default
        default = config.get_rule_config("TEST.DEFAULT")
        assert default.enabled is True
        assert default.severity_override is None

    def test_engine_config_get_rule_parameter(self):
        """Test getting specific rule parameters."""
        config = RuleEngineConfig()
        config.rules["TEST.RULE"] = RuleConfig(
            parameters={"threshold": 10, "mode": "strict"},
        )

        assert config.get_rule_parameter("TEST.RULE", "threshold") == 10
        assert config.get_rule_parameter("TEST.RULE", "mode") == "strict"
        assert config.get_rule_parameter("TEST.RULE", "missing") is None
        assert config.get_rule_parameter("TEST.RULE", "missing", 42) == 42

    def test_engine_config_to_dict(self):
        """Test RuleEngineConfig serialization."""
        config = RuleEngineConfig(
            enabled=True,
            fail_on_severity=Severity.CRITICAL,
        )
        d = config.to_dict()
        assert d["enabled"] is True
        assert d["failOnSeverity"] == "critical"

    def test_engine_config_merge(self):
        """Test merging configurations."""
        base = RuleEngineConfig(
            enabled=True,
            fail_on_severity=Severity.HIGH,
        )
        base.rules["TEST.1"] = RuleConfig(enabled=True)
        base.categories["security"] = CategoryConfig(enabled=True)

        override = RuleEngineConfig(
            fail_on_severity=Severity.CRITICAL,
        )
        override.rules["TEST.2"] = RuleConfig(enabled=False)
        override.categories["tech_debt"] = CategoryConfig(enabled=False)

        merged = base.merge(override)
        # Override values take precedence
        assert merged.fail_on_severity == Severity.CRITICAL
        # Both rules present
        assert "TEST.1" in merged.rules
        assert "TEST.2" in merged.rules
        # Both categories present
        assert "security" in merged.categories
        assert "tech_debt" in merged.categories


class TestRuleEngineConfigLoader:
    """Tests for RuleEngineConfigLoader class."""

    def test_loader_initialization(self, tmp_path):
        """Test loader initialization."""
        loader = RuleEngineConfigLoader(project_path=tmp_path)
        assert loader.project_path == tmp_path

    def test_loader_load_no_config(self, tmp_path):
        """Test loading when no config files exist."""
        loader = RuleEngineConfigLoader(project_path=tmp_path)
        config = loader.load()
        # Should return default config
        assert config.enabled is True

    def test_loader_load_project_config(self, tmp_path):
        """Test loading project configuration."""
        # Create .claude directory and config
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "guard.config.json"
        config_file.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "failOnSeverity": "critical",
                    "rules": {
                        "TEST.RULE": {"enabled": False},
                    },
                }
            )
        )

        loader = RuleEngineConfigLoader(project_path=tmp_path)
        config = loader.load()

        assert config.fail_on_severity == Severity.CRITICAL
        assert config.is_rule_enabled("TEST.RULE") is False

    def test_loader_load_local_override(self, tmp_path):
        """Test that local config overrides project config."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()

        # Project config
        project_config = claude_dir / "guard.config.json"
        project_config.write_text(
            json.dumps(
                {
                    "failOnSeverity": "high",
                    "rules": {"TEST.RULE": {"enabled": True}},
                }
            )
        )

        # Local override
        local_config = claude_dir / "guard.config.local.json"
        local_config.write_text(
            json.dumps(
                {
                    "failOnSeverity": "low",
                    "rules": {"TEST.RULE": {"enabled": False}},
                }
            )
        )

        loader = RuleEngineConfigLoader(project_path=tmp_path)
        config = loader.load()

        # Local should override project
        assert config.fail_on_severity == Severity.LOW
        assert config.is_rule_enabled("TEST.RULE") is False

    def test_loader_save_config(self, tmp_path):
        """Test saving configuration."""
        loader = RuleEngineConfigLoader(project_path=tmp_path)
        config = RuleEngineConfig(fail_on_severity=Severity.CRITICAL)

        saved_path = loader.save(config)
        assert saved_path.exists()

        # Verify saved content
        saved_data = json.loads(saved_path.read_text())
        assert saved_data["failOnSeverity"] == "critical"

    def test_loader_save_local_config(self, tmp_path):
        """Test saving local configuration."""
        loader = RuleEngineConfigLoader(project_path=tmp_path)
        config = RuleEngineConfig()

        saved_path = loader.save(config, local=True)
        assert "local" in saved_path.name

    def test_loader_handles_invalid_json(self, tmp_path):
        """Test loader handles invalid JSON gracefully."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        config_file = claude_dir / "guard.config.json"
        config_file.write_text("invalid json {{{")

        loader = RuleEngineConfigLoader(project_path=tmp_path)
        # Should return default config, not raise
        config = loader.load()
        assert config.enabled is True


class TestGetDefaultConfig:
    """Tests for get_default_config function."""

    def test_get_default_config(self):
        """Test getting default configuration."""
        config = get_default_config()
        assert config.enabled is True
        assert config.fail_on_severity == Severity.HIGH
        assert "security" in config.categories
        assert config.categories["security"].default_severity == "critical"
