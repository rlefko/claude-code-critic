"""Unit tests for risk mitigation configurations."""

from claude_indexer.ui.config import (
    DeterministicDataConfig,
    PIIRedactionConfig,
    RiskMitigationConfig,
    StorybookPreferenceConfig,
    UIQualityConfig,
)


class TestDeterministicDataConfig:
    """Tests for DeterministicDataConfig."""

    def test_config_defaults(self):
        """Default values should be set correctly."""
        config = DeterministicDataConfig()

        assert config.enabled is False
        assert config.seed == 42
        assert config.mock_timestamps is True
        assert config.mock_user_data is True

    def test_config_serialization(self):
        """to_dict/from_dict should preserve all fields."""
        original = DeterministicDataConfig(
            enabled=True,
            seed=123,
            mock_timestamps=False,
            mock_user_data=False,
        )

        data = original.to_dict()
        restored = DeterministicDataConfig.from_dict(data)

        assert restored.enabled == original.enabled
        assert restored.seed == original.seed
        assert restored.mock_timestamps == original.mock_timestamps
        assert restored.mock_user_data == original.mock_user_data

    def test_config_from_empty_dict(self):
        """from_dict should handle empty dict with defaults."""
        config = DeterministicDataConfig.from_dict({})

        assert config.enabled is False
        assert config.seed == 42


class TestPIIRedactionConfig:
    """Tests for PIIRedactionConfig."""

    def test_config_defaults(self):
        """Default values should enable redaction."""
        config = PIIRedactionConfig()

        assert config.enabled is True
        assert config.redact_emails is True
        assert config.redact_names is True
        assert config.redact_phone_numbers is True
        assert config.redact_addresses is True
        assert config.redaction_placeholder == "[REDACTED]"
        assert config.blur_images is True
        assert config.custom_patterns == []

    def test_config_serialization(self):
        """to_dict/from_dict should preserve all fields."""
        original = PIIRedactionConfig(
            enabled=True,
            redact_emails=False,
            custom_patterns=[r"\d{3}-\d{2}-\d{4}"],  # SSN pattern
            redaction_placeholder="***",
        )

        data = original.to_dict()
        restored = PIIRedactionConfig.from_dict(data)

        assert restored.enabled == original.enabled
        assert restored.redact_emails == original.redact_emails
        assert restored.custom_patterns == original.custom_patterns
        assert restored.redaction_placeholder == original.redaction_placeholder

    def test_custom_patterns_preserved(self):
        """Custom regex patterns should be preserved."""
        config = PIIRedactionConfig(
            custom_patterns=[
                r"\b[A-Z]{2}\d{6}\b",  # License plate
                r"\b\d{4}-\d{4}-\d{4}-\d{4}\b",  # Credit card
            ]
        )

        data = config.to_dict()
        restored = PIIRedactionConfig.from_dict(data)

        assert len(restored.custom_patterns) == 2
        assert r"\b[A-Z]{2}\d{6}\b" in restored.custom_patterns


class TestStorybookPreferenceConfig:
    """Tests for StorybookPreferenceConfig."""

    def test_config_defaults(self):
        """Default values should prefer Storybook."""
        config = StorybookPreferenceConfig()

        assert config.prefer_storybook is True
        assert config.storybook_only is False
        assert config.story_patterns == ["*"]
        assert config.skip_stories == []

    def test_config_serialization(self):
        """to_dict/from_dict should preserve all fields."""
        original = StorybookPreferenceConfig(
            prefer_storybook=True,
            storybook_only=True,
            story_patterns=["Button*", "Input*"],
            skip_stories=["WIP/*"],
        )

        data = original.to_dict()
        restored = StorybookPreferenceConfig.from_dict(data)

        assert restored.prefer_storybook == original.prefer_storybook
        assert restored.storybook_only == original.storybook_only
        assert restored.story_patterns == original.story_patterns
        assert restored.skip_stories == original.skip_stories

    def test_story_patterns_filtering(self):
        """Story patterns should be preserved for filtering."""
        config = StorybookPreferenceConfig(
            story_patterns=["Components/**", "!Components/Internal/**"],
            skip_stories=["Deprecated/*"],
        )

        assert "Components/**" in config.story_patterns
        assert "Deprecated/*" in config.skip_stories


