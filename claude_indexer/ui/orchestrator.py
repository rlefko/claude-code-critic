"""Redesign orchestrator for comprehensive UI audits.

Coordinates the complete /redesign flow including:
- Runtime collection (Playwright)
- Static analysis (CI audit)
- Visual clustering
- Critique generation
- Plan generation
- HTML report output
"""

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .collectors.runtime import CrawlResult, CrawlTarget, RuntimeCollector
    from .collectors.screenshots import VisualClusteringResult

from .ci.audit_runner import CIAuditResult, CIAuditRunner
from .config import UIQualityConfig, load_ui_config
from .critique.engine import CritiqueEngine, CritiqueReport
from .models import RuntimeElementFingerprint
from .plan.generator import PlanGenerator, PlanGeneratorConfig
from .plan.task import ImplementationPlan
from .reporters.html import HTMLReportConfig, HTMLReporter


@dataclass
class RedesignConfig:
    """Configuration for /redesign command execution."""

    focus: str | None = None  # Optional focus area (route, component, keyword)
    include_runtime: bool = True  # Run Playwright crawl
    include_static: bool = True  # Run static CI audit
    output_format: str = "html"  # "html" | "json" | "both"
    output_dir: Path | None = None  # Output directory for reports
    max_pages: int = 50  # Maximum pages/stories to crawl
    viewports: list[str] | None = None  # Viewport names to use
    skip_screenshots: bool = False  # Skip screenshot capture
    timeout_seconds: int = 300  # Maximum runtime in seconds


@dataclass
class RedesignResult:
    """Complete result of /redesign command execution."""

    critique_report: CritiqueReport
    implementation_plan: ImplementationPlan
    ci_result: CIAuditResult | None = None
    crawl_results: list["CrawlResult"] = field(default_factory=list)
    visual_clusters: "VisualClusteringResult | None" = None
    html_report_path: Path | None = None
    json_report_path: Path | None = None
    execution_time_ms: float = 0.0
    focus_area: str | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "critique_report": self.critique_report.to_dict(),
            "implementation_plan": self.implementation_plan.to_dict(),
            "ci_result": self.ci_result.to_dict() if self.ci_result else None,
            "crawl_results": [r.to_dict() for r in self.crawl_results],
            "visual_clusters": (
                self.visual_clusters.to_dict() if self.visual_clusters else None
            ),
            "html_report_path": str(self.html_report_path) if self.html_report_path else None,
            "json_report_path": str(self.json_report_path) if self.json_report_path else None,
            "execution_time_ms": self.execution_time_ms,
            "focus_area": self.focus_area,
            "errors": self.errors,
        }

    @property
    def has_errors(self) -> bool:
        """Check if execution had any errors."""
        return len(self.errors) > 0

    @property
    def summary(self) -> str:
        """Generate brief summary of results."""
        parts = [
            f"Analyzed {self.critique_report.statistics.elements_analyzed} elements",
            f"across {self.critique_report.statistics.pages_crawled} pages.",
            f"\nFound {self.critique_report.summary.total_critiques} issues",
            f"({self.critique_report.fail_count} critical,",
            f"{self.critique_report.warn_count} warnings).",
            f"\nGenerated {self.implementation_plan.total_tasks} tasks",
            f"with {len(self.implementation_plan.quick_wins)} quick wins.",
        ]
        return " ".join(parts)


