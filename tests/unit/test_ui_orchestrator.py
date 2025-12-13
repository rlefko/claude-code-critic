"""Tests for UI redesign orchestrator module.

Tests RedesignOrchestrator, RedesignConfig, and RedesignResult with
comprehensive mocking of dependencies.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_indexer.ui.orchestrator import (
    RedesignConfig,
    RedesignOrchestrator,
    RedesignResult,
    run_redesign,
)

# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def sample_critique_report():
    """Create a mock critique report."""
    from claude_indexer.ui.critique.engine import (
        CritiqueItem,
        CritiqueReport,
        CritiqueStatistics,
        CritiqueSummary,
    )
    from claude_indexer.ui.models import Severity

    items = [
        CritiqueItem(
            id="C001",
            category="consistency",
            subcategory="token_adherence",
            severity=Severity.FAIL,
            title="Inconsistent Button Styling",
            description="Button uses non-token color",
            evidence=[],
            remediation_hints=["Use --color-primary instead"],
        ),
        CritiqueItem(
            id="C002",
            category="duplication",
            subcategory="style_duplication",
            severity=Severity.WARN,
            title="Duplicate Card Styles",
            description="Similar card styles found in 3 locations",
            evidence=[],
            remediation_hints=["Extract to shared Card component"],
        ),
    ]

    summary = CritiqueSummary(
        total_critiques=2,
        by_category={"consistency": 1, "duplication": 1},
        by_severity={"fail": 1, "warn": 1},
    )

    statistics = CritiqueStatistics(
        elements_analyzed=50,
        pages_crawled=5,
    )

    return CritiqueReport(
        critiques=items,
        summary=summary,
        statistics=statistics,
    )


@pytest.fixture
def sample_implementation_plan():
    """Create a mock implementation plan."""
    from claude_indexer.ui.plan.task import ImplementationPlan, Task, TaskGroup

    task1 = Task(
        id="T001",
        title="Fix button colors",
        description="Replace hardcoded colors with design tokens",
        scope="component",
        priority=1,
        estimated_effort="small",
        impact="high",
    )

    task2 = Task(
        id="T002",
        title="Extract Card component",
        description="Create shared Card component from duplicates",
        scope="component",
        priority=2,
        estimated_effort="medium",
        impact="medium",
    )

    group = TaskGroup(
        scope="component",
        description="Component Improvements",
        tasks=[task1, task2],
    )

    return ImplementationPlan(
        groups=[group],
        quick_wins=[task1],
    )


@pytest.fixture
def mock_ui_config():
    """Create a UIQualityConfig for testing."""
    from claude_indexer.ui.config import UIQualityConfig

    return UIQualityConfig()


@pytest.fixture
def mock_ci_result():
    """Create a mock CI audit result."""
    from claude_indexer.ui.ci.audit_runner import CIAuditResult

    return CIAuditResult(
        new_findings=[],
        baseline_findings=[],
        files_analyzed=10,
        analysis_time_ms=500.0,
        cross_file_clusters=None,
    )


@pytest.fixture
def mock_crawl_result():
    """Create a mock crawl result."""
    from claude_indexer.ui.collectors.runtime import CrawlResult, CrawlTarget
    from claude_indexer.ui.config import ViewportConfig

    target = CrawlTarget(
        url="http://localhost:6006/",
        page_id="/@desktop",
        viewport=ViewportConfig("desktop", 1440, 900),
    )

    return CrawlResult(
        target=target,
        fingerprints=[],
        errors=[],
        crawl_time_ms=100.0,
    )


# ==============================================================================
# RedesignConfig Tests
# ==============================================================================


class TestRedesignConfig:
    """Tests for RedesignConfig dataclass."""

    def test_default_values(self):
        """Test RedesignConfig default values."""
        config = RedesignConfig()

        assert config.focus is None
        assert config.include_runtime is True
        assert config.include_static is True
        assert config.output_format == "html"
        assert config.output_dir is None
        assert config.max_pages == 50
        assert config.viewports is None
        assert config.skip_screenshots is False
        assert config.timeout_seconds == 300

    def test_custom_values(self):
        """Test RedesignConfig with custom values."""
        config = RedesignConfig(
            focus="/checkout",
            include_runtime=False,
            include_static=True,
            output_format="json",
            output_dir=Path("/tmp/reports"),
            max_pages=100,
            viewports=["mobile", "desktop"],
            skip_screenshots=True,
            timeout_seconds=600,
        )

        assert config.focus == "/checkout"
        assert config.include_runtime is False
        assert config.output_format == "json"
        assert config.output_dir == Path("/tmp/reports")
        assert config.max_pages == 100
        assert config.viewports == ["mobile", "desktop"]
        assert config.skip_screenshots is True
        assert config.timeout_seconds == 600


# ==============================================================================
# RedesignResult Tests
# ==============================================================================


class TestRedesignResult:
    """Tests for RedesignResult dataclass."""

    def test_default_values(self, sample_critique_report, sample_implementation_plan):
        """Test RedesignResult default values."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
        )

        assert result.ci_result is None
        assert result.crawl_results == []
        assert result.visual_clusters is None
        assert result.html_report_path is None
        assert result.json_report_path is None
        assert result.execution_time_ms == 0.0
        assert result.focus_area is None
        assert result.errors == []

    def test_has_errors_false(self, sample_critique_report, sample_implementation_plan):
        """Test has_errors returns False when no errors."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
            errors=[],
        )

        assert result.has_errors is False

    def test_has_errors_true(self, sample_critique_report, sample_implementation_plan):
        """Test has_errors returns True when errors exist."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
            errors=["Runtime collection failed"],
        )

        assert result.has_errors is True

    def test_summary_property(self, sample_critique_report, sample_implementation_plan):
        """Test summary property generates summary string."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
        )

        summary = result.summary

        assert "50 elements" in summary
        assert "5 pages" in summary
        assert "2 issues" in summary
        assert "1 critical" in summary
        assert "1 warnings" in summary
        assert "2 tasks" in summary
        assert "1 quick wins" in summary

    def test_to_dict_serialization(
        self, sample_critique_report, sample_implementation_plan, tmp_path
    ):
        """Test RedesignResult to_dict serialization."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
            html_report_path=tmp_path / "report.html",
            json_report_path=tmp_path / "report.json",
            execution_time_ms=1500.5,
            focus_area="/checkout",
            errors=["Minor warning"],
        )

        data = result.to_dict()

        assert "critique_report" in data
        assert "implementation_plan" in data
        assert data["html_report_path"] == str(tmp_path / "report.html")
        assert data["json_report_path"] == str(tmp_path / "report.json")
        assert data["execution_time_ms"] == 1500.5
        assert data["focus_area"] == "/checkout"
        assert data["errors"] == ["Minor warning"]

    def test_to_dict_with_none_values(
        self, sample_critique_report, sample_implementation_plan
    ):
        """Test to_dict handles None values correctly."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
        )

        data = result.to_dict()

        assert data["ci_result"] is None
        assert data["visual_clusters"] is None
        assert data["html_report_path"] is None
        assert data["json_report_path"] is None
        assert data["focus_area"] is None


# ==============================================================================
# RedesignOrchestrator Initialization Tests
# ==============================================================================


class TestOrchestratorInit:
    """Tests for RedesignOrchestrator initialization."""

    def test_basic_initialization(self, tmp_path):
        """Test basic orchestrator initialization."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
        )

        assert orchestrator.project_path == tmp_path
        assert orchestrator.redesign_config is not None
        assert orchestrator._config is None  # Lazy-loaded

    def test_initialization_with_config(self, tmp_path, mock_ui_config):
        """Test initialization with provided config."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        assert orchestrator._config == mock_ui_config
        assert orchestrator.config == mock_ui_config

    def test_initialization_with_redesign_config(self, tmp_path):
        """Test initialization with custom redesign config."""
        redesign_config = RedesignConfig(
            focus="/checkout",
            max_pages=20,
        )

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            redesign_config=redesign_config,
        )

        assert orchestrator.redesign_config.focus == "/checkout"
        assert orchestrator.redesign_config.max_pages == 20

    def test_output_dir_default(self, tmp_path):
        """Test default output directory is set."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
        )

        expected_dir = tmp_path / ".ui-redesign-reports"
        assert orchestrator._output_dir == expected_dir

    def test_output_dir_custom(self, tmp_path):
        """Test custom output directory from config."""
        custom_dir = tmp_path / "custom_reports"
        redesign_config = RedesignConfig(output_dir=custom_dir)

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            redesign_config=redesign_config,
        )

        assert orchestrator._output_dir == custom_dir

    def test_lazy_config_loading(self, tmp_path, mock_ui_config):
        """Test config is lazy-loaded."""
        with patch("claude_indexer.ui.orchestrator.load_ui_config") as mock_load:
            mock_load.return_value = mock_ui_config

            orchestrator = RedesignOrchestrator(
                project_path=tmp_path,
            )

            # Config not loaded yet
            mock_load.assert_not_called()

            # Access config triggers load
            _ = orchestrator.config
            mock_load.assert_called_once_with(tmp_path)