class TestRiskMitigationConfig:
    """Tests for RiskMitigationConfig."""

    def test_config_defaults(self):
        """Default values should have nested configs."""
        config = RiskMitigationConfig()

        assert isinstance(config.deterministic_data, DeterministicDataConfig)
        assert isinstance(config.pii_redaction, PIIRedactionConfig)
        assert isinstance(config.storybook_preference, StorybookPreferenceConfig)

    def test_config_serialization(self):
        """to_dict/from_dict should preserve nested configs."""
        original = RiskMitigationConfig(
            deterministic_data=DeterministicDataConfig(enabled=True, seed=999),
            pii_redaction=PIIRedactionConfig(enabled=False),
            storybook_preference=StorybookPreferenceConfig(storybook_only=True),
        )

        data = original.to_dict()
        restored = RiskMitigationConfig.from_dict(data)

        assert restored.deterministic_data.enabled is True
        assert restored.deterministic_data.seed == 999
        assert restored.pii_redaction.enabled is False
        assert restored.storybook_preference.storybook_only is True

    def test_config_from_empty_dict(self):
        """from_dict should handle empty dict with default nested configs."""
        config = RiskMitigationConfig.from_dict({})

        assert config.deterministic_data.enabled is False
        assert config.pii_redaction.enabled is True
        assert config.storybook_preference.prefer_storybook is True


class TestUIQualityConfigWithRiskMitigation:
    """Tests for UIQualityConfig with risk mitigation."""

    def test_config_includes_risk_mitigation(self):
        """UIQualityConfig should include risk_mitigation field."""
        config = UIQualityConfig()

        assert hasattr(config, "risk_mitigation")
        assert isinstance(config.risk_mitigation, RiskMitigationConfig)

    def test_config_serialization_with_risk_mitigation(self):
        """to_dict/from_dict should preserve risk_mitigation."""
        original = UIQualityConfig()
        original.risk_mitigation = RiskMitigationConfig(
            deterministic_data=DeterministicDataConfig(enabled=True),
        )

        data = original.to_dict()
        assert "riskMitigation" in data

        restored = UIQualityConfig.from_dict(data)
        assert restored.risk_mitigation.deterministic_data.enabled is True

    def test_config_from_dict_without_risk_mitigation(self):
        """from_dict should handle missing riskMitigation field."""
        data = {
            "designSystem": {},
            "crawl": {},
            "gating": {},
            # No riskMitigation field
        }

        config = UIQualityConfig.from_dict(data)

        # Should have default risk mitigation config
        assert isinstance(config.risk_mitigation, RiskMitigationConfig)
        assert config.risk_mitigation.pii_redaction.enabled is True


class TestRiskMitigationIntegration:
    """Integration tests for risk mitigation features."""

    def test_deterministic_mode_seed_consistency(self):
        """Same seed should produce same config."""
        config1 = DeterministicDataConfig(enabled=True, seed=42)
        config2 = DeterministicDataConfig(enabled=True, seed=42)

        assert config1.seed == config2.seed

    def test_pii_redaction_all_types_enabled(self):
        """All PII types should be redactable by default."""
        config = PIIRedactionConfig()

        assert config.redact_emails is True
        assert config.redact_names is True
        assert config.redact_phone_numbers is True
        assert config.redact_addresses is True

    def test_storybook_preference_over_routes(self):
        """Storybook should be preferred by default."""
        config = StorybookPreferenceConfig()

        assert config.prefer_storybook is True
        assert config.storybook_only is False  # But not exclusively
