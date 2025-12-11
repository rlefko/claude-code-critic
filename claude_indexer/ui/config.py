"""UI Quality configuration loader.

Loads and validates ui-quality.config.json configuration files.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..indexer_logging import get_logger
from .token_adapters import get_default_registry
from .tokens import TokenSet, TypographyToken

logger = get_logger()

# Default configuration file name
CONFIG_FILENAME = "ui-quality.config.json"


@dataclass
class ViewportConfig:
    """Configuration for a viewport size."""

    name: str
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ViewportConfig":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            width=data["width"],
            height=data["height"],
        )


@dataclass
class ElementTargetingConfig:
    """Configuration for element targeting during crawl."""

    roles: list[str] = field(default_factory=lambda: [
        "button", "link", "textbox", "checkbox", "radio", "combobox",
        "listbox", "menu", "menuitem", "tab", "tabpanel", "dialog",
        "alert", "heading", "img", "navigation", "main"
    ])
    selectors: list[str] = field(default_factory=list)
    test_id_patterns: list[str] = field(
        default_factory=lambda: ["data-testid", "data-test-id", "data-cy"]
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "roles": self.roles,
            "selectors": self.selectors,
            "testIdPatterns": self.test_id_patterns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementTargetingConfig":
        """Create from dictionary."""
        return cls(
            roles=data.get("roles", cls.__dataclass_fields__["roles"].default_factory()),
            selectors=data.get("selectors", []),
            test_id_patterns=data.get("testIdPatterns", ["data-testid", "data-test-id", "data-cy"]),
        )


@dataclass
class CrawlConfig:
    """Configuration for Playwright runtime analysis."""

    storybook_url: str | None = None
    storybook_start_command: str | None = None
    routes: list[str] = field(default_factory=list)
    sitemap_url: str | None = None
    viewports: list[ViewportConfig] = field(
        default_factory=lambda: [
            ViewportConfig("mobile", 375, 812),
            ViewportConfig("tablet", 768, 1024),
            ViewportConfig("desktop", 1440, 900),
        ]
    )
    element_targeting: ElementTargetingConfig = field(
        default_factory=ElementTargetingConfig
    )
    max_pages_per_run: int = 50
    max_elements_per_role: int = 50
    disable_animations: bool = True
    wait_for_stable_layout: bool = True
    stable_layout_timeout: int = 3000

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "storybookUrl": self.storybook_url,
            "storybookStartCommand": self.storybook_start_command,
            "routes": self.routes,
            "sitemapUrl": self.sitemap_url,
            "viewports": [v.to_dict() for v in self.viewports],
            "elementTargeting": self.element_targeting.to_dict(),
            "maxPagesPerRun": self.max_pages_per_run,
            "maxElementsPerRole": self.max_elements_per_role,
            "disableAnimations": self.disable_animations,
            "waitForStableLayout": self.wait_for_stable_layout,
            "stableLayoutTimeout": self.stable_layout_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlConfig":
        """Create from dictionary."""
        viewports = [
            ViewportConfig.from_dict(v) for v in data.get("viewports", [])
        ]
        if not viewports:
            viewports = cls.__dataclass_fields__["viewports"].default_factory()

        element_targeting = ElementTargetingConfig.from_dict(
            data.get("elementTargeting", {})
        )

        return cls(
            storybook_url=data.get("storybookUrl"),
            storybook_start_command=data.get("storybookStartCommand"),
            routes=data.get("routes", []),
            sitemap_url=data.get("sitemapUrl"),
            viewports=viewports,
            element_targeting=element_targeting,
            max_pages_per_run=data.get("maxPagesPerRun", 50),
            max_elements_per_role=data.get("maxElementsPerRole", 50),
            disable_animations=data.get("disableAnimations", True),
            wait_for_stable_layout=data.get("waitForStableLayout", True),
            stable_layout_timeout=data.get("stableLayoutTimeout", 3000),
        )


@dataclass
class SeverityThresholds:
    """Severity thresholds for different rule categories."""

    token_drift: str = "FAIL"
    duplication: str = "WARN"
    inconsistency: str = "WARN"
    smells: str = "WARN"
    accessibility: str = "WARN"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tokenDrift": self.token_drift,
            "duplication": self.duplication,
            "inconsistency": self.inconsistency,
            "smells": self.smells,
            "accessibility": self.accessibility,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SeverityThresholds":
        """Create from dictionary."""
        return cls(
            token_drift=data.get("tokenDrift", "FAIL"),
            duplication=data.get("duplication", "WARN"),
            inconsistency=data.get("inconsistency", "WARN"),
            smells=data.get("smells", "WARN"),
            accessibility=data.get("accessibility", "WARN"),
        )


@dataclass
class SimilarityThresholds:
    """Similarity thresholds for duplicate detection."""

    duplicate: float = 0.95
    near_duplicate: float = 0.80
    component_reuse: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "duplicate": self.duplicate,
            "nearDuplicate": self.near_duplicate,
            "componentReuse": self.component_reuse,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SimilarityThresholds":
        """Create from dictionary."""
        return cls(
            duplicate=data.get("duplicate", 0.95),
            near_duplicate=data.get("nearDuplicate", 0.80),
            component_reuse=data.get("componentReuse", 0.75),
        )


@dataclass
class GatingConfig:
    """Gating and severity configuration."""

    severity_thresholds: SeverityThresholds = field(
        default_factory=SeverityThresholds
    )
    similarity_thresholds: SimilarityThresholds = field(
        default_factory=SimilarityThresholds
    )
    baseline_mode: bool = True
    fail_only_on_new: bool = True
    min_confidence: float = 0.7
    require_multi_evidence: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "severityThresholds": self.severity_thresholds.to_dict(),
            "similarityThresholds": self.similarity_thresholds.to_dict(),
            "baselineMode": self.baseline_mode,
            "failOnlyOnNew": self.fail_only_on_new,
            "minConfidence": self.min_confidence,
            "requireMultiEvidence": self.require_multi_evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatingConfig":
        """Create from dictionary."""
        return cls(
            severity_thresholds=SeverityThresholds.from_dict(
                data.get("severityThresholds", {})
            ),
            similarity_thresholds=SimilarityThresholds.from_dict(
                data.get("similarityThresholds", {})
            ),
            baseline_mode=data.get("baselineMode", True),
            fail_only_on_new=data.get("failOnlyOnNew", True),
            min_confidence=data.get("minConfidence", 0.7),
            require_multi_evidence=data.get("requireMultiEvidence", True),
        )


@dataclass
class IgnoreRule:
    """A rule to ignore with rationale."""

    rule: str
    reason: str
    paths: list[str] = field(default_factory=list)
    expiry: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "rule": self.rule,
            "reason": self.reason,
        }
        if self.paths:
            result["paths"] = self.paths
        if self.expiry:
            result["expiry"] = self.expiry
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IgnoreRule":
        """Create from dictionary."""
        return cls(
            rule=data["rule"],
            reason=data["reason"],
            paths=data.get("paths", []),
            expiry=data.get("expiry"),
        )


@dataclass
class OutputConfig:
    """Output format configuration."""

    format: str = "json"
    include_screenshots: bool = True
    screenshot_dir: str = ".ui-quality/screenshots"
    report_dir: str = ".ui-quality/reports"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "format": self.format,
            "includeScreenshots": self.include_screenshots,
            "screenshotDir": self.screenshot_dir,
            "reportDir": self.report_dir,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutputConfig":
        """Create from dictionary."""
        return cls(
            format=data.get("format", "json"),
            include_screenshots=data.get("includeScreenshots", True),
            screenshot_dir=data.get("screenshotDir", ".ui-quality/screenshots"),
            report_dir=data.get("reportDir", ".ui-quality/reports"),
        )


@dataclass
class AllowedScales:
    """Allowed value scales for consistency checking."""

    spacing: list[float] = field(
        default_factory=lambda: [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64, 80, 96, 128]
    )
    radius: list[float] = field(
        default_factory=lambda: [0, 2, 4, 6, 8, 12, 16, 9999]
    )
    typography: list[TypographyToken] = field(
        default_factory=lambda: [
            TypographyToken("xs", 12, 16),
            TypographyToken("sm", 14, 20),
            TypographyToken("base", 16, 24),
            TypographyToken("lg", 18, 28),
            TypographyToken("xl", 20, 28),
            TypographyToken("2xl", 24, 32),
            TypographyToken("3xl", 30, 36),
            TypographyToken("4xl", 36, 40),
        ]
    )
    shadows: list[str] = field(
        default_factory=lambda: ["none", "sm", "md", "lg", "xl", "2xl"]
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "spacing": self.spacing,
            "radius": self.radius,
            "typography": [t.to_dict() for t in self.typography],
            "shadows": self.shadows,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AllowedScales":
        """Create from dictionary."""
        typography = []
        for t in data.get("typography", []):
            if isinstance(t, dict):
                typography.append(
                    TypographyToken(
                        name=t["name"],
                        size=t["size"],
                        line_height=t.get("lineHeight"),
                    )
                )
        if not typography:
            typography = cls.__dataclass_fields__["typography"].default_factory()

        return cls(
            spacing=data.get("spacing", cls.__dataclass_fields__["spacing"].default_factory()),
            radius=data.get("radius", cls.__dataclass_fields__["radius"].default_factory()),
            typography=typography,
            shadows=data.get("shadows", cls.__dataclass_fields__["shadows"].default_factory()),
        )


@dataclass
class DesignSystemConfig:
    """Design system token sources and scales."""

    token_sources: list[str] = field(default_factory=list)
    allowed_scales: AllowedScales = field(default_factory=AllowedScales)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "tokenSources": self.token_sources,
            "allowedScales": self.allowed_scales.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignSystemConfig":
        """Create from dictionary."""
        return cls(
            token_sources=data.get("tokenSources", []),
            allowed_scales=AllowedScales.from_dict(data.get("allowedScales", {})),
        )


# =============================================================================
# Risk Mitigation Configuration (Phase 9)
# =============================================================================


@dataclass
class DeterministicDataConfig:
    """Configuration for deterministic demo data mode.

    When enabled, produces reproducible results for testing
    by using fixed seeds and mock timestamps.
    """

    enabled: bool = False
    seed: int = 42  # Random seed for reproducibility
    mock_timestamps: bool = True  # Use fixed timestamps
    mock_user_data: bool = True  # Use placeholder user data

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "seed": self.seed,
            "mockTimestamps": self.mock_timestamps,
            "mockUserData": self.mock_user_data,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeterministicDataConfig":
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", False),
            seed=data.get("seed", 42),
            mock_timestamps=data.get("mockTimestamps", True),
            mock_user_data=data.get("mockUserData", True),
        )


@dataclass
class PIIRedactionConfig:
    """Configuration for PII redaction in screenshots.

    Protects sensitive information when capturing UI screenshots
    during runtime analysis.
    """

    enabled: bool = True
    redact_emails: bool = True
    redact_names: bool = True
    redact_phone_numbers: bool = True
    redact_addresses: bool = True
    custom_patterns: list[str] = field(default_factory=list)  # Regex patterns
    redaction_placeholder: str = "[REDACTED]"
    blur_images: bool = True  # Blur user avatars/profile images

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "enabled": self.enabled,
            "redactEmails": self.redact_emails,
            "redactNames": self.redact_names,
            "redactPhoneNumbers": self.redact_phone_numbers,
            "redactAddresses": self.redact_addresses,
            "customPatterns": self.custom_patterns,
            "redactionPlaceholder": self.redaction_placeholder,
            "blurImages": self.blur_images,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PIIRedactionConfig":
        """Create from dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            redact_emails=data.get("redactEmails", True),
            redact_names=data.get("redactNames", True),
            redact_phone_numbers=data.get("redactPhoneNumbers", True),
            redact_addresses=data.get("redactAddresses", True),
            custom_patterns=data.get("customPatterns", []),
            redaction_placeholder=data.get("redactionPlaceholder", "[REDACTED]"),
            blur_images=data.get("blurImages", True),
        )


