"""CI audit runner for UI consistency checking.

This module provides the main orchestration for CI-tier UI audits,
including cross-file analysis, baseline separation, and reporting.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..collectors import GitDiffCollector, SourceCollector
    from ..config import UIQualityConfig
    from ..models import (
        Finding,
        StaticComponentFingerprint,
        StyleFingerprint,
    )
    from ..rules.engine import RuleEngine

from ..models import Severity
from .baseline import BaselineManager, CleanupMap
from .cache import CacheManager
from .cross_file_analyzer import CrossFileAnalyzer, CrossFileClusterResult


@dataclass
class CIAuditConfig:
    """Configuration for CI audit runs."""

    base_branch: str = "main"
    enable_caching: bool = True
    enable_clustering: bool = True
    parallel_workers: int = 4
    max_analysis_time_seconds: int = 600  # 10 minutes
    generate_cleanup_map: bool = True
    update_baseline: bool = False  # Only on merge to main
    fail_on_new_issues: bool = True
    include_baseline_in_output: bool = True
    record_metrics: bool = True  # Auto-record metrics after audit


@dataclass
class CIAuditResult:
    """Complete result of CI audit."""

    new_findings: list["Finding"] = field(default_factory=list)
    baseline_findings: list["Finding"] = field(default_factory=list)
    cross_file_clusters: CrossFileClusterResult | None = None
    cleanup_map: CleanupMap | None = None
    analysis_time_ms: float = 0.0
    files_analyzed: int = 0
    cache_hit_rate: float = 0.0
    tier: int = 1

    @property
    def should_fail(self) -> bool:
        """Whether CI should fail based on new findings."""
        return any(f.severity == Severity.FAIL for f in self.new_findings)

    @property
    def exit_code(self) -> int:
        """Exit code for CI: 0=pass, 1=fail."""
        return 1 if self.should_fail else 0

    @property
    def total_findings(self) -> int:
        """Total number of findings (new + baseline)."""
        return len(self.new_findings) + len(self.baseline_findings)

    @property
    def new_findings_count(self) -> int:
        """Number of new findings."""
        return len(self.new_findings)

    @property
    def baseline_findings_count(self) -> int:
        """Number of baseline findings."""
        return len(self.baseline_findings)

    def get_findings_by_severity(
        self, severity: Severity, include_baseline: bool = False
    ) -> list["Finding"]:
        """Get findings filtered by severity.

        Args:
            severity: Severity level to filter by.
            include_baseline: Whether to include baseline findings.

        Returns:
            List of findings matching severity.
        """
        findings = self.new_findings.copy()
        if include_baseline:
            findings.extend(self.baseline_findings)
        return [f for f in findings if f.severity == severity]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "new_findings": [f.to_dict() for f in self.new_findings],
            "baseline_findings": [f.to_dict() for f in self.baseline_findings],
            "cross_file_clusters": (
                self.cross_file_clusters.to_dict() if self.cross_file_clusters else None
            ),
            "cleanup_map": (self.cleanup_map.to_dict() if self.cleanup_map else None),
            "analysis_time_ms": self.analysis_time_ms,
            "files_analyzed": self.files_analyzed,
            "cache_hit_rate": self.cache_hit_rate,
            "tier": self.tier,
            "should_fail": self.should_fail,
            "exit_code": self.exit_code,
            "summary": {
                "total": self.total_findings,
                "new": self.new_findings_count,
                "baseline": self.baseline_findings_count,
            },
        }


class CIAuditRunner:
    """Orchestrates full CI audit process.

    Coordinates caching, fingerprint extraction, cross-file analysis,
    rule evaluation, and baseline separation.
    """

    # UI file extensions to analyze
    UI_EXTENSIONS = {
        ".css",
        ".scss",
        ".less",
        ".tsx",
        ".jsx",
        ".vue",
        ".svelte",
    }

    def __init__(
        self,
        project_path: Path,
        config: "UIQualityConfig | None" = None,
        audit_config: CIAuditConfig | None = None,
    ):
        """Initialize the CI audit runner.

        Args:
            project_path: Root path of the project.
            config: Optional UI quality configuration.
            audit_config: Optional CI-specific configuration.
        """
        self.project_path = Path(project_path)
        self.audit_config = audit_config or CIAuditConfig()

        # Lazy-load config if not provided
        self._config = config
        self._cache_manager: CacheManager | None = None
        self._source_collector: SourceCollector | None = None
        self._cross_file_analyzer: CrossFileAnalyzer | None = None
        self._baseline_manager: BaselineManager | None = None
        self._rule_engine: RuleEngine | None = None
        self._diff_collector: GitDiffCollector | None = None

    @property
    def config(self) -> "UIQualityConfig":
        """Lazy-loaded UI quality configuration."""
        if self._config is None:
            from ..config import load_ui_config

            self._config = load_ui_config(self.project_path)
        return self._config

    @property
    def cache_manager(self) -> CacheManager:
        """Lazy-initialized cache manager."""
        if self._cache_manager is None:
            self._cache_manager = CacheManager(self.project_path, self.config)
        return self._cache_manager

    @property
    def source_collector(self) -> "SourceCollector":
        """Lazy-initialized source collector."""
        if self._source_collector is None:
            from ..collectors import SourceCollector

            self._source_collector = SourceCollector()
        return self._source_collector

    @property
    def cross_file_analyzer(self) -> CrossFileAnalyzer:
        """Lazy-initialized cross-file analyzer."""
        if self._cross_file_analyzer is None:
            self._cross_file_analyzer = CrossFileAnalyzer(self.config)
        return self._cross_file_analyzer

    @property
    def baseline_manager(self) -> BaselineManager:
        """Lazy-initialized baseline manager."""
        if self._baseline_manager is None:
            self._baseline_manager = BaselineManager(self.project_path, self.config)
        return self._baseline_manager

    @property
    def rule_engine(self) -> "RuleEngine":
        """Lazy-initialized rule engine."""
        if self._rule_engine is None:
            from ..rules.engine import create_rule_engine

            self._rule_engine = create_rule_engine(self.config, register_defaults=True)
        return self._rule_engine

    @property
    def diff_collector(self) -> "GitDiffCollector":
        """Lazy-initialized git diff collector."""
        if self._diff_collector is None:
            from ..collectors import GitDiffCollector

            self._diff_collector = GitDiffCollector(self.project_path)
        return self._diff_collector

    def run(self) -> CIAuditResult:
        """Run the complete CI audit.

        Returns:
            CIAuditResult with findings and analysis data.
        """
        start_time = time.time()

        # Step 1: Collect all UI files
        ui_files = self._collect_ui_files()

        # Step 2: Extract fingerprints (with caching)
        all_styles, all_components = self._extract_all_fingerprints(ui_files)

        # Step 3: Run cross-file clustering (if enabled)
        cross_file_result = None
        if self.audit_config.enable_clustering:
            cross_file_result = self._run_cross_file_analysis(
                all_styles, all_components
            )

        # Step 4: Build rule context and run rule engine
        all_findings = self._run_rule_engine(
            all_styles, all_components, cross_file_result
        )

        # Step 5: Separate new vs baseline findings
        new_findings, baseline_findings = self.baseline_manager.separate_findings(
            all_findings
        )

        # Step 6: Generate cleanup map (if enabled)
        cleanup_map = None
        if self.audit_config.generate_cleanup_map:
            cleanup_map = self.baseline_manager.generate_cleanup_map(
                cross_file_result=cross_file_result
            )

        # Step 7: Update baseline (if configured)
        if self.audit_config.update_baseline:
            self.baseline_manager.update_from_findings(all_findings)
            self.baseline_manager.save()

        # Finalize caching
        if self.audit_config.enable_caching:
            self.cache_manager.finalize()

        analysis_time_ms = (time.time() - start_time) * 1000

        result = CIAuditResult(
            new_findings=new_findings,
            baseline_findings=baseline_findings,
            cross_file_clusters=cross_file_result,
            cleanup_map=cleanup_map,
            analysis_time_ms=analysis_time_ms,
            files_analyzed=len(ui_files),
            cache_hit_rate=self.cache_manager.hit_rate,
            tier=1,
        )

        # Auto-record metrics if enabled
        if self.audit_config.record_metrics:
            try:
                from ..metrics import MetricsCollector

                collector = MetricsCollector(self.project_path, self.config)
                collector.record_audit_run(result, tier=1)
                collector.save()
            except Exception:
                # Don't fail audit if metrics recording fails
                pass

        return result

    def run_incremental(self, changed_files: list[Path] | None = None) -> CIAuditResult:
        """Run audit only on changed files with cross-file context.

        Args:
            changed_files: Optional list of changed file paths.
                          If None, uses git diff to detect changes.

        Returns:
            CIAuditResult with findings.
        """
        start_time = time.time()

        # Get changed files from git if not provided
        if changed_files is None:
            diff_result = self.diff_collector.collect()
            changed_files = [
                Path(fc.file_path)
                for fc in diff_result.changed_files
                if self._is_ui_file(Path(fc.file_path))
            ]

        # Filter to UI files only
        ui_changed_files = [f for f in changed_files if self._is_ui_file(f)]

        if not ui_changed_files:
            # No UI files changed
            return CIAuditResult(
                analysis_time_ms=(time.time() - start_time) * 1000,
                files_analyzed=0,
            )

        # Extract fingerprints for changed files only
        changed_styles, changed_components = self._extract_fingerprints_for_files(
            ui_changed_files
        )

        # Run rules on changed fingerprints
        all_findings = self._run_rule_engine(changed_styles, changed_components, None)

        # Separate findings
        new_findings, baseline_findings = self.baseline_manager.separate_findings(
            all_findings
        )

        analysis_time_ms = (time.time() - start_time) * 1000

        result = CIAuditResult(
            new_findings=new_findings,
            baseline_findings=baseline_findings,
            analysis_time_ms=analysis_time_ms,
            files_analyzed=len(ui_changed_files),
            cache_hit_rate=self.cache_manager.hit_rate,
        )

        # Auto-record metrics if enabled
        if self.audit_config.record_metrics:
            try:
                from ..metrics import MetricsCollector

                collector = MetricsCollector(self.project_path, self.config)
                collector.record_audit_run(result, tier=0)  # Incremental = Tier 0
                collector.save()
            except Exception:
                # Don't fail audit if metrics recording fails
                pass

        return result

    def _collect_ui_files(self) -> list[Path]:
        """Collect all UI files in the project.

        Returns:
            List of UI file paths.
        """
        ui_files = []
        for ext in self.UI_EXTENSIONS:
            ui_files.extend(self.project_path.rglob(f"*{ext}"))

        # Filter out node_modules, dist, etc.
        excluded_dirs = {"node_modules", "dist", "build", ".git", "__pycache__"}
        ui_files = [
            f
            for f in ui_files
            if not any(excluded in f.parts for excluded in excluded_dirs)
        ]

        return ui_files

    def _is_ui_file(self, file_path: Path) -> bool:
        """Check if a file is a UI file.

        Args:
            file_path: Path to check.

        Returns:
            True if UI file, False otherwise.
        """
        return file_path.suffix.lower() in self.UI_EXTENSIONS

    def _extract_all_fingerprints(
        self, ui_files: list[Path]
    ) -> tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]]:
        """Extract fingerprints from all UI files.

        Uses caching and parallel processing for performance.

        Args:
            ui_files: List of UI file paths.

        Returns:
            Tuple of (all_styles, all_components).
        """
        all_styles: list[StyleFingerprint] = []
        all_components: list[StaticComponentFingerprint] = []

        if self.audit_config.enable_caching:
            self.cache_manager.initialize()

        # Process files (with parallelization if configured)
        if self.audit_config.parallel_workers > 1:
            results = self._extract_parallel(ui_files)
        else:
            results = self._extract_sequential(ui_files)

        # Aggregate results
        for styles, components in results:
            all_styles.extend(styles)
            all_components.extend(components)

        return all_styles, all_components

    def _extract_sequential(
        self, ui_files: list[Path]
    ) -> list[tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]]]:
        """Extract fingerprints sequentially.

        Args:
            ui_files: List of UI file paths.

        Returns:
            List of (styles, components) tuples.
        """
        results = []
        for file_path in ui_files:
            styles, components = self._extract_from_file(file_path)
            results.append((styles, components))
        return results

    def _extract_parallel(
        self, ui_files: list[Path]
    ) -> list[tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]]]:
        """Extract fingerprints in parallel.

        Args:
            ui_files: List of UI file paths.

        Returns:
            List of (styles, components) tuples.
        """
        results = []
        with ThreadPoolExecutor(
            max_workers=self.audit_config.parallel_workers
        ) as executor:
            futures = {
                executor.submit(self._extract_from_file, fp): fp for fp in ui_files
            }

            for future in as_completed(futures):
                try:
                    styles, components = future.result()
                    results.append((styles, components))
                except Exception:
                    # Log error but continue
                    results.append(([], []))

        return results

    def _extract_from_file(
        self, file_path: Path
    ) -> tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]]:
        """Extract fingerprints from a single file.

        Uses cache if available.

        Args:
            file_path: Path to the file.

        Returns:
            Tuple of (styles, components).
        """
        # Try cache first
        if self.audit_config.enable_caching:
            cached = self.cache_manager.get_cached_fingerprints(file_path)
            if cached:
                return cached

        # Extract from source
        try:
            extraction_result = self.source_collector.extract(file_path)

            # Convert to fingerprints
            from ..normalizers import ComponentNormalizer, StyleNormalizer

            style_normalizer = StyleNormalizer()
            component_normalizer = ComponentNormalizer()

            styles = []
            for extracted_style in extraction_result.styles:
                normalized = style_normalizer.normalize(extracted_style.declarations)
                styles.append(normalized.to_fingerprint(extracted_style.source_ref))

            components = []
            for extracted_component in extraction_result.components:
                normalized = component_normalizer.normalize(
                    extracted_component.element_type,
                    extracted_component.attributes,
                    extracted_component.children,
                )
                components.append(
                    normalized.to_fingerprint(extracted_component.source_ref)
                )

            # Cache results
            if self.audit_config.enable_caching:
                self.cache_manager.cache_fingerprints(file_path, styles, components)

            return styles, components

        except Exception:
            return [], []

    def _extract_fingerprints_for_files(
        self, files: list[Path]
    ) -> tuple[list["StyleFingerprint"], list["StaticComponentFingerprint"]]:
        """Extract fingerprints for specific files.

        Args:
            files: List of file paths.

        Returns:
            Tuple of (styles, components).
        """
        all_styles: list[StyleFingerprint] = []
        all_components: list[StaticComponentFingerprint] = []

        for file_path in files:
            styles, components = self._extract_from_file(file_path)
            all_styles.extend(styles)
            all_components.extend(components)

        return all_styles, all_components

    def _run_cross_file_analysis(
        self,
        all_styles: list["StyleFingerprint"],
        all_components: list["StaticComponentFingerprint"],
    ) -> CrossFileClusterResult:
        """Run cross-file clustering analysis.

        Args:
            all_styles: All style fingerprints.
            all_components: All component fingerprints.

        Returns:
            CrossFileClusterResult with analysis data.
        """
        return self.cross_file_analyzer.run_full_analysis(all_styles, all_components)

    def _run_rule_engine(
        self,
        styles: list["StyleFingerprint"],
        components: list["StaticComponentFingerprint"],
        cross_file_result: CrossFileClusterResult | None,
    ) -> list["Finding"]:
        """Run rule engine and collect findings.

        Args:
            styles: Style fingerprints.
            components: Component fingerprints.
            cross_file_result: Optional cross-file analysis result.

        Returns:
            List of findings.
        """
        from ..rules.base import RuleContext

        # Build context
        context = RuleContext(
            config=self.config,
            style_fingerprints=styles,
            component_fingerprints=components,
        )

        # Add cross-file data if available
        if cross_file_result:
            context.cross_file_clusters = cross_file_result

        # Run all rules (full mode)
        result = self.rule_engine.run(context)
        return result.findings


def run_ci_audit(
    project_path: Path,
    base_branch: str = "main",
    enable_caching: bool = True,
    update_baseline: bool = False,
    config: "UIQualityConfig | None" = None,
) -> CIAuditResult:
    """Convenience function to run CI audit.

    Args:
        project_path: Root path of the project.
        base_branch: Base branch for comparison.
        enable_caching: Whether to enable fingerprint caching.
        update_baseline: Whether to update baseline with findings.
        config: Optional UI quality configuration.

    Returns:
        CIAuditResult with findings and analysis data.
    """
    audit_config = CIAuditConfig(
        base_branch=base_branch,
        enable_caching=enable_caching,
        update_baseline=update_baseline,
    )

    runner = CIAuditRunner(
        project_path=project_path,
        config=config,
        audit_config=audit_config,
    )

    return runner.run()


__all__ = [
    "CIAuditConfig",
    "CIAuditResult",
    "CIAuditRunner",
    "run_ci_audit",
]
