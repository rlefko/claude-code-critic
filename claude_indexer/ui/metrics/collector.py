"""Metrics collector for UI consistency checking.

This module provides the MetricsCollector class for recording and
persisting metrics from audit runs.
"""

import json
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .models import (
    MetricSnapshot,
    MetricsReport,
    PerformancePercentiles,
    PlanAdoptionRecord,
)

if TYPE_CHECKING:
    from ..ci.audit_runner import CIAuditResult
    from ..ci.cross_file_analyzer import CrossFileClusterResult
    from ..config import UIQualityConfig
    from ..models import Finding, UIAnalysisResult


class MetricsCollector:
    """Collects and persists metrics from audit runs.

    Records point-in-time snapshots of UI quality metrics and maintains
    historical data for trend analysis and success tracking.
    """

    METRICS_FILE = ".ui-quality/metrics.json"
    METRICS_VERSION = "1.0"
    MAX_SNAPSHOTS = 1000  # Rolling window to limit storage

    def __init__(self, project_path: Path, config: "UIQualityConfig | None" = None):
        """Initialize the metrics collector.

        Args:
            project_path: Root path of the project.
            config: Optional UI quality configuration.
        """
        self.project_path = Path(project_path)
        self.config = config
        self.metrics_path = self.project_path / self.METRICS_FILE
        self._report: MetricsReport | None = None

    def load(self) -> MetricsReport:
        """Load metrics from disk, creating if needed.

        Returns:
            Loaded or newly created MetricsReport.
        """
        if self._report is not None:
            return self._report

        if not self.metrics_path.exists():
            self._report = MetricsReport(project_path=str(self.project_path))
            return self._report

        try:
            with open(self.metrics_path, "r") as f:
                data = json.load(f)
                self._report = MetricsReport.from_dict(data)
                return self._report

        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted metrics file, start fresh
            self._report = MetricsReport(project_path=str(self.project_path))
            return self._report

    def save(self, report: MetricsReport | None = None) -> None:
        """Save metrics to disk.

        Args:
            report: Optional report to save. Uses loaded report if None.
        """
        report_to_save = report or self._report
        if report_to_save is None:
            return

        # Update last_updated timestamp
        report_to_save.last_updated = datetime.now().isoformat()

        # Ensure directory exists
        self.metrics_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file then rename (atomic)
        temp_path = self.metrics_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(report_to_save.to_dict(), f, indent=2)
        temp_path.rename(self.metrics_path)

    def record_audit_run(
        self,
        result: "CIAuditResult | UIAnalysisResult",
        tier: int | None = None,
    ) -> MetricSnapshot:
        """Record metrics from an audit run.

        Extracts metrics from the audit result and creates a snapshot
        for historical tracking.

        Args:
            result: The audit result to record metrics from.
            tier: Optional tier override. Defaults to result.tier if available.

        Returns:
            Created MetricSnapshot.
        """
        report = self.load()

        # Determine tier
        if tier is None:
            tier = getattr(result, "tier", 0)

        # Get git context
        commit_hash, branch_name = self.get_git_context()

        # Extract metrics based on result type
        from ..ci.audit_runner import CIAuditResult
        from ..models import UIAnalysisResult

        if isinstance(result, CIAuditResult):
            snapshot = self._create_snapshot_from_ci_result(
                result, tier, commit_hash, branch_name
            )
        elif isinstance(result, UIAnalysisResult):
            snapshot = self._create_snapshot_from_analysis_result(
                result, tier, commit_hash, branch_name
            )
        else:
            # Fallback for unknown types
            snapshot = MetricSnapshot(
                timestamp=datetime.now().isoformat(),
                tier=tier,
                commit_hash=commit_hash,
                branch_name=branch_name,
            )

        # Add snapshot to report
        report.snapshots.append(snapshot)

        # Enforce rolling window
        if len(report.snapshots) > self.MAX_SNAPSHOTS:
            report.snapshots = report.snapshots[-self.MAX_SNAPSHOTS :]

        # Update current values
        self._update_current_values(report, snapshot)

        # Update baseline if this is first snapshot
        if len(report.snapshots) == 1:
            self._set_baseline_values(report, snapshot)

        # Update performance percentiles
        self._update_percentiles(report, tier, snapshot.analysis_time_ms)

        self._report = report
        return snapshot

    def record_plan_generated(self, total_tasks: int) -> str:
        """Record a /redesign plan generation.

        Args:
            total_tasks: Number of tasks in the generated plan.

        Returns:
            Generated plan ID for tracking adoption.
        """
        report = self.load()

        plan_id = str(uuid.uuid4())[:8]  # Short ID
        record = PlanAdoptionRecord(
            plan_id=plan_id,
            generated_at=datetime.now().isoformat(),
            total_tasks=total_tasks,
        )

        report.plan_records.append(record)
        self._report = report
        return plan_id

    def record_plan_progress(
        self, plan_id: str, completed_tasks: int, mark_complete: bool = False
    ) -> bool:
        """Record progress on a /redesign plan.

        Args:
            plan_id: ID of the plan to update.
            completed_tasks: Number of tasks now completed.
            mark_complete: Whether to mark the plan as fully complete.

        Returns:
            True if plan was found and updated, False otherwise.
        """
        report = self.load()

        for record in report.plan_records:
            if record.plan_id == plan_id:
                record.completed_tasks = completed_tasks
                if mark_complete or completed_tasks >= record.total_tasks:
                    record.completed_at = datetime.now().isoformat()
                self._report = report
                return True

        return False

    def get_git_context(self) -> tuple[str | None, str | None]:
        """Get current git commit hash and branch name.

        Returns:
            Tuple of (commit_hash, branch_name), either may be None.
        """
        commit_hash = None
        branch_name = None

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=5,
            )
            if result.returncode == 0:
                commit_hash = result.stdout.strip()[:12]  # Short hash
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=5,
            )
            if result.returncode == 0:
                branch_name = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return commit_hash, branch_name

    def _create_snapshot_from_ci_result(
        self,
        result: "CIAuditResult",
        tier: int,
        commit_hash: str | None,
        branch_name: str | None,
    ) -> MetricSnapshot:
        """Create snapshot from CIAuditResult."""
        # Extract token drift metrics from findings
        all_findings = result.new_findings + result.baseline_findings
        token_metrics = self._extract_token_drift_metrics(all_findings)

        # Extract deduplication metrics
        dedup_metrics = self._extract_dedup_metrics(result.cross_file_clusters)

        # Calculate suppression rate
        suppression_rate = 0.0
        if result.baseline_findings:
            suppressed = sum(
                1 for f in result.baseline_findings
                if self._is_finding_suppressed(f)
            )
            suppression_rate = suppressed / len(result.baseline_findings)

        return MetricSnapshot(
            timestamp=datetime.now().isoformat(),
            tier=tier,
            unique_hardcoded_colors=token_metrics.get("colors", 0),
            unique_hardcoded_spacings=token_metrics.get("spacings", 0),
            unique_off_scale_radii=token_metrics.get("radii", 0),
            unique_off_scale_typography=token_metrics.get("typography", 0),
            duplicate_clusters_found=dedup_metrics.get("duplicate", 0),
            near_duplicate_clusters_found=dedup_metrics.get("near_duplicate", 0),
            total_findings=result.total_findings,
            new_findings=result.new_findings_count,
            baseline_findings=result.baseline_findings_count,
            suppressed_findings=int(suppression_rate * result.baseline_findings_count),
            suppression_rate=suppression_rate,
            analysis_time_ms=result.analysis_time_ms,
            files_analyzed=result.files_analyzed,
            cache_hit_rate=result.cache_hit_rate,
            commit_hash=commit_hash,
            branch_name=branch_name,
        )

    def _create_snapshot_from_analysis_result(
        self,
        result: "UIAnalysisResult",
        tier: int,
        commit_hash: str | None,
        branch_name: str | None,
    ) -> MetricSnapshot:
        """Create snapshot from UIAnalysisResult."""
        # Extract token drift metrics
        token_metrics = self._extract_token_drift_metrics(result.findings)

        return MetricSnapshot(
            timestamp=datetime.now().isoformat(),
            tier=tier,
            unique_hardcoded_colors=token_metrics.get("colors", 0),
            unique_hardcoded_spacings=token_metrics.get("spacings", 0),
            unique_off_scale_radii=token_metrics.get("radii", 0),
            unique_off_scale_typography=token_metrics.get("typography", 0),
            total_findings=len(result.findings),
            new_findings=sum(1 for f in result.findings if f.is_new),
            baseline_findings=len(result.baseline_findings),
            analysis_time_ms=result.analysis_time_ms,
            files_analyzed=len(result.files_analyzed),
            commit_hash=commit_hash,
            branch_name=branch_name,
        )

    def _extract_token_drift_metrics(
        self, findings: list["Finding"]
    ) -> dict[str, int]:
        """Extract unique token drift values from findings.

        Counts unique hardcoded values by analyzing finding evidence.

        Args:
            findings: List of findings to analyze.

        Returns:
            Dict with counts by type (colors, spacings, radii, typography).
        """
        colors: set[str] = set()
        spacings: set[str] = set()
        radii: set[str] = set()
        typography: set[str] = set()

        for finding in findings:
            rule_id = finding.rule_id.upper()

            # Extract unique values from evidence data
            for evidence in finding.evidence:
                value = evidence.data.get("value", "")
                if not value:
                    continue

                if "COLOR" in rule_id:
                    colors.add(str(value))
                elif "SPACING" in rule_id:
                    spacings.add(str(value))
                elif "RADIUS" in rule_id:
                    radii.add(str(value))
                elif "TYPOGRAPHY" in rule_id or "TYPE" in rule_id:
                    typography.add(str(value))

        return {
            "colors": len(colors),
            "spacings": len(spacings),
            "radii": len(radii),
            "typography": len(typography),
        }

    def _extract_dedup_metrics(
        self, clusters: "CrossFileClusterResult | None"
    ) -> dict[str, int]:
        """Extract deduplication metrics from cluster results.

        Args:
            clusters: Cross-file cluster analysis result.

        Returns:
            Dict with duplicate and near_duplicate counts.
        """
        if clusters is None:
            return {"duplicate": 0, "near_duplicate": 0}

        return {
            "duplicate": clusters.exact_duplicate_count,
            "near_duplicate": clusters.near_duplicate_count,
        }

    def _is_finding_suppressed(self, finding: "Finding") -> bool:
        """Check if a finding is suppressed via config.

        Args:
            finding: Finding to check.

        Returns:
            True if suppressed, False otherwise.
        """
        if self.config is None:
            return False

        file_path = None
        if finding.source_ref:
            file_path = finding.source_ref.file_path

        return self.config.is_rule_ignored(finding.rule_id, file_path)

    def _update_current_values(
        self, report: MetricsReport, snapshot: MetricSnapshot
    ) -> None:
        """Update current values in report from snapshot."""
        report.current_unique_colors = snapshot.unique_hardcoded_colors
        report.current_unique_spacings = snapshot.unique_hardcoded_spacings
        report.current_duplicate_clusters = (
            snapshot.duplicate_clusters_found + snapshot.near_duplicate_clusters_found
        )
        report.current_suppression_rate = snapshot.suppression_rate

    def _set_baseline_values(
        self, report: MetricsReport, snapshot: MetricSnapshot
    ) -> None:
        """Set baseline values from first snapshot."""
        report.baseline_unique_colors = snapshot.unique_hardcoded_colors
        report.baseline_unique_spacings = snapshot.unique_hardcoded_spacings
        report.baseline_duplicate_clusters = (
            snapshot.duplicate_clusters_found + snapshot.near_duplicate_clusters_found
        )

    def _update_percentiles(
        self, report: MetricsReport, tier: int, time_ms: float
    ) -> None:
        """Update performance percentiles for a tier.

        Uses simple incremental calculation for rolling percentiles.

        Args:
            report: Report to update.
            tier: Tier number (0, 1, or 2).
            time_ms: Analysis time in milliseconds.
        """
        # Get all times for this tier
        times = [
            s.analysis_time_ms for s in report.snapshots if s.tier == tier
        ]

        if not times:
            return

        times_sorted = sorted(times)
        n = len(times_sorted)

        # Calculate percentiles
        p50_idx = int(n * 0.50)
        p95_idx = min(int(n * 0.95), n - 1)
        p99_idx = min(int(n * 0.99), n - 1)

        percentiles = PerformancePercentiles(
            tier=tier,
            p50_ms=times_sorted[p50_idx],
            p95_ms=times_sorted[p95_idx],
            p99_ms=times_sorted[p99_idx],
            sample_count=n,
        )

        if tier == 0:
            report.tier_0_percentiles = percentiles
        elif tier == 1:
            report.tier_1_percentiles = percentiles
        elif tier == 2:
            report.tier_2_percentiles = percentiles

    def reset(self) -> None:
        """Clear all metrics and start fresh."""
        self._report = MetricsReport(project_path=str(self.project_path))
        if self.metrics_path.exists():
            self.metrics_path.unlink()


__all__ = ["MetricsCollector"]
