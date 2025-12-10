"""Unit tests for the HTML reporter module.

Tests cover:
- HTMLReporter: HTML generation, styling, and output
- Gallery rendering
- Style diff highlighting
- File:line link generation
"""

import json
import tempfile
from pathlib import Path

import pytest

from claude_indexer.ui.critique.engine import (
    CritiqueItem,
    CritiqueReport,
    CritiqueStatistics,
    CritiqueSummary,
)
from claude_indexer.ui.models import Evidence, EvidenceType, Severity, SymbolKind, SymbolRef
from claude_indexer.ui.plan.task import ImplementationPlan, Task, TaskGroup
from claude_indexer.ui.reporters.html import HTMLReportConfig, HTMLReporter


@pytest.fixture
def sample_critique_report() -> CritiqueReport:
    """Create sample critique report for testing."""
    critiques = [
        CritiqueItem(
            id="CONSISTENCY-TOKEN_ADHERENCE-0001",
            category="consistency",
            subcategory="token_adherence",
            severity=Severity.FAIL,
            title="Low Token Adherence Rate",
            description="Only 60% of style values use design tokens. 25 values are off-scale.",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.RUNTIME,
                    description="padding: 17px (off-scale)",
                    data={"property": "padding", "value": "17px"},
                    source_ref=SymbolRef(
                        file_path="src/components/Button.tsx",
                        start_line=45,
                        end_line=45,
                        kind=SymbolKind.COMPONENT,
                    ),
                ),
            ],
            screenshots=["/path/to/screenshot1.png", "/path/to/screenshot2.png"],
            metrics={"adherence_rate": 0.6, "off_scale_values": 25},
            remediation_hints=[
                "Replace hardcoded values with design tokens",
                "Use CSS custom properties for consistency",
            ],
        ),
        CritiqueItem(
            id="HIERARCHY-CONTRAST-0001",
            category="hierarchy",
            subcategory="contrast",
            severity=Severity.WARN,
            title="Insufficient Text Contrast",
            description="5 text elements have insufficient contrast ratio.",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.RUNTIME,
                    description="Contrast ratio 2.5:1 (required 4.5:1)",
                    data={"contrast_ratio": 2.5, "required": 4.5},
                ),
            ],
            metrics={"pass_rate": 0.8, "failing_checks": 5},
            remediation_hints=["Increase text color contrast to meet WCAG 4.5:1"],
        ),
        CritiqueItem(
            id="AFFORDANCE-TAP_TARGETS-0001",
            category="affordance",
            subcategory="tap_targets",
            severity=Severity.INFO,
            title="Undersized Touch Targets",
            description="3 interactive elements are smaller than 44x44px.",
            evidence=[],
            metrics={"undersized": 3, "compliance_rate": 0.9},
        ),
    ]

    return CritiqueReport(
        critiques=critiques,
        summary=CritiqueSummary(
            total_critiques=3,
            by_category={"consistency": 1, "hierarchy": 1, "affordance": 1},
            by_severity={"fail": 1, "warn": 1, "info": 1},
            token_adherence_rate=0.6,
            role_variant_counts={"button": 6, "input": 3},
            accessibility_issues=2,
        ),
        statistics=CritiqueStatistics(
            elements_analyzed=150,
            pages_crawled=10,
            visual_clusters_found=5,
            analysis_time_ms=2500.0,
        ),
    )


@pytest.fixture
def sample_plan() -> ImplementationPlan:
    """Create sample implementation plan for testing."""
    return ImplementationPlan(
        groups=[
            TaskGroup(
                scope="tokens",
                description="Design token updates and standardization",
                tasks=[
                    Task(
                        id="TASK-TOK-0001",
                        title="Standardize design token usage",
                        description="Replace 25 hardcoded values with design tokens",
                        scope="tokens",
                        priority=1,
                        estimated_effort="low",
                        impact=0.9,
                        acceptance_criteria=[
                            "All color values use CSS custom properties",
                            "Token adherence rate reaches 95% or higher",
                        ],
                        evidence_links=["src/components/Button.tsx:45"],
                    ),
                ],
            ),
            TaskGroup(
                scope="components",
                description="Component consolidation and consistency",
                tasks=[
                    Task(
                        id="TASK-COM-0001",
                        title="Consolidate button variants",
                        description="Reduce button variants from 6 to 3",
                        scope="components",
                        priority=2,
                        estimated_effort="medium",
                        impact=0.7,
                        acceptance_criteria=[
                            "All buttons use shared Button component",
                            "Maximum 3 intentional variants documented",
                        ],
                    ),
                ],
            ),
        ],
        quick_wins=[
            Task(
                id="TASK-TOK-0001",
                title="Standardize design token usage",
                description="",
                scope="tokens",
                priority=1,
                estimated_effort="low",
                impact=0.9,
            ),
        ],
        summary="Implementation plan with 2 tasks across 2 scope areas.",
    )