# ==============================================================================
# Focus Parsing Tests
# ==============================================================================


class TestFocusParsing:
    """Tests for _parse_focus method."""

    def test_parse_focus_none(self, tmp_path):
        """Test parsing None focus."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus(None)
        assert result == {}

    def test_parse_focus_empty(self, tmp_path):
        """Test parsing empty focus."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("")
        assert result == {}

    def test_parse_focus_route(self, tmp_path):
        """Test parsing route focus (starts with /)."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("/checkout")

        assert result["filter_type"] == "route"
        assert result["route_pattern"] == "/checkout"
        assert result["raw_focus"] == "/checkout"

    def test_parse_focus_route_wildcard(self, tmp_path):
        """Test parsing route wildcard focus."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("/settings/*")

        assert result["filter_type"] == "route"
        assert result["route_pattern"] == "/settings/*"

    def test_parse_focus_story(self, tmp_path):
        """Test parsing story focus (contains --)."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("Button--primary")

        assert result["filter_type"] == "story"
        assert result["story_pattern"] == "Button--primary"

    def test_parse_focus_component(self, tmp_path):
        """Test parsing component focus (PascalCase)."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("AuthModal")

        assert result["filter_type"] == "component"
        assert result["component_name"] == "AuthModal"

    def test_parse_focus_keyword(self, tmp_path):
        """Test parsing keyword focus (lowercase)."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("authentication")

        assert result["filter_type"] == "keyword"
        assert result["keyword"] == "authentication"

    def test_parse_focus_uppercase_as_keyword(self, tmp_path):
        """Test all uppercase is treated as keyword."""
        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        result = orchestrator._parse_focus("API")

        assert result["filter_type"] == "keyword"
        assert result["keyword"] == "api"


# ==============================================================================
# Target Filtering Tests
# ==============================================================================


class TestTargetFiltering:
    """Tests for _filter_crawl_targets method."""

    def test_filter_no_focus(self, tmp_path):
        """Test filtering with no focus returns all targets."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        orchestrator.redesign_config.max_pages = 100

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="/a"),
            CrawlTarget(url="http://localhost/b", page_id="/b"),
            CrawlTarget(url="http://localhost/c", page_id="/c"),
        ]

        result = orchestrator._filter_crawl_targets(targets, {})
        assert len(result) == 3

    def test_filter_respects_max_pages(self, tmp_path):
        """Test filtering respects max_pages limit."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)
        orchestrator.redesign_config.max_pages = 2

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="/a"),
            CrawlTarget(url="http://localhost/b", page_id="/b"),
            CrawlTarget(url="http://localhost/c", page_id="/c"),
        ]

        result = orchestrator._filter_crawl_targets(targets, {})
        assert len(result) == 2

    def test_filter_by_route_exact(self, tmp_path):
        """Test filtering by exact route."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="/checkout"),
            CrawlTarget(url="http://localhost/b", page_id="/settings"),
            CrawlTarget(url="http://localhost/c", page_id="/checkout/confirm"),
        ]

        filters = {"filter_type": "route", "route_pattern": "/checkout"}
        result = orchestrator._filter_crawl_targets(targets, filters)

        assert len(result) == 1
        assert result[0].page_id == "/checkout"

    def test_filter_by_route_wildcard(self, tmp_path):
        """Test filtering by route wildcard."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="/checkout"),
            CrawlTarget(url="http://localhost/b", page_id="/checkout/confirm"),
            CrawlTarget(url="http://localhost/c", page_id="/settings"),
        ]

        filters = {"filter_type": "route", "route_pattern": "/checkout*"}
        result = orchestrator._filter_crawl_targets(targets, filters)

        assert len(result) == 2

    def test_filter_by_story(self, tmp_path):
        """Test filtering by story pattern."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)

        targets = [
            CrawlTarget(
                url="http://localhost/a",
                page_id="btn",
                story_id="Button--primary",
            ),
            CrawlTarget(
                url="http://localhost/b",
                page_id="card",
                story_id="Card--default",
            ),
            CrawlTarget(
                url="http://localhost/c",
                page_id="btn2",
                story_id="Button--secondary",
            ),
        ]

        filters = {"filter_type": "story", "story_pattern": "Button"}
        result = orchestrator._filter_crawl_targets(targets, filters)

        assert len(result) == 2
        assert all("button" in r.story_id.lower() for r in result)

    def test_filter_by_component(self, tmp_path):
        """Test filtering by component name."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="AuthModal@desktop"),
            CrawlTarget(url="http://localhost/b", page_id="Card@desktop"),
            CrawlTarget(url="http://localhost/c", page_id="AuthForm@desktop"),
        ]

        filters = {"filter_type": "component", "component_name": "Auth"}
        result = orchestrator._filter_crawl_targets(targets, filters)

        assert len(result) == 2
        assert all("auth" in r.page_id.lower() for r in result)

    def test_filter_by_keyword(self, tmp_path):
        """Test filtering by keyword."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(project_path=tmp_path)

        targets = [
            CrawlTarget(url="http://localhost/a", page_id="/login"),
            CrawlTarget(url="http://localhost/b", page_id="/dashboard"),
            CrawlTarget(url="http://localhost/c", page_id="/settings/login"),
        ]

        filters = {"filter_type": "keyword", "keyword": "login"}
        result = orchestrator._filter_crawl_targets(targets, filters)

        assert len(result) == 2
        assert all("login" in r.page_id.lower() for r in result)


# ==============================================================================
# Static Analysis Tests
# ==============================================================================


class TestStaticAnalysis:
    """Tests for _run_static_analysis method."""

    @pytest.mark.asyncio
    async def test_static_analysis_runs_when_enabled(
        self, tmp_path, mock_ui_config, mock_ci_result
    ):
        """Test static analysis runs when enabled."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        with patch("claude_indexer.ui.orchestrator.CIAuditRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = mock_ci_result
            mock_runner_cls.return_value = mock_runner

            result = await orchestrator._run_static_analysis()

            assert result is not None
            mock_runner.run.assert_called_once()

    @pytest.mark.asyncio
    async def test_static_analysis_skips_when_disabled(self, tmp_path, mock_ui_config):
        """Test static analysis skips when disabled."""
        redesign_config = RedesignConfig(include_static=False)

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=redesign_config,
        )

        result = await orchestrator._run_static_analysis()
        assert result is None

    @pytest.mark.asyncio
    async def test_static_analysis_handles_error(self, tmp_path, mock_ui_config):
        """Test static analysis handles exceptions."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        with patch("claude_indexer.ui.orchestrator.CIAuditRunner") as mock_runner_cls:
            mock_runner_cls.side_effect = Exception("Audit failed")

            result = await orchestrator._run_static_analysis()
            assert result is None


# ==============================================================================
# Runtime Collection Tests
# ==============================================================================


class TestRuntimeCollection:
    """Tests for _run_runtime_collection method."""

    @pytest.mark.asyncio
    async def test_runtime_collection_skips_when_disabled(
        self, tmp_path, mock_ui_config
    ):
        """Test runtime collection skips when disabled."""
        redesign_config = RedesignConfig(include_runtime=False)

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=redesign_config,
        )

        crawl_results, fingerprints = await orchestrator._run_runtime_collection({})

        assert crawl_results == []
        assert fingerprints == []

    @pytest.mark.asyncio
    async def test_runtime_collection_handles_import_error(
        self, tmp_path, mock_ui_config
    ):
        """Test runtime collection handles ImportError."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        with patch.dict(
            "sys.modules",
            {"claude_indexer.ui.collectors.runtime": None},
        ):
            # This should handle the import error gracefully
            crawl_results, fingerprints = await orchestrator._run_runtime_collection({})

            # May return empty or error depending on implementation
            assert isinstance(crawl_results, list)
            assert isinstance(fingerprints, list)


# ==============================================================================
# Visual Clustering Tests
# ==============================================================================


class TestVisualClustering:
    """Tests for _run_visual_clustering method."""

    def test_visual_clustering_skips_when_disabled(
        self, tmp_path, mock_ui_config, mock_crawl_result
    ):
        """Test visual clustering skips when screenshots disabled."""
        redesign_config = RedesignConfig(skip_screenshots=True)

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=redesign_config,
        )

        result = orchestrator._run_visual_clustering([mock_crawl_result])
        assert result is None

    def test_visual_clustering_handles_no_screenshots(
        self, tmp_path, mock_ui_config, mock_crawl_result
    ):
        """Test visual clustering handles empty screenshots."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        # Crawl result with no screenshots
        mock_crawl_result.screenshots_dir = None

        result = orchestrator._run_visual_clustering([mock_crawl_result])
        assert result is None


# ==============================================================================
# Report Generation Tests
# ==============================================================================


class TestReportGeneration:
    """Tests for _generate_reports method."""

    def test_generate_html_report(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test HTML report generation."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(output_format="html"),
        )

        # Pre-populate the lazy attribute with a mock
        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value="{}")
        orchestrator._html_reporter = mock_reporter

        html_path, json_path = orchestrator._generate_reports(
            sample_critique_report, sample_implementation_plan
        )

        assert html_path is not None
        assert "redesign_report_" in str(html_path)
        assert html_path.suffix == ".html"
        assert json_path is None
        mock_reporter.generate.assert_called_once()

    def test_generate_json_report(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test JSON report generation."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(output_format="json"),
        )

        # Pre-populate the lazy attribute with a mock
        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value='{"test": true}')
        orchestrator._html_reporter = mock_reporter

        html_path, json_path = orchestrator._generate_reports(
            sample_critique_report, sample_implementation_plan
        )

        assert html_path is None
        assert json_path is not None
        assert "redesign_report_" in str(json_path)
        assert json_path.suffix == ".json"
        mock_reporter.generate_json.assert_called_once()

    def test_generate_both_reports(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test both HTML and JSON report generation."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(output_format="both"),
        )

        # Pre-populate the lazy attribute with a mock
        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value='{"test": true}')
        orchestrator._html_reporter = mock_reporter

        html_path, json_path = orchestrator._generate_reports(
            sample_critique_report, sample_implementation_plan
        )

        assert html_path is not None
        assert json_path is not None
        mock_reporter.generate.assert_called_once()
        mock_reporter.generate_json.assert_called_once()

    def test_creates_output_directory(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test output directory is created."""
        output_dir = tmp_path / "reports" / "nested"
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(output_dir=output_dir),
        )

        # Pre-populate the lazy attribute with a mock
        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        orchestrator._html_reporter = mock_reporter

        orchestrator._generate_reports(
            sample_critique_report, sample_implementation_plan
        )

        assert output_dir.exists()


# ==============================================================================
# Full Run Tests
# ==============================================================================


class TestFullRun:
    """Tests for complete run() method."""

    @pytest.mark.asyncio
    async def test_run_coordinates_all_steps(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test run() coordinates all analysis steps."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(
                include_runtime=False,  # Skip runtime for test
                include_static=False,  # Skip static for test
            ),
        )

        # Pre-populate lazy attributes with mocks
        mock_critique = MagicMock()
        mock_critique.generate_critique.return_value = sample_critique_report
        orchestrator._critique_engine = mock_critique

        mock_plan_gen = MagicMock()
        mock_plan_gen.generate.return_value = sample_implementation_plan
        orchestrator._plan_generator = mock_plan_gen

        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value="{}")
        orchestrator._html_reporter = mock_reporter

        result = await orchestrator.run()

        assert isinstance(result, RedesignResult)
        assert result.critique_report == sample_critique_report
        assert result.implementation_plan == sample_implementation_plan
        assert result.execution_time_ms > 0

    @pytest.mark.asyncio
    async def test_run_with_focus(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test run() with focus area."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(
                focus="/checkout",
                include_runtime=False,
                include_static=False,
            ),
        )

        # Pre-populate lazy attributes with mocks
        mock_critique = MagicMock()
        mock_critique.generate_critique.return_value = sample_critique_report
        orchestrator._critique_engine = mock_critique

        mock_plan_gen = MagicMock()
        mock_plan_gen.generate.return_value = sample_implementation_plan
        orchestrator._plan_generator = mock_plan_gen

        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value="{}")
        orchestrator._html_reporter = mock_reporter

        result = await orchestrator.run()

        assert result.focus_area == "/checkout"
        mock_plan_gen.generate.assert_called_once()
        # Verify focus was passed to plan generator
        call_kwargs = mock_plan_gen.generate.call_args.kwargs
        assert call_kwargs.get("focus_area") == "/checkout"

    def test_run_sync_wrapper(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test run_sync() wrapper works correctly."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
            redesign_config=RedesignConfig(
                include_runtime=False,
                include_static=False,
            ),
        )

        # Pre-populate lazy attributes with mocks
        mock_critique = MagicMock()
        mock_critique.generate_critique.return_value = sample_critique_report
        orchestrator._critique_engine = mock_critique

        mock_plan_gen = MagicMock()
        mock_plan_gen.generate.return_value = sample_implementation_plan
        orchestrator._plan_generator = mock_plan_gen

        mock_reporter = MagicMock()
        mock_reporter.generate = MagicMock()
        mock_reporter.generate_json = MagicMock(return_value="{}")
        orchestrator._html_reporter = mock_reporter

        result = orchestrator.run_sync()

        assert isinstance(result, RedesignResult)


# ==============================================================================
# Convenience Function Tests
# ==============================================================================


class TestRunRedesignFunction:
    """Tests for run_redesign convenience function."""

    @pytest.mark.asyncio
    async def test_run_redesign_creates_orchestrator(
        self,
        tmp_path,
        mock_ui_config,
        sample_critique_report,
        sample_implementation_plan,
    ):
        """Test run_redesign creates and runs orchestrator."""
        with patch(
            "claude_indexer.ui.orchestrator.RedesignOrchestrator"
        ) as mock_orch_cls:
            mock_orchestrator = MagicMock()
            mock_orchestrator.run = AsyncMock(
                return_value=RedesignResult(
                    critique_report=sample_critique_report,
                    implementation_plan=sample_implementation_plan,
                )
            )
            mock_orch_cls.return_value = mock_orchestrator

            result = await run_redesign(
                project_path=tmp_path,
                focus="/checkout",
                output_format="json",
                include_runtime=False,
                config=mock_ui_config,
            )

            mock_orch_cls.assert_called_once()
            assert isinstance(result, RedesignResult)


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestOrchestratorIntegration:
    """Integration tests for RedesignOrchestrator."""

    def test_lazy_property_initialization(self, tmp_path, mock_ui_config):
        """Test lazy properties are initialized correctly."""
        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        # All lazy properties should work
        assert orchestrator.config is not None
        assert orchestrator.critique_engine is not None
        assert orchestrator.plan_generator is not None
        assert orchestrator.html_reporter is not None

        # Second access should return same instance
        assert orchestrator.critique_engine is orchestrator._critique_engine
        assert orchestrator.plan_generator is orchestrator._plan_generator

    def test_focus_parsing_to_filtering_integration(self, tmp_path, mock_ui_config):
        """Test focus parsing integrates with target filtering."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        orchestrator = RedesignOrchestrator(
            project_path=tmp_path,
            config=mock_ui_config,
        )

        # Parse focus
        filters = orchestrator._parse_focus("AuthModal")
        assert filters["filter_type"] == "component"

        # Create targets
        targets = [
            CrawlTarget(url="http://localhost/a", page_id="AuthModal@desktop"),
            CrawlTarget(url="http://localhost/b", page_id="Card@desktop"),
        ]

        # Filter targets
        filtered = orchestrator._filter_crawl_targets(targets, filters)

        assert len(filtered) == 1
        assert filtered[0].page_id == "AuthModal@desktop"

    def test_result_serialization_roundtrip(
        self, sample_critique_report, sample_implementation_plan, tmp_path
    ):
        """Test RedesignResult serialization produces valid JSON."""
        result = RedesignResult(
            critique_report=sample_critique_report,
            implementation_plan=sample_implementation_plan,
            html_report_path=tmp_path / "report.html",
            execution_time_ms=1500.0,
            focus_area="/checkout",
        )

        # Serialize to dict
        data = result.to_dict()

        # Should be JSON serializable
        json_str = json.dumps(data, indent=2)
        assert json_str is not None

        # Deserialize back
        parsed = json.loads(json_str)
        assert parsed["focus_area"] == "/checkout"
        assert parsed["execution_time_ms"] == 1500.0
