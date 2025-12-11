"""Data models for UI metrics tracking.

This module defines the core data structures for tracking UI quality
metrics over time, including performance percentiles and success criteria.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class MetricSnapshot:
    """Point-in-time metric capture from an audit run.

    Records key metrics from a single UI quality audit for
    historical tracking and trend analysis.
    """

    timestamp: str  # ISO format
    tier: int  # 0 = pre-commit, 1 = CI, 2 = /redesign

    # Token drift metrics
    unique_hardcoded_colors: int = 0
    unique_hardcoded_spacings: int = 0
    unique_off_scale_radii: int = 0
    unique_off_scale_typography: int = 0

    # Deduplication metrics
    duplicate_clusters_found: int = 0
    near_duplicate_clusters_found: int = 0

    # Finding counts
    total_findings: int = 0
    new_findings: int = 0
    baseline_findings: int = 0
    suppressed_findings: int = 0

    # Calculated rates
    suppression_rate: float = 0.0  # suppressed / total_baseline

    # Plan adoption (Tier 2 only)
    plan_tasks_generated: int = 0

    # Performance metrics
    analysis_time_ms: float = 0.0
    files_analyzed: int = 0
    cache_hit_rate: float = 0.0

    # Git context
    commit_hash: str | None = None
    branch_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "tier": self.tier,
            "unique_hardcoded_colors": self.unique_hardcoded_colors,
            "unique_hardcoded_spacings": self.unique_hardcoded_spacings,
            "unique_off_scale_radii": self.unique_off_scale_radii,
            "unique_off_scale_typography": self.unique_off_scale_typography,
            "duplicate_clusters_found": self.duplicate_clusters_found,
            "near_duplicate_clusters_found": self.near_duplicate_clusters_found,
            "total_findings": self.total_findings,
            "new_findings": self.new_findings,
            "baseline_findings": self.baseline_findings,
            "suppressed_findings": self.suppressed_findings,
            "suppression_rate": self.suppression_rate,
            "plan_tasks_generated": self.plan_tasks_generated,
            "analysis_time_ms": self.analysis_time_ms,
            "files_analyzed": self.files_analyzed,
            "cache_hit_rate": self.cache_hit_rate,
            "commit_hash": self.commit_hash,
            "branch_name": self.branch_name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricSnapshot":
        """Create from dictionary."""
        return cls(
            timestamp=data["timestamp"],
            tier=data["tier"],
            unique_hardcoded_colors=data.get("unique_hardcoded_colors", 0),
            unique_hardcoded_spacings=data.get("unique_hardcoded_spacings", 0),
            unique_off_scale_radii=data.get("unique_off_scale_radii", 0),
            unique_off_scale_typography=data.get("unique_off_scale_typography", 0),
            duplicate_clusters_found=data.get("duplicate_clusters_found", 0),
            near_duplicate_clusters_found=data.get("near_duplicate_clusters_found", 0),
            total_findings=data.get("total_findings", 0),
            new_findings=data.get("new_findings", 0),
            baseline_findings=data.get("baseline_findings", 0),
            suppressed_findings=data.get("suppressed_findings", 0),
            suppression_rate=data.get("suppression_rate", 0.0),
            plan_tasks_generated=data.get("plan_tasks_generated", 0),
            analysis_time_ms=data.get("analysis_time_ms", 0.0),
            files_analyzed=data.get("files_analyzed", 0),
            cache_hit_rate=data.get("cache_hit_rate", 0.0),
            commit_hash=data.get("commit_hash"),
            branch_name=data.get("branch_name"),
        )


@dataclass
class PerformancePercentiles:
    """Performance latency percentiles for a tier.

    Tracks p50, p95, and p99 latencies for performance monitoring.
    """

    tier: int
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    sample_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "tier": self.tier,
            "p50_ms": self.p50_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "sample_count": self.sample_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerformancePercentiles":
        """Create from dictionary."""
        return cls(
            tier=data["tier"],
            p50_ms=data.get("p50_ms", 0.0),
            p95_ms=data.get("p95_ms", 0.0),
            p99_ms=data.get("p99_ms", 0.0),
            sample_count=data.get("sample_count", 0),
        )

    def meets_target(self, target_p95_ms: float) -> bool:
        """Check if p95 meets the target latency."""
        return self.p95_ms <= target_p95_ms


@dataclass
class PlanAdoptionRecord:
    """Record of /redesign plan adoption.

    Tracks which generated plans led to completed work.
    """

    plan_id: str
    generated_at: str  # ISO format
    total_tasks: int
    completed_tasks: int = 0
    completed_at: str | None = None  # ISO format when marked complete

    @property
    def adoption_rate(self) -> float:
        """Calculate adoption rate (completed / total)."""
        if self.total_tasks == 0:
            return 0.0
        return self.completed_tasks / self.total_tasks

    @property
    def is_complete(self) -> bool:
        """Check if plan is fully completed."""
        return self.completed_tasks >= self.total_tasks

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "plan_id": self.plan_id,
            "generated_at": self.generated_at,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanAdoptionRecord":
        """Create from dictionary."""
        return cls(
            plan_id=data["plan_id"],
            generated_at=data["generated_at"],
            total_tasks=data["total_tasks"],
            completed_tasks=data.get("completed_tasks", 0),
            completed_at=data.get("completed_at"),
        )


@dataclass
class MetricsReport:
    """Aggregated metrics with historical snapshots.

    Combines point-in-time snapshots with aggregated statistics
    and target tracking from PRD success criteria.
    """

    version: str = "1.0"
    project_path: str = ""

    # Historical snapshots (rolling window)
    snapshots: list[MetricSnapshot] = field(default_factory=list)

    # Plan adoption records
    plan_records: list[PlanAdoptionRecord] = field(default_factory=list)

    # Baseline values (first recorded)
    baseline_unique_colors: int = 0
    baseline_unique_spacings: int = 0
    baseline_duplicate_clusters: int = 0

    # Current values (most recent snapshot)
    current_unique_colors: int = 0
    current_unique_spacings: int = 0
    current_duplicate_clusters: int = 0
    current_suppression_rate: float = 0.0

    # Performance percentiles by tier
    tier_0_percentiles: PerformancePercentiles = field(
        default_factory=lambda: PerformancePercentiles(tier=0)
    )
    tier_1_percentiles: PerformancePercentiles = field(
        default_factory=lambda: PerformancePercentiles(tier=1)
    )
    tier_2_percentiles: PerformancePercentiles = field(
        default_factory=lambda: PerformancePercentiles(tier=2)
    )

    # PRD targets
    targets: dict[str, Any] = field(
        default_factory=lambda: {
            "color_reduction_percent": 50.0,  # 50% reduction over 3 months
            "clusters_resolved_monthly": 10,  # 10+ per month
            "suppression_rate_max": 0.05,  # <5% suppression
            "plan_adoption_min": 0.70,  # >70% adoption
            "tier_0_p95_ms": 300,  # <300ms pre-commit
            "tier_1_p95_ms": 600000,  # <10 min CI
            "tier_2_p95_ms": 300000,  # <5 min /redesign
        }
    )

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "project_path": self.project_path,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "plan_records": [p.to_dict() for p in self.plan_records],
            "baseline_unique_colors": self.baseline_unique_colors,
            "baseline_unique_spacings": self.baseline_unique_spacings,
            "baseline_duplicate_clusters": self.baseline_duplicate_clusters,
            "current_unique_colors": self.current_unique_colors,
            "current_unique_spacings": self.current_unique_spacings,
            "current_duplicate_clusters": self.current_duplicate_clusters,
            "current_suppression_rate": self.current_suppression_rate,
            "tier_0_percentiles": self.tier_0_percentiles.to_dict(),
            "tier_1_percentiles": self.tier_1_percentiles.to_dict(),
            "tier_2_percentiles": self.tier_2_percentiles.to_dict(),
            "targets": self.targets,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MetricsReport":
        """Create from dictionary."""
        snapshots = [MetricSnapshot.from_dict(s) for s in data.get("snapshots", [])]
        plan_records = [
            PlanAdoptionRecord.from_dict(p) for p in data.get("plan_records", [])
        ]

        return cls(
            version=data.get("version", "1.0"),
            project_path=data.get("project_path", ""),
            snapshots=snapshots,
            plan_records=plan_records,
            baseline_unique_colors=data.get("baseline_unique_colors", 0),
            baseline_unique_spacings=data.get("baseline_unique_spacings", 0),
            baseline_duplicate_clusters=data.get("baseline_duplicate_clusters", 0),
            current_unique_colors=data.get("current_unique_colors", 0),
            current_unique_spacings=data.get("current_unique_spacings", 0),
            current_duplicate_clusters=data.get("current_duplicate_clusters", 0),
            current_suppression_rate=data.get("current_suppression_rate", 0.0),
            tier_0_percentiles=PerformancePercentiles.from_dict(
                data.get("tier_0_percentiles", {"tier": 0})
            ),
            tier_1_percentiles=PerformancePercentiles.from_dict(
                data.get("tier_1_percentiles", {"tier": 1})
            ),
            tier_2_percentiles=PerformancePercentiles.from_dict(
                data.get("tier_2_percentiles", {"tier": 2})
            ),
            targets=data.get(
                "targets",
                cls.__dataclass_fields__["targets"].default_factory(),
            ),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
        )

    @property
    def color_reduction_percent(self) -> float:
        """Calculate % reduction in unique hardcoded colors."""
        if self.baseline_unique_colors == 0:
            return 0.0
        return (
            (self.baseline_unique_colors - self.current_unique_colors)
            / self.baseline_unique_colors
        ) * 100

    @property
    def spacing_reduction_percent(self) -> float:
        """Calculate % reduction in unique hardcoded spacings."""
        if self.baseline_unique_spacings == 0:
            return 0.0
        return (
            (self.baseline_unique_spacings - self.current_unique_spacings)
            / self.baseline_unique_spacings
        ) * 100

    @property
    def plan_adoption_rate(self) -> float:
        """Calculate overall plan adoption rate."""
        if not self.plan_records:
            return 0.0
        total_tasks = sum(p.total_tasks for p in self.plan_records)
        completed_tasks = sum(p.completed_tasks for p in self.plan_records)
        if total_tasks == 0:
            return 0.0
        return completed_tasks / total_tasks

    @property
    def snapshot_count(self) -> int:
        """Total number of snapshots."""
        return len(self.snapshots)


__all__ = [
    "MetricSnapshot",
    "PerformancePercentiles",
    "PlanAdoptionRecord",
    "MetricsReport",
]