@dataclass
class StorybookPreferenceConfig:
    """Configuration for Storybook preference over live routes.

    Controls whether runtime analysis prefers Storybook for
    more predictable, isolated component testing.
    """

    prefer_storybook: bool = True  # Use Storybook if available
    storybook_only: bool = False  # Never crawl live routes
    story_patterns: list[str] = field(
        default_factory=lambda: ["*"]
    )  # Story glob patterns
    skip_stories: list[str] = field(default_factory=list)  # Stories to skip

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "preferStorybook": self.prefer_storybook,
            "storybookOnly": self.storybook_only,
            "storyPatterns": self.story_patterns,
            "skipStories": self.skip_stories,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StorybookPreferenceConfig":
        """Create from dictionary."""
        return cls(
            prefer_storybook=data.get("preferStorybook", True),
            storybook_only=data.get("storybookOnly", False),
            story_patterns=data.get("storyPatterns", ["*"]),
            skip_stories=data.get("skipStories", []),
        )


@dataclass
class RiskMitigationConfig:
    """Risk mitigation settings for UI analysis.

    Combines deterministic data mode, PII protection, and
    Storybook preferences for safer, more reliable analysis.
    """

    deterministic_data: DeterministicDataConfig = field(
        default_factory=DeterministicDataConfig
    )
    pii_redaction: PIIRedactionConfig = field(default_factory=PIIRedactionConfig)
    storybook_preference: StorybookPreferenceConfig = field(
        default_factory=StorybookPreferenceConfig
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "deterministicData": self.deterministic_data.to_dict(),
            "piiRedaction": self.pii_redaction.to_dict(),
            "storybookPreference": self.storybook_preference.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RiskMitigationConfig":
        """Create from dictionary."""
        return cls(
            deterministic_data=DeterministicDataConfig.from_dict(
                data.get("deterministicData", {})
            ),
            pii_redaction=PIIRedactionConfig.from_dict(data.get("piiRedaction", {})),
            storybook_preference=StorybookPreferenceConfig.from_dict(
                data.get("storybookPreference", {})
            ),
        )


@dataclass
class UIQualityConfig:
    """Complete UI quality configuration.

    This is the main configuration class that combines all aspects
    of UI quality checking configuration.
    """

    design_system: DesignSystemConfig = field(default_factory=DesignSystemConfig)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    gating: GatingConfig = field(default_factory=GatingConfig)
    ignore_rules: list[IgnoreRule] = field(default_factory=list)
    output: OutputConfig = field(default_factory=OutputConfig)
    risk_mitigation: RiskMitigationConfig = field(default_factory=RiskMitigationConfig)

    # Computed properties
    _token_set: TokenSet | None = field(default=None, repr=False)
    _project_path: Path | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "designSystem": self.design_system.to_dict(),
            "crawl": self.crawl.to_dict(),
            "gating": self.gating.to_dict(),
            "ignoreRules": [r.to_dict() for r in self.ignore_rules],
            "output": self.output.to_dict(),
            "riskMitigation": self.risk_mitigation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIQualityConfig":
        """Create from dictionary."""
        return cls(
            design_system=DesignSystemConfig.from_dict(data.get("designSystem", {})),
            crawl=CrawlConfig.from_dict(data.get("crawl", {})),
            gating=GatingConfig.from_dict(data.get("gating", {})),
            ignore_rules=[
                IgnoreRule.from_dict(r) for r in data.get("ignoreRules", [])
            ],
            output=OutputConfig.from_dict(data.get("output", {})),
            risk_mitigation=RiskMitigationConfig.from_dict(
                data.get("riskMitigation", {})
            ),
        )

    def load_tokens(self, project_path: Path | None = None) -> TokenSet:
        """Load design tokens from configured sources.

        Args:
            project_path: Project root path for resolving relative paths.

        Returns:
            Merged TokenSet from all configured sources.
        """
        if self._token_set is not None and self._project_path == project_path:
            return self._token_set

        self._project_path = project_path
        registry = get_default_registry()
        result = TokenSet()

        for source in self.design_system.token_sources:
            source_path = Path(source)
            if not source_path.is_absolute() and project_path:
                source_path = project_path / source_path

            if source_path.exists():
                try:
                    tokens = registry.extract(source_path)
                    result = result.merge(tokens)
                    logger.debug(
                        f"Loaded {tokens.total_tokens} tokens from {source_path}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to load tokens from {source_path}: {e}")
            else:
                logger.warning(f"Token source not found: {source_path}")

        # Add allowed scales as tokens if not already present
        result = self._add_scale_tokens(result)

        self._token_set = result
        return result

    def _add_scale_tokens(self, token_set: TokenSet) -> TokenSet:
        """Add allowed scales as tokens if not already present."""
        from .tokens import RadiusToken, SpacingToken

        # Add spacing scale
        for value in self.design_system.allowed_scales.spacing:
            name = f"scale-{int(value)}"
            if name not in token_set.spacing:
                token_set.spacing[name] = SpacingToken(
                    name=name,
                    value=float(value),
                )

        # Add radius scale
        for value in self.design_system.allowed_scales.radius:
            name = f"radius-{int(value)}" if value != 9999 else "radius-full"
            if name not in token_set.radii:
                token_set.radii[name] = RadiusToken(
                    name=name,
                    value=float(value),
                )

        # Add typography scale
        for typo in self.design_system.allowed_scales.typography:
            if typo.name not in token_set.typography:
                token_set.typography[typo.name] = typo

        return token_set

    def is_rule_ignored(self, rule_id: str, file_path: str | None = None) -> bool:
        """Check if a rule is ignored for the given file path.

        Args:
            rule_id: The rule ID to check.
            file_path: Optional file path to check path-specific ignores.

        Returns:
            True if the rule should be ignored.
        """
        import fnmatch
        from datetime import date

        for ignore in self.ignore_rules:
            if ignore.rule != rule_id:
                continue

            # Check expiry
            if ignore.expiry:
                try:
                    expiry_date = date.fromisoformat(ignore.expiry)
                    if date.today() > expiry_date:
                        continue  # Ignore has expired
                except ValueError:
                    pass  # Invalid date, ignore it

            # Check path patterns
            if ignore.paths and file_path:
                matched = any(
                    fnmatch.fnmatch(file_path, pattern) for pattern in ignore.paths
                )
                if not matched:
                    continue

            return True

        return False


class UIConfigLoader:
    """Loader for UI quality configuration."""

    def __init__(self, project_path: Path | None = None):
        """Initialize the config loader.

        Args:
            project_path: Path to the project root. Defaults to current directory.
        """
        self.project_path = Path(project_path) if project_path else Path.cwd()

    def load(self, config_path: Path | None = None) -> UIQualityConfig:
        """Load UI quality configuration.

        Precedence (highest to lowest):
        1. Explicit config_path
        2. Environment variable UI_QUALITY_CONFIG
        3. ui-quality.config.json in project root
        4. Default configuration

        Args:
            config_path: Optional explicit path to config file.

        Returns:
            Loaded UIQualityConfig instance.
        """
        # Try explicit path
        if config_path and config_path.exists():
            return self._load_from_file(config_path)

        # Try environment variable
        env_path = os.environ.get("UI_QUALITY_CONFIG")
        if env_path:
            env_config_path = Path(env_path)
            if env_config_path.exists():
                return self._load_from_file(env_config_path)

        # Try project root
        project_config = self.project_path / CONFIG_FILENAME
        if project_config.exists():
            return self._load_from_file(project_config)

        # Return defaults
        logger.debug("No UI quality config found, using defaults")
        return UIQualityConfig()

    def _load_from_file(self, config_path: Path) -> UIQualityConfig:
        """Load configuration from a file.

        Args:
            config_path: Path to the config file.

        Returns:
            Loaded UIQualityConfig instance.

        Raises:
            json.JSONDecodeError: If the file is not valid JSON.
        """
        logger.debug(f"Loading UI quality config from {config_path}")
        content = config_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return UIQualityConfig.from_dict(data)

    def save(self, config: UIQualityConfig, config_path: Path | None = None) -> Path:
        """Save configuration to a file.

        Args:
            config: Configuration to save.
            config_path: Optional path. Defaults to project root.

        Returns:
            Path where config was saved.
        """
        if config_path is None:
            config_path = self.project_path / CONFIG_FILENAME

        content = json.dumps(config.to_dict(), indent=2)
        config_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved UI quality config to {config_path}")
        return config_path


def load_ui_config(project_path: Path | None = None) -> UIQualityConfig:
    """Convenience function to load UI quality configuration.

    Args:
        project_path: Optional project root path.

    Returns:
        Loaded UIQualityConfig instance.
    """
    loader = UIConfigLoader(project_path)
    return loader.load()