class TestHTMLReporter:
    """Tests for HTMLReporter."""

    def test_generate_html_file(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test HTML file generation."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            result_path = reporter.generate(
                sample_critique_report, sample_plan, output_path
            )

            assert result_path.exists()
            assert result_path == output_path

            content = result_path.read_text()
            assert "<!DOCTYPE html>" in content
            assert "<html" in content
            assert "</html>" in content

    def test_html_contains_title(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains configured title."""
        config = HTMLReportConfig(title="Custom Report Title")
        reporter = HTMLReporter(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            assert "Custom Report Title" in content

    def test_html_contains_summary_stats(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains summary statistics."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for summary stats
            assert "Total Issues" in content or "3" in content  # Total critiques
            assert "150" in content  # Elements analyzed

    def test_html_contains_critiques(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains critique items."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for critique content
            assert "Low Token Adherence Rate" in content
            assert "Insufficient Text Contrast" in content

    def test_html_contains_severity_badges(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains severity badges."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for severity badge classes
            assert "badge-fail" in content or "FAIL" in content
            assert "badge-warn" in content or "WARN" in content

    def test_html_contains_plan_tasks(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains implementation plan tasks."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for task content
            assert "Standardize design token usage" in content
            assert "Consolidate button variants" in content

    def test_html_contains_quick_wins(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains quick wins section."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for quick wins
            assert "Quick Win" in content or "quick-win" in content

    def test_html_contains_remediation_hints(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains remediation hints."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for hints
            assert "Recommended Actions" in content or "design tokens" in content

    def test_html_contains_file_links(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML contains file:line links."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for file link (vscode URL scheme)
            assert "vscode://" in content or "Button.tsx:45" in content

    def test_html_responsive_css(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML includes responsive CSS."""
        reporter = HTMLReporter(HTMLReportConfig(responsive=True))

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for responsive media query
            assert "@media" in content

    def test_html_escapes_content(
        self,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that HTML escapes potentially dangerous content."""
        # Create critique with HTML in description
        critiques = [
            CritiqueItem(
                id="TEST-0001",
                category="consistency",
                subcategory="test",
                severity=Severity.INFO,
                title="<script>alert('xss')</script>",
                description="Test with <b>HTML</b> content",
            ),
        ]
        report = CritiqueReport(
            critiques=critiques,
            summary=CritiqueSummary(total_critiques=1),
        )

        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(report, sample_plan, output_path)

            content = output_path.read_text()
            # Script tag should be escaped
            assert "<script>" not in content
            assert "&lt;script&gt;" in content

    def test_generate_json(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test JSON output generation."""
        reporter = HTMLReporter()

        json_str = reporter.generate_json(sample_critique_report, sample_plan)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "critique_report" in parsed
        assert "plan" in parsed

    def test_dark_theme_config(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test dark theme configuration."""
        config = HTMLReportConfig(theme="dark")
        reporter = HTMLReporter(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Should have dark theme colors
            assert "#1a1a2e" in content or "dark" in content.lower()

    def test_skip_screenshots_config(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test skip screenshots configuration."""
        config = HTMLReportConfig(include_screenshots=False)
        reporter = HTMLReporter(config)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Should still generate valid HTML
            assert "<!DOCTYPE html>" in content

    def test_category_sections(
        self,
        sample_critique_report: CritiqueReport,
        sample_plan: ImplementationPlan,
    ) -> None:
        """Test that critiques are grouped by category."""
        reporter = HTMLReporter()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.html"
            reporter.generate(sample_critique_report, sample_plan, output_path)

            content = output_path.read_text()
            # Check for category headings
            assert "Consistency" in content
            assert "Hierarchy" in content
            assert "Affordance" in content


class TestHTMLReporterHelpers:
    """Tests for HTMLReporter helper methods."""

    def test_render_file_link(self) -> None:
        """Test file link rendering."""
        reporter = HTMLReporter()

        link = reporter._render_file_link("src/Button.tsx", 45)

        assert "src/Button.tsx:45" in link
        assert "vscode://" in link
        assert "file-link" in link

    def test_render_style_diff(self) -> None:
        """Test style diff rendering."""
        reporter = HTMLReporter()

        style1 = {"padding": "12px", "color": "#000"}
        style2 = {"padding": "16px", "color": "#000", "margin": "8px"}

        diff_html = reporter._render_style_diff(style1, style2, "Before", "After")

        # Should show changed padding
        assert "12px" in diff_html or "16px" in diff_html
        # Should show added margin
        assert "margin" in diff_html

    def test_escape_html(self) -> None:
        """Test HTML escaping."""
        reporter = HTMLReporter()

        result = reporter._escape("<script>alert('xss')</script>")

        assert "<script>" not in result
        assert "&lt;script&gt;" in result
