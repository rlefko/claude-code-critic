"""Unit tests for UI quality configuration."""

import json

from claude_indexer.ui.config import (
    AllowedScales,
    CrawlConfig,
    DesignSystemConfig,
    GatingConfig,
    IgnoreRule,
    OutputConfig,
    SeverityThresholds,
    SimilarityThresholds,
    UIConfigLoader,
    UIQualityConfig,
    ViewportConfig,
    load_ui_config,
)


class TestViewportConfig:
    """Tests for ViewportConfig."""

    def test_create_viewport(self):
        """Test basic ViewportConfig creation."""
        viewport = ViewportConfig(name="mobile", width=375, height=812)

        assert viewport.name == "mobile"
        assert viewport.width == 375
        assert viewport.height == 812

    def test_viewport_round_trip(self):
        """Test ViewportConfig serialization round-trip."""
        viewport = ViewportConfig(name="desktop", width=1440, height=900)

        data = viewport.to_dict()
        restored = ViewportConfig.from_dict(data)

        assert restored.name == "desktop"
        assert restored.width == 1440


class TestSeverityThresholds:
    """Tests for SeverityThresholds."""

    def test_default_thresholds(self):
        """Test default severity thresholds."""
        thresholds = SeverityThresholds()

        assert thresholds.token_drift == "FAIL"
        assert thresholds.duplication == "WARN"
        assert thresholds.inconsistency == "WARN"

    def test_custom_thresholds(self):
        """Test custom severity thresholds."""
        thresholds = SeverityThresholds(
            token_drift="WARN",
            duplication="INFO",
        )

        assert thresholds.token_drift == "WARN"
        assert thresholds.duplication == "INFO"


class TestSimilarityThresholds:
    """Tests for SimilarityThresholds."""

    def test_default_similarity(self):
        """Test default similarity thresholds."""
        thresholds = SimilarityThresholds()

        assert thresholds.duplicate == 0.95
        assert thresholds.near_duplicate == 0.80
        assert thresholds.component_reuse == 0.75

    def test_custom_similarity(self):
        """Test custom similarity thresholds."""
        thresholds = SimilarityThresholds(
            duplicate=0.98,
            near_duplicate=0.85,
        )

        assert thresholds.duplicate == 0.98
        assert thresholds.near_duplicate == 0.85


class TestGatingConfig:
    """Tests for GatingConfig."""

    def test_default_gating(self):
        """Test default gating configuration."""
        config = GatingConfig()

        assert config.baseline_mode is True
        assert config.fail_only_on_new is True
        assert config.min_confidence == 0.7
        assert config.require_multi_evidence is True

    def test_gating_round_trip(self):
        """Test GatingConfig serialization round-trip."""
        config = GatingConfig(
            baseline_mode=False,
            min_confidence=0.8,
        )

        data = config.to_dict()
        restored = GatingConfig.from_dict(data)

        assert restored.baseline_mode is False
        assert restored.min_confidence == 0.8


class TestIgnoreRule:
    """Tests for IgnoreRule."""

    def test_create_ignore_rule(self):
        """Test basic IgnoreRule creation."""
        rule = IgnoreRule(
            rule="COLOR.NON_TOKEN",
            reason="Legacy code, will be refactored in Q2",
        )

        assert rule.rule == "COLOR.NON_TOKEN"
        assert rule.reason == "Legacy code, will be refactored in Q2"
        assert rule.paths == []
        assert rule.expiry is None

    def test_ignore_rule_with_paths(self):
        """Test IgnoreRule with path patterns."""
        rule = IgnoreRule(
            rule="STYLE.DUPLICATE_SET",
            reason="Intentional duplication for testing",
            paths=["tests/**", "fixtures/**"],
            expiry="2025-06-01",
        )

        assert len(rule.paths) == 2
        assert rule.expiry == "2025-06-01"

    def test_ignore_rule_round_trip(self):
        """Test IgnoreRule serialization round-trip."""
        rule = IgnoreRule(
            rule="COMPONENT.DUPLICATE_CLUSTER",
            reason="Under refactor",
            paths=["src/legacy/**"],
        )

        data = rule.to_dict()
        restored = IgnoreRule.from_dict(data)

        assert restored.rule == "COMPONENT.DUPLICATE_CLUSTER"
        assert restored.paths == ["src/legacy/**"]


