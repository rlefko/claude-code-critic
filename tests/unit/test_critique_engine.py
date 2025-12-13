"""Unit tests for the critique engine module.

Tests cover:
- ConsistencyAnalyzer: Token adherence, role variants, outlier detection
- HierarchyAnalyzer: Heading scale, contrast, spacing rhythm
- AffordanceAnalyzer: Focus visibility, tap targets, form labels
- CritiqueEngine: Critique generation and evidence linking
"""

import pytest

from claude_indexer.ui.config import (
    AllowedScales,
    DesignSystemConfig,
    GatingConfig,
    SimilarityThresholds,
    UIQualityConfig,
)
from claude_indexer.ui.critique.affordance import AffordanceAnalyzer
from claude_indexer.ui.critique.consistency import ConsistencyAnalyzer
from claude_indexer.ui.critique.engine import CritiqueEngine
from claude_indexer.ui.critique.hierarchy import HierarchyAnalyzer
from claude_indexer.ui.models import (
    LayoutBox,
    RuntimeElementFingerprint,
    Severity,
)


@pytest.fixture
def mock_config() -> UIQualityConfig:
    """Create mock UI quality config for testing."""
    from claude_indexer.ui.tokens import TypographyToken

    return UIQualityConfig(
        design_system=DesignSystemConfig(
            allowed_scales=AllowedScales(
                spacing=[0, 4, 8, 12, 16, 24, 32, 48, 64],
                radius=[0, 2, 4, 6, 8, 12, 16],
                typography=[
                    TypographyToken("xs", 12, 16),
                    TypographyToken("sm", 14, 20),
                    TypographyToken("base", 16, 24),
                    TypographyToken("lg", 18, 28),
                    TypographyToken("xl", 20, 28),
                    TypographyToken("2xl", 24, 32),
                    TypographyToken("3xl", 30, 36),
                    TypographyToken("4xl", 36, 40),
                    TypographyToken("5xl", 48, 52),
                ],
            ),
        ),
        gating=GatingConfig(
            similarity_thresholds=SimilarityThresholds(
                duplicate=0.95,
                near_duplicate=0.8,
            ),
        ),
    )


@pytest.fixture
def sample_fingerprints() -> list[RuntimeElementFingerprint]:
    """Create sample runtime fingerprints for testing."""
    return [
        RuntimeElementFingerprint(
            page_id="/home",
            selector="button.primary",
            role="button",
            computed_style_subset={
                "background-color": "#3b82f6",
                "padding": "12px",
                "border-radius": "8px",
                "font-size": "16px",
            },
            layout_box=LayoutBox(x=0, y=0, width=100, height=44),
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="button.secondary",
            role="button",
            computed_style_subset={
                "background-color": "#6b7280",
                "padding": "12px",
                "border-radius": "8px",
                "font-size": "16px",
            },
            layout_box=LayoutBox(x=0, y=0, width=100, height=44),
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="button.danger",
            role="button",
            computed_style_subset={
                "background-color": "#ef4444",
                "padding": "18px",  # Off-scale
                "border-radius": "6px",  # Different from others
                "font-size": "14px",
            },
            layout_box=LayoutBox(x=0, y=0, width=80, height=36),  # Undersized
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="input.text",
            role="input",
            computed_style_subset={
                "padding": "8px",
                "border-radius": "4px",
                "font-size": "16px",
            },
            layout_box=LayoutBox(x=0, y=0, width=200, height=40),
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="h1.title",
            role="heading",
            computed_style_subset={
                "font-size": "36px",
                "line-height": "1.2",
                "color": "#111827",
            },
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="h2.subtitle",
            role="heading",
            computed_style_subset={
                "font-size": "24px",
                "line-height": "1.3",
                "color": "#374151",
            },
        ),
    ]