class RedesignOrchestrator:
    """Orchestrates the complete /redesign audit flow.

    Coordinates runtime collection, static analysis, visual clustering,
    critique generation, plan generation, and report output.
    """

    def __init__(
        self,
        project_path: Path | str,
        config: UIQualityConfig | None = None,
        redesign_config: RedesignConfig | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            project_path: Root path of the project.
            config: Optional UI quality configuration.
            redesign_config: Optional redesign-specific configuration.
        """
        self.project_path = Path(project_path)
        self.redesign_config = redesign_config or RedesignConfig()

        # Lazy-load config
        self._config = config

        # Lazy-initialize components
        self._runtime_collector: "RuntimeCollector | None" = None
        self._ci_runner: CIAuditRunner | None = None
        self._critique_engine: CritiqueEngine | None = None
        self._plan_generator: PlanGenerator | None = None
        self._html_reporter: HTMLReporter | None = None

        # Set up output directory
        self._output_dir = self.redesign_config.output_dir or (
            self.project_path / ".ui-redesign-reports"
        )

    @property
    def config(self) -> UIQualityConfig:
        """Lazy-loaded UI quality configuration."""
        if self._config is None:
            self._config = load_ui_config(self.project_path)
        return self._config

    @property
    def critique_engine(self) -> CritiqueEngine:
        """Lazy-initialized critique engine."""
        if self._critique_engine is None:
            self._critique_engine = CritiqueEngine(self.config)
        return self._critique_engine

    @property
    def plan_generator(self) -> PlanGenerator:
        """Lazy-initialized plan generator."""
        if self._plan_generator is None:
            self._plan_generator = PlanGenerator(
                config=self.config,
                generator_config=PlanGeneratorConfig(
                    include_info_severity=False,
                    group_related_tasks=True,
                ),
            )
        return self._plan_generator

    @property
    def html_reporter(self) -> HTMLReporter:
        """Lazy-initialized HTML reporter."""
        if self._html_reporter is None:
            self._html_reporter = HTMLReporter(HTMLReportConfig(
                title=f"UI Redesign Report{' - ' + self.redesign_config.focus if self.redesign_config.focus else ''}",
                include_screenshots=not self.redesign_config.skip_screenshots,
            ))
        return self._html_reporter

    def _parse_focus(self, focus: str | None) -> dict[str, Any]:
        """Parse focus argument to filter configuration.

        Focus can be:
        - Route: /checkout, /settings/*
        - Story: Button--primary, Modal
        - Component: AuthModal, PaymentForm
        - Keyword: authentication, forms

        Args:
            focus: Focus string.

        Returns:
            Dict with filter configuration.
        """
        if not focus:
            return {}

        filters: dict[str, Any] = {"raw_focus": focus}

        # Route pattern (starts with /)
        if focus.startswith("/"):
            filters["route_pattern"] = focus
            filters["filter_type"] = "route"

        # Story pattern (contains --)
        elif "--" in focus:
            filters["story_pattern"] = focus
            filters["filter_type"] = "story"

        # Component name (PascalCase)
        elif focus[0].isupper() and not focus.isupper():
            filters["component_name"] = focus
            filters["filter_type"] = "component"

        # Keyword (anything else)
        else:
            filters["keyword"] = focus.lower()
            filters["filter_type"] = "keyword"

        return filters

    def _filter_crawl_targets(
        self,
        targets: list["CrawlTarget"],
        focus_filters: dict[str, Any],
    ) -> list["CrawlTarget"]:
        """Filter crawl targets by focus.

        Args:
            targets: All available targets.
            focus_filters: Parsed focus filters.

        Returns:
            Filtered target list.
        """
        if not focus_filters:
            return targets[: self.redesign_config.max_pages]

        filter_type = focus_filters.get("filter_type")
        filtered = []

        for target in targets:
            include = False

            if filter_type == "route":
                pattern = focus_filters.get("route_pattern", "")
                if pattern.endswith("*"):
                    include = target.page_id.startswith(pattern[:-1])
                else:
                    include = target.page_id == pattern

            elif filter_type == "story":
                pattern = focus_filters.get("story_pattern", "")
                include = pattern.lower() in (target.story_id or "").lower()

            elif filter_type == "component":
                component = focus_filters.get("component_name", "")
                include = component.lower() in target.page_id.lower()

            elif filter_type == "keyword":
                keyword = focus_filters.get("keyword", "")
                include = keyword in target.page_id.lower()

            if include:
                filtered.append(target)

        return filtered[: self.redesign_config.max_pages]

    async def _run_static_analysis(self) -> CIAuditResult | None:
        """Run static CI audit.

        Returns:
            CIAuditResult or None if disabled/failed.
        """
        if not self.redesign_config.include_static:
            return None

        try:
            if self._ci_runner is None:
                self._ci_runner = CIAuditRunner(
                    project_path=self.project_path,
                    config=self.config,
                )
            return self._ci_runner.run()
        except Exception as e:
            return None

    async def _run_runtime_collection(
        self,
        focus_filters: dict[str, Any],
    ) -> tuple[list["CrawlResult"], list[RuntimeElementFingerprint]]:
        """Run Playwright runtime collection.

        Args:
            focus_filters: Parsed focus filters.

        Returns:
            Tuple of (crawl_results, all_fingerprints).
        """
        if not self.redesign_config.include_runtime:
            return [], []

        try:
            from .collectors.runtime import RuntimeCollector

            collector = RuntimeCollector(
                config=self.config,
                project_path=self.project_path,
                screenshot_dir=self._output_dir / "screenshots",
            )

            async with collector:
                # Build target list
                targets = await collector.build_target_list()

                # Filter by focus
                targets = self._filter_crawl_targets(targets, focus_filters)

                if not targets:
                    return [], []

                # Crawl targets
                crawl_results = await collector.crawl(targets)

                # Extract all fingerprints
                all_fingerprints = []
                for result in crawl_results:
                    all_fingerprints.extend(result.fingerprints)

                return crawl_results, all_fingerprints

        except ImportError:
            # Playwright not available
            return [], []
        except Exception:
            return [], []

    def _run_visual_clustering(
        self,
        crawl_results: list["CrawlResult"],
    ) -> "VisualClusteringResult | None":
        """Run visual clustering on screenshots.

        Args:
            crawl_results: Crawl results with screenshots.

        Returns:
            VisualClusteringResult or None if disabled/failed.
        """
        if self.redesign_config.skip_screenshots:
            return None

        try:
            from .collectors.screenshots import VisualClusteringEngine

            # Collect screenshots from crawl results
            screenshots = []
            for result in crawl_results:
                if result.screenshots_dir and result.screenshots_dir.exists():
                    screenshots.extend(result.screenshots_dir.glob("*.png"))

            if not screenshots:
                return None

            engine = VisualClusteringEngine(
                identical_threshold=self.config.gating.similarity_thresholds.duplicate,
                similar_threshold=self.config.gating.similarity_thresholds.near_duplicate,
            )

            return engine.cluster_screenshots(screenshots)

        except ImportError:
            return None
        except Exception:
            return None

    def _generate_reports(
        self,
        critique_report: CritiqueReport,
        plan: ImplementationPlan,
    ) -> tuple[Path | None, Path | None]:
        """Generate output reports.

        Args:
            critique_report: Critique report.
            plan: Implementation plan.

        Returns:
            Tuple of (html_path, json_path).
        """
        self._output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        html_path = None
        json_path = None

        output_format = self.redesign_config.output_format

        if output_format in ("html", "both"):
            html_path = self._output_dir / f"redesign_report_{timestamp}.html"
            self.html_reporter.generate(critique_report, plan, html_path)

        if output_format in ("json", "both"):
            json_path = self._output_dir / f"redesign_report_{timestamp}.json"
            json_content = self.html_reporter.generate_json(critique_report, plan)
            json_path.write_text(json_content, encoding="utf-8")

        return html_path, json_path

    async def run(self) -> RedesignResult:
        """Execute complete /redesign analysis.

        Returns:
            RedesignResult with critique, plan, and reports.
        """
        start_time = time.time()
        errors: list[str] = []

        # Parse focus
        focus_filters = self._parse_focus(self.redesign_config.focus)

        # Step 1: Run static analysis (in parallel with runtime)
        static_task = asyncio.create_task(self._run_static_analysis())

        # Step 2: Run runtime collection
        crawl_results, runtime_fingerprints = await self._run_runtime_collection(
            focus_filters
        )

        # Wait for static analysis
        ci_result = await static_task

        # Step 3: Run visual clustering
        visual_clusters = self._run_visual_clustering(crawl_results)

        # Step 4: Generate critique
        critique_report = self.critique_engine.generate_critique(
            runtime_fingerprints=runtime_fingerprints,
            crawl_results=crawl_results,
            ci_result=ci_result,
            visual_clusters=visual_clusters,
        )

        # Step 5: Generate plan
        plan = self.plan_generator.generate(
            critique_report=critique_report,
            ci_result=ci_result,
            cross_file_result=ci_result.cross_file_clusters if ci_result else None,
            focus_area=self.redesign_config.focus,
        )

        # Step 6: Generate reports
        html_path, json_path = self._generate_reports(critique_report, plan)

        execution_time_ms = (time.time() - start_time) * 1000

        return RedesignResult(
            critique_report=critique_report,
            implementation_plan=plan,
            ci_result=ci_result,
            crawl_results=crawl_results,
            visual_clusters=visual_clusters,
            html_report_path=html_path,
            json_report_path=json_path,
            execution_time_ms=execution_time_ms,
            focus_area=self.redesign_config.focus,
            errors=errors,
        )

    def run_sync(self) -> RedesignResult:
        """Synchronous wrapper for run().

        Returns:
            RedesignResult with critique, plan, and reports.
        """
        return asyncio.run(self.run())


async def run_redesign(
    project_path: Path | str,
    focus: str | None = None,
    output_format: str = "html",
    include_runtime: bool = True,
    config: UIQualityConfig | None = None,
) -> RedesignResult:
    """Convenience function to run /redesign audit.

    Args:
        project_path: Project root path.
        focus: Optional focus area.
        output_format: Output format (html, json, both).
        include_runtime: Whether to include Playwright crawl.
        config: Optional UI quality config.

    Returns:
        RedesignResult with all analysis data.
    """
    redesign_config = RedesignConfig(
        focus=focus,
        output_format=output_format,
        include_runtime=include_runtime,
    )

    orchestrator = RedesignOrchestrator(
        project_path=project_path,
        config=config,
        redesign_config=redesign_config,
    )

    return await orchestrator.run()


__all__ = [
    "RedesignConfig",
    "RedesignOrchestrator",
    "RedesignResult",
    "run_redesign",
]