class TestCrawlConfig:
    """Tests for CrawlConfig."""

    def test_default_crawl(self):
        """Test default crawl configuration."""
        config = CrawlConfig()

        assert config.storybook_url is None
        assert config.max_pages_per_run == 50
        assert config.disable_animations is True
        assert len(config.viewports) == 3  # mobile, tablet, desktop

    def test_crawl_with_storybook(self):
        """Test crawl configuration with Storybook."""
        config = CrawlConfig(
            storybook_url="http://localhost:6006",
            storybook_start_command="npm run storybook",
        )

        assert config.storybook_url == "http://localhost:6006"
        assert config.storybook_start_command == "npm run storybook"

    def test_crawl_round_trip(self):
        """Test CrawlConfig serialization round-trip."""
        config = CrawlConfig(
            routes=["/", "/about", "/contact"],
            max_pages_per_run=100,
        )

        data = config.to_dict()
        restored = CrawlConfig.from_dict(data)

        assert restored.routes == ["/", "/about", "/contact"]
        assert restored.max_pages_per_run == 100


class TestAllowedScales:
    """Tests for AllowedScales."""

    def test_default_scales(self):
        """Test default allowed scales."""
        scales = AllowedScales()

        assert 0 in scales.spacing
        assert 8 in scales.spacing
        assert 16 in scales.spacing
        assert 4 in scales.radius
        assert 9999 in scales.radius  # full

    def test_custom_scales(self):
        """Test custom allowed scales."""
        scales = AllowedScales(
            spacing=[0, 4, 8, 16, 32],
            radius=[0, 4, 8],
        )

        assert scales.spacing == [0, 4, 8, 16, 32]
        assert scales.radius == [0, 4, 8]


class TestDesignSystemConfig:
    """Tests for DesignSystemConfig."""

    def test_default_design_system(self):
        """Test default design system configuration."""
        config = DesignSystemConfig()

        assert config.token_sources == []
        assert config.allowed_scales is not None

    def test_design_system_with_sources(self):
        """Test design system with token sources."""
        config = DesignSystemConfig(
            token_sources=["./tokens.css", "tailwind.config.js"],
        )

        assert len(config.token_sources) == 2


class TestOutputConfig:
    """Tests for OutputConfig."""

    def test_default_output(self):
        """Test default output configuration."""
        config = OutputConfig()

        assert config.format == "json"
        assert config.include_screenshots is True
        assert config.screenshot_dir == ".ui-quality/screenshots"

    def test_output_html(self):
        """Test HTML output configuration."""
        config = OutputConfig(
            format="html",
            report_dir="./reports",
        )

        assert config.format == "html"
        assert config.report_dir == "./reports"


class TestUIQualityConfig:
    """Tests for UIQualityConfig."""

    def test_default_config(self):
        """Test default UI quality configuration."""
        config = UIQualityConfig()

        assert config.design_system is not None
        assert config.crawl is not None
        assert config.gating is not None
        assert config.ignore_rules == []

    def test_config_to_dict(self):
        """Test UIQualityConfig serialization."""
        config = UIQualityConfig()
        data = config.to_dict()

        assert "designSystem" in data
        assert "crawl" in data
        assert "gating" in data
        assert "ignoreRules" in data
        assert "output" in data

    def test_config_round_trip(self):
        """Test UIQualityConfig serialization round-trip."""
        config = UIQualityConfig(
            design_system=DesignSystemConfig(token_sources=["./tokens.json"]),
            gating=GatingConfig(min_confidence=0.9),
            ignore_rules=[
                IgnoreRule(rule="TEST.RULE", reason="Testing"),
            ],
        )

        data = config.to_dict()
        restored = UIQualityConfig.from_dict(data)

        assert restored.design_system.token_sources == ["./tokens.json"]
        assert restored.gating.min_confidence == 0.9
        assert len(restored.ignore_rules) == 1

    def test_is_rule_ignored(self):
        """Test rule ignore checking."""
        config = UIQualityConfig(
            ignore_rules=[
                IgnoreRule(rule="COLOR.NON_TOKEN", reason="Legacy"),
                IgnoreRule(
                    rule="STYLE.DUPLICATE_SET",
                    reason="Test files",
                    paths=["tests/**"],
                ),
            ],
        )

        # Rule is globally ignored
        assert config.is_rule_ignored("COLOR.NON_TOKEN") is True
        assert config.is_rule_ignored("COLOR.NON_TOKEN", "/src/Button.tsx") is True

        # Rule is only ignored for certain paths
        assert (
            config.is_rule_ignored("STYLE.DUPLICATE_SET") is True
        )  # No path = applies
        assert (
            config.is_rule_ignored("STYLE.DUPLICATE_SET", "tests/Button.test.tsx")
            is True
        )
        assert config.is_rule_ignored("STYLE.DUPLICATE_SET", "src/Button.tsx") is False

        # Unknown rule is not ignored
        assert config.is_rule_ignored("UNKNOWN.RULE") is False

    def test_is_rule_ignored_expired(self):
        """Test expired rule ignore."""
        config = UIQualityConfig(
            ignore_rules=[
                IgnoreRule(
                    rule="OLD.RULE",
                    reason="Temporary",
                    expiry="2020-01-01",  # Past date
                ),
            ],
        )

        # Expired ignore should not apply
        assert config.is_rule_ignored("OLD.RULE") is False