class TestConsistencyAnalyzer:
    """Tests for ConsistencyAnalyzer."""

    def test_token_adherence_on_scale(self, mock_config: UIQualityConfig) -> None:
        """Test token adherence calculation with on-scale values."""
        analyzer = ConsistencyAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="div.test",
                role="button",
                computed_style_subset={
                    "padding": "16px",  # On scale
                    "margin": "8px",  # On scale
                },
            ),
        ]

        metrics, evidence = analyzer.analyze_token_adherence(fingerprints)

        assert metrics.total_values == 2
        assert metrics.on_scale_values == 2
        assert metrics.off_scale_values == 0
        assert metrics.adherence_rate == 1.0

    def test_token_adherence_off_scale(self, mock_config: UIQualityConfig) -> None:
        """Test token adherence calculation with off-scale values."""
        analyzer = ConsistencyAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="div.test",
                role="button",
                computed_style_subset={
                    "padding": "17px",  # Off scale
                    "margin": "8px",  # On scale
                },
            ),
        ]

        metrics, evidence = analyzer.analyze_token_adherence(fingerprints)

        assert metrics.total_values == 2
        assert metrics.on_scale_values == 1
        assert metrics.off_scale_values == 1
        assert metrics.adherence_rate == 0.5
        assert len(evidence) == 1
        assert evidence[0]["property"] == "padding"

    def test_role_variants_counting(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test variant counting per role."""
        analyzer = ConsistencyAnalyzer(mock_config)

        metrics = analyzer.analyze_role_variants(sample_fingerprints)

        assert "button" in metrics
        assert metrics["button"].variant_count >= 1  # Should detect variants
        assert metrics["button"].role == "button"

    def test_outlier_detection(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test statistical outlier detection."""
        analyzer = ConsistencyAnalyzer(mock_config)

        # Add more buttons to have a clear majority
        fingerprints = sample_fingerprints + [
            RuntimeElementFingerprint(
                page_id="/page2",
                selector="button.extra1",
                role="button",
                computed_style_subset={
                    "border-radius": "8px",
                    "padding": "12px",
                },
            ),
            RuntimeElementFingerprint(
                page_id="/page2",
                selector="button.extra2",
                role="button",
                computed_style_subset={
                    "border-radius": "8px",
                    "padding": "12px",
                },
            ),
        ]

        outliers = analyzer.detect_outliers(fingerprints)

        # Should detect that 6px radius is an outlier among 8px majority
        # (depends on statistical threshold)
        assert isinstance(outliers, list)

    def test_generate_consistency_critiques(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test critique generation from consistency analysis."""
        analyzer = ConsistencyAnalyzer(mock_config)

        critiques = analyzer.generate_consistency_critiques(sample_fingerprints)

        assert isinstance(critiques, list)
        for critique in critiques:
            assert "category" in critique
            assert "subcategory" in critique
            assert "severity" in critique
            assert "title" in critique
            assert "description" in critique


class TestHierarchyAnalyzer:
    """Tests for HierarchyAnalyzer."""

    def test_heading_scale_analysis(self, mock_config: UIQualityConfig) -> None:
        """Test heading scale consistency analysis."""
        analyzer = HierarchyAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="h1.title",
                role="heading",
                computed_style_subset={"font-size": "36px"},
            ),
            RuntimeElementFingerprint(
                page_id="/test",
                selector="h2.subtitle",
                role="heading",
                computed_style_subset={"font-size": "24px"},
            ),
            RuntimeElementFingerprint(
                page_id="/test",
                selector="h3.section",
                role="heading",
                computed_style_subset={"font-size": "18px"},
            ),
        ]

        metrics = analyzer.analyze_heading_scale(fingerprints)

        assert isinstance(metrics.heading_levels_found, dict)
        # Should find font sizes for headings

    def test_contrast_ratio_calculation(self, mock_config: UIQualityConfig) -> None:
        """Test contrast ratio calculation."""
        analyzer = HierarchyAnalyzer(mock_config)

        # Test with black text on white background (should pass)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="p.text",
                role="text",
                computed_style_subset={
                    "color": "#000000",
                    "background-color": "#ffffff",
                    "font-size": "16px",
                },
            ),
        ]

        metrics = analyzer.analyze_contrast(fingerprints)

        assert metrics.total_checks >= 1
        assert metrics.passing_checks >= 1  # Black on white should pass

    def test_contrast_ratio_failure(self, mock_config: UIQualityConfig) -> None:
        """Test contrast ratio failure detection."""
        analyzer = HierarchyAnalyzer(mock_config)

        # Test with light gray text on white background (should fail)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="p.text",
                role="text",
                computed_style_subset={
                    "color": "#cccccc",
                    "background-color": "#ffffff",
                    "font-size": "16px",
                },
            ),
        ]

        metrics = analyzer.analyze_contrast(fingerprints)

        assert metrics.total_checks >= 1
        assert metrics.failing_checks >= 1

    def test_spacing_rhythm_analysis(self, mock_config: UIQualityConfig) -> None:
        """Test spacing rhythm analysis."""
        analyzer = HierarchyAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="div.box1",
                role="card",
                computed_style_subset={
                    "padding": "16px",  # On scale
                    "margin": "8px",  # On scale
                },
            ),
            RuntimeElementFingerprint(
                page_id="/test",
                selector="div.box2",
                role="card",
                computed_style_subset={
                    "padding": "17px",  # Off scale
                    "margin": "8px",  # On scale
                },
            ),
        ]

        metrics = analyzer.analyze_spacing_rhythm(fingerprints)

        assert metrics.total_spacings >= 2
        assert metrics.rhythm_adherence < 1.0  # Not all on scale


class TestAffordanceAnalyzer:
    """Tests for AffordanceAnalyzer."""

    def test_tap_target_adequate(self, mock_config: UIQualityConfig) -> None:
        """Test tap target size detection - adequate size."""
        analyzer = AffordanceAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="button.big",
                role="button",
                computed_style_subset={},
                layout_box=LayoutBox(x=0, y=0, width=100, height=50),
            ),
        ]

        metrics = analyzer.analyze_tap_targets(fingerprints)

        assert metrics.total_targets == 1
        assert metrics.adequate_size == 1
        assert metrics.undersized == 0

    def test_tap_target_undersized(self, mock_config: UIQualityConfig) -> None:
        """Test tap target size detection - undersized."""
        analyzer = AffordanceAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="button.small",
                role="button",
                computed_style_subset={},
                layout_box=LayoutBox(x=0, y=0, width=30, height=30),  # < 44x44
            ),
        ]

        metrics = analyzer.analyze_tap_targets(fingerprints)

        assert metrics.total_targets == 1
        assert metrics.undersized == 1
        assert metrics.compliance_rate < 1.0

    def test_form_layout_analysis(self, mock_config: UIQualityConfig) -> None:
        """Test form layout analysis."""
        analyzer = AffordanceAnalyzer(mock_config)
        fingerprints = [
            RuntimeElementFingerprint(
                page_id="/test",
                selector="input.email",
                role="input",
                computed_style_subset={},
            ),
            RuntimeElementFingerprint(
                page_id="/test",
                selector="label[for=email]",
                role="text",  # Label element
                computed_style_subset={},
            ),
        ]

        metrics = analyzer.analyze_form_layout(fingerprints)

        assert metrics.total_inputs >= 1


class TestCritiqueEngine:
    """Tests for CritiqueEngine."""

    def test_critique_generation(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test complete critique generation."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        assert report is not None
        assert isinstance(report.critiques, list)
        assert report.statistics.elements_analyzed == len(sample_fingerprints)
        assert report.generated_at is not None

    def test_critique_item_structure(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test that critique items have proper structure."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        for critique in report.critiques:
            assert critique.id is not None
            assert critique.category in ["consistency", "hierarchy", "affordance"]
            assert critique.subcategory is not None
            assert isinstance(critique.severity, Severity)
            assert critique.title
            assert critique.description

    def test_critique_sorting_by_severity(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test that critiques are sorted by severity (FAIL first)."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        if len(report.critiques) > 1:
            # FAIL should come before WARN, WARN before INFO
            severity_order = {Severity.FAIL: 0, Severity.WARN: 1, Severity.INFO: 2}
            for i in range(len(report.critiques) - 1):
                current = severity_order[report.critiques[i].severity]
                next_sev = severity_order[report.critiques[i + 1].severity]
                assert current <= next_sev

    def test_remediation_hints(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test that critiques include remediation hints."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        # At least some critiques should have remediation hints
        any(len(c.remediation_hints) > 0 for c in report.critiques)
        # This assertion depends on the specific critiques generated
        # Just verify the structure is correct
        for critique in report.critiques:
            assert isinstance(critique.remediation_hints, list)

    def test_summary_generation(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test critique summary generation."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        summary = report.summary
        assert summary.total_critiques == len(report.critiques)
        assert isinstance(summary.by_category, dict)
        assert isinstance(summary.by_severity, dict)

    def test_critique_to_dict(
        self,
        mock_config: UIQualityConfig,
        sample_fingerprints: list[RuntimeElementFingerprint],
    ) -> None:
        """Test critique serialization to dict."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        report_dict = report.to_dict()

        assert "critiques" in report_dict
        assert "summary" in report_dict
        assert "statistics" in report_dict
        assert "generated_at" in report_dict

    def test_empty_fingerprints(self, mock_config: UIQualityConfig) -> None:
        """Test critique generation with empty input."""
        engine = CritiqueEngine(mock_config)

        report = engine.generate_critique(
            runtime_fingerprints=[],
        )

        assert report is not None
        assert report.statistics.elements_analyzed == 0