class TestUIConfigLoader:
    """Tests for UIConfigLoader."""

    def test_load_defaults(self, tmp_path):
        """Test loading default configuration when no file exists."""
        loader = UIConfigLoader(tmp_path)
        config = loader.load()

        assert config is not None
        assert isinstance(config, UIQualityConfig)

    def test_load_from_file(self, tmp_path):
        """Test loading configuration from file."""
        config_data = {
            "designSystem": {
                "tokenSources": ["./custom-tokens.css"],
            },
            "gating": {
                "minConfidence": 0.85,
            },
        }

        config_file = tmp_path / "ui-quality.config.json"
        config_file.write_text(json.dumps(config_data))

        loader = UIConfigLoader(tmp_path)
        config = loader.load()

        assert config.design_system.token_sources == ["./custom-tokens.css"]
        assert config.gating.min_confidence == 0.85

    def test_load_from_env(self, tmp_path, monkeypatch):
        """Test loading configuration from environment variable."""
        config_data = {
            "gating": {
                "baselineMode": False,
            },
        }

        env_config_file = tmp_path / "env-config.json"
        env_config_file.write_text(json.dumps(config_data))

        monkeypatch.setenv("UI_QUALITY_CONFIG", str(env_config_file))

        loader = UIConfigLoader(tmp_path)
        config = loader.load()

        assert config.gating.baseline_mode is False

    def test_save_config(self, tmp_path):
        """Test saving configuration to file."""
        config = UIQualityConfig(
            design_system=DesignSystemConfig(token_sources=["./tokens.css"]),
        )

        loader = UIConfigLoader(tmp_path)
        saved_path = loader.save(config)

        assert saved_path.exists()

        # Verify saved content
        saved_data = json.loads(saved_path.read_text())
        assert saved_data["designSystem"]["tokenSources"] == ["./tokens.css"]


class TestLoadUIConfig:
    """Tests for load_ui_config convenience function."""

    def test_load_ui_config(self, tmp_path):
        """Test load_ui_config convenience function."""
        config = load_ui_config(tmp_path)

        assert config is not None
        assert isinstance(config, UIQualityConfig)


class TestTokenLoading:
    """Tests for token loading functionality."""

    def test_load_tokens_empty(self, tmp_path):
        """Test loading tokens with no sources."""
        config = UIQualityConfig()
        tokens = config.load_tokens(tmp_path)

        # Should have scale tokens from defaults
        assert tokens is not None
        assert len(tokens.spacing) > 0  # From allowed scales

    def test_load_tokens_from_css(self, tmp_path):
        """Test loading tokens from CSS file."""
        css_content = """
        :root {
            --color-primary: #3B82F6;
            --spacing-4: 16px;
        }
        """
        css_file = tmp_path / "tokens.css"
        css_file.write_text(css_content)

        config = UIQualityConfig(
            design_system=DesignSystemConfig(token_sources=["tokens.css"]),
        )

        tokens = config.load_tokens(tmp_path)

        assert "color-primary" in tokens.colors
        assert "spacing-4" in tokens.spacing

    def test_load_tokens_caching(self, tmp_path):
        """Test that token loading is cached."""
        config = UIQualityConfig()

        tokens1 = config.load_tokens(tmp_path)
        tokens2 = config.load_tokens(tmp_path)

        # Should return same instance (cached)
        assert tokens1 is tokens2

    def test_add_scale_tokens(self, tmp_path):
        """Test that allowed scales are added as tokens."""
        config = UIQualityConfig(
            design_system=DesignSystemConfig(
                allowed_scales=AllowedScales(
                    spacing=[0, 8, 16],
                    radius=[0, 4, 9999],
                ),
            ),
        )

        tokens = config.load_tokens(tmp_path)

        # Check spacing scale tokens
        assert "scale-0" in tokens.spacing
        assert "scale-8" in tokens.spacing
        assert "scale-16" in tokens.spacing

        # Check radius scale tokens
        assert "radius-0" in tokens.radii
        assert "radius-4" in tokens.radii
        assert "radius-full" in tokens.radii
