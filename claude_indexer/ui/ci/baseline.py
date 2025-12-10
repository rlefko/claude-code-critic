"""Baseline management for UI consistency checking.

This module provides baseline tracking to separate new issues from
existing (inherited) issues, enabling progressive adoption of UI
quality standards.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..config import UIQualityConfig
    from ..models import Finding

from .cross_file_analyzer import CrossFileClusterResult


@dataclass
class BaselineEntry:
    """Single entry in the baseline.

    Represents a known finding that existed before the current PR/commit.
    """

    finding_hash: str  # Hash of rule_id + source location
    rule_id: str
    file_path: str
    line_number: int
    summary: str = ""
    first_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now().isoformat())
    suppressed: bool = False
    suppression_reason: str | None = None
    suppression_expiry: str | None = None  # ISO date for temp suppressions

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "finding_hash": self.finding_hash,
            "rule_id": self.rule_id,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "summary": self.summary,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "suppressed": self.suppressed,
            "suppression_reason": self.suppression_reason,
            "suppression_expiry": self.suppression_expiry,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaselineEntry":
        """Create from dictionary."""
        return cls(
            finding_hash=data["finding_hash"],
            rule_id=data["rule_id"],
            file_path=data["file_path"],
            line_number=data["line_number"],
            summary=data.get("summary", ""),
            first_seen=data.get("first_seen", datetime.now().isoformat()),
            last_seen=data.get("last_seen", datetime.now().isoformat()),
            suppressed=data.get("suppressed", False),
            suppression_reason=data.get("suppression_reason"),
            suppression_expiry=data.get("suppression_expiry"),
        )


@dataclass
class BaselineReport:
    """Complete baseline state.

    Contains all known baseline entries and aggregate statistics.
    """

    version: str = "1.0"
    entries: list[BaselineEntry] = field(default_factory=list)
    rule_counts: dict[str, int] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
            "rule_counts": self.rule_counts,
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaselineReport":
        """Create from dictionary."""
        entries = [BaselineEntry.from_dict(e) for e in data.get("entries", [])]
        return cls(
            version=data.get("version", "1.0"),
            entries=entries,
            rule_counts=data.get("rule_counts", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            last_updated=data.get("last_updated", datetime.now().isoformat()),
        )

    def get_entries_by_rule(self, rule_id: str) -> list[BaselineEntry]:
        """Get all baseline entries for a rule.

        Args:
            rule_id: The rule ID to filter by.

        Returns:
            List of baseline entries for the rule.
        """
        return [e for e in self.entries if e.rule_id == rule_id]

    def get_entry_by_hash(self, finding_hash: str) -> BaselineEntry | None:
        """Get a baseline entry by its hash.

        Args:
            finding_hash: Hash of the finding.

        Returns:
            BaselineEntry if found, None otherwise.
        """
        for entry in self.entries:
            if entry.finding_hash == finding_hash:
                return entry
        return None

    def is_in_baseline(self, finding_hash: str) -> bool:
        """Check if a finding hash is in the baseline.

        Args:
            finding_hash: Hash of the finding.

        Returns:
            True if in baseline, False otherwise.
        """
        return self.get_entry_by_hash(finding_hash) is not None

    @property
    def total_entries(self) -> int:
        """Total number of baseline entries."""
        return len(self.entries)

    @property
    def suppressed_count(self) -> int:
        """Number of suppressed entries."""
        return sum(1 for e in self.entries if e.suppressed)


@dataclass
class CleanupItem:
    """Single item in the cleanup map.

    Represents a prioritized cleanup task based on baseline analysis.
    """

    rule_id: str
    count: int
    estimated_effort: str  # "low", "medium", "high"
    priority: int  # 1-5, 1 being highest
    sample_locations: list[str] = field(default_factory=list)  # Up to 3 examples
    suggested_approach: str = ""
    impact_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "count": self.count,
            "estimated_effort": self.estimated_effort,
            "priority": self.priority,
            "sample_locations": self.sample_locations,
            "suggested_approach": self.suggested_approach,
            "impact_description": self.impact_description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CleanupItem":
        """Create from dictionary."""
        return cls(
            rule_id=data["rule_id"],
            count=data["count"],
            estimated_effort=data.get("estimated_effort", "medium"),
            priority=data.get("priority", 3),
            sample_locations=data.get("sample_locations", []),
            suggested_approach=data.get("suggested_approach", ""),
            impact_description=data.get("impact_description", ""),
        )


@dataclass
class CleanupMap:
    """Prioritized cleanup recommendations.

    Provides an ordered list of cleanup tasks based on impact and effort.
    """

    items: list[CleanupItem] = field(default_factory=list)
    total_baseline_issues: int = 0
    estimated_total_effort: str = "unknown"
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "items": [item.to_dict() for item in self.items],
            "total_baseline_issues": self.total_baseline_issues,
            "estimated_total_effort": self.estimated_total_effort,
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CleanupMap":
        """Create from dictionary."""
        items = [CleanupItem.from_dict(i) for i in data.get("items", [])]
        return cls(
            items=items,
            total_baseline_issues=data.get("total_baseline_issues", 0),
            estimated_total_effort=data.get("estimated_total_effort", "unknown"),
            generated_at=data.get("generated_at", datetime.now().isoformat()),
        )

    def get_by_priority(self, max_priority: int = 3) -> list[CleanupItem]:
        """Get items up to a given priority level.

        Args:
            max_priority: Maximum priority level (1-5, 1 being highest).

        Returns:
            List of cleanup items at or above the priority level.
        """
        return [item for item in self.items if item.priority <= max_priority]


class BaselineManager:
    """Manages baseline state for progressive adoption.

    Provides functionality to load, save, compare, and update the
    baseline of known UI issues.
    """

    BASELINE_FILE = ".ui-quality/baseline.json"
    BASELINE_VERSION = "1.0"

    # Effort estimates by rule type
    EFFORT_MAP = {
        "COLOR.NON_TOKEN": "low",
        "SPACING.OFF_SCALE": "low",
        "RADIUS.OFF_SCALE": "low",
        "TYPOGRAPHY.OFF_SCALE": "low",
        "STYLE.DUPLICATE_SET": "medium",
        "STYLE.NEAR_DUPLICATE_SET": "medium",
        "UTILITY.DUPLICATE_SEQUENCE": "low",
        "COMPONENT.DUPLICATE_CLUSTER": "high",
        "ROLE.OUTLIER.BUTTON": "medium",
        "ROLE.OUTLIER.INPUT": "medium",
        "ROLE.OUTLIER.CARD": "medium",
        "FOCUS.RING.INCONSISTENT": "medium",
        "CSS.SPECIFICITY.ESCALATION": "medium",
        "IMPORTANT.NEW_USAGE": "low",
        "SUPPRESSION.NO_RATIONALE": "low",
    }

    # Suggested approaches by rule type
    APPROACH_MAP = {
        "COLOR.NON_TOKEN": "Replace hardcoded colors with design tokens",
        "SPACING.OFF_SCALE": "Use spacing scale values (4, 8, 12, 16, etc.)",
        "RADIUS.OFF_SCALE": "Use radius tokens from design system",
        "TYPOGRAPHY.OFF_SCALE": "Apply typography scale presets",
        "STYLE.DUPLICATE_SET": "Extract to shared CSS class or utility",
        "STYLE.NEAR_DUPLICATE_SET": "Consolidate into single parameterized style",
        "UTILITY.DUPLICATE_SEQUENCE": "Create composite utility class",
        "COMPONENT.DUPLICATE_CLUSTER": "Extract shared component with variants",
        "ROLE.OUTLIER.BUTTON": "Standardize button styles to match majority",
        "ROLE.OUTLIER.INPUT": "Align input styles with design system",
        "ROLE.OUTLIER.CARD": "Use consistent card component styling",
        "FOCUS.RING.INCONSISTENT": "Apply uniform focus ring styling",
        "CSS.SPECIFICITY.ESCALATION": "Reduce selector specificity",
        "IMPORTANT.NEW_USAGE": "Remove !important by fixing specificity",
        "SUPPRESSION.NO_RATIONALE": "Add rationale comment for suppression",
    }

    def __init__(self, project_path: Path, config: "UIQualityConfig"):
        """Initialize the baseline manager.

        Args:
            project_path: Root path of the project.
            config: UI quality configuration.
        """
        self.project_path = Path(project_path)
        self.config = config
        self.baseline_path = self.project_path / self.BASELINE_FILE
        self._baseline: BaselineReport | None = None

    def load(self) -> BaselineReport:
        """Load baseline from disk, creating if needed.

        Returns:
            Loaded or newly created BaselineReport.
        """
        if self._baseline is not None:
            return self._baseline

        if not self.baseline_path.exists():
            self._baseline = BaselineReport()
            return self._baseline

        try:
            with open(self.baseline_path, "r") as f:
                data = json.load(f)
                self._baseline = BaselineReport.from_dict(data)

                # Check version compatibility
                if self._baseline.version != self.BASELINE_VERSION:
                    # Future: handle migrations
                    pass

                return self._baseline

        except (json.JSONDecodeError, KeyError, TypeError):
            # Corrupted baseline, start fresh
            self._baseline = BaselineReport()
            return self._baseline

    def save(self, baseline: BaselineReport | None = None) -> None:
        """Save baseline to disk.

        Args:
            baseline: Optional baseline to save. Uses loaded baseline if None.
        """
        baseline_to_save = baseline or self._baseline
        if baseline_to_save is None:
            return

        # Ensure directory exists
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)

        # Update timestamps
        baseline_to_save.last_updated = datetime.now().isoformat()

        with open(self.baseline_path, "w") as f:
            json.dump(baseline_to_save.to_dict(), f, indent=2)

    def update_from_findings(self, findings: list["Finding"]) -> BaselineReport:
        """Update baseline with new finding state.

        Adds new findings to baseline and updates last_seen for existing.

        Args:
            findings: List of current findings.

        Returns:
            Updated BaselineReport.
        """
        baseline = self.load()
        now = datetime.now().isoformat()

        # Build lookup of existing entries by hash
        existing_by_hash = {e.finding_hash: e for e in baseline.entries}

        # Process each finding
        new_entries = []
        for finding in findings:
            finding_hash = self._compute_finding_hash(finding)

            if finding_hash in existing_by_hash:
                # Update last_seen for existing entry
                existing_by_hash[finding_hash].last_seen = now
            else:
                # Add new entry
                file_path = ""
                line_number = 0
                if finding.source_ref:
                    file_path = finding.source_ref.file_path
                    line_number = finding.source_ref.start_line

                new_entries.append(
                    BaselineEntry(
                        finding_hash=finding_hash,
                        rule_id=finding.rule_id,
                        file_path=file_path,
                        line_number=line_number,
                        summary=finding.summary,
                        first_seen=now,
                        last_seen=now,
                    )
                )

        # Combine existing and new entries
        baseline.entries = list(existing_by_hash.values()) + new_entries

        # Update rule counts
        baseline.rule_counts = {}
        for entry in baseline.entries:
            baseline.rule_counts[entry.rule_id] = (
                baseline.rule_counts.get(entry.rule_id, 0) + 1
            )

        self._baseline = baseline
        return baseline

    def separate_findings(
        self, findings: list["Finding"]
    ) -> tuple[list["Finding"], list["Finding"]]:
        """Separate new findings from baseline findings.

        Args:
            findings: List of all findings.

        Returns:
            Tuple of (new_findings, baseline_findings).
        """
        baseline = self.load()

        new_findings = []
        baseline_findings = []

        for finding in findings:
            finding_hash = self._compute_finding_hash(finding)

            if baseline.is_in_baseline(finding_hash):
                # Mark as baseline finding
                finding.is_new = False
                baseline_findings.append(finding)
            else:
                # New finding
                finding.is_new = True
                new_findings.append(finding)

        return new_findings, baseline_findings

    def generate_cleanup_map(
        self,
        baseline: BaselineReport | None = None,
        cross_file_result: CrossFileClusterResult | None = None,
    ) -> CleanupMap:
        """Generate prioritized cleanup recommendations.

        Prioritization factors:
        1. Severity/impact of issues
        2. Count of occurrences
        3. Cross-file cluster size (from cross_file_result)
        4. Estimated effort (smaller = higher priority)

        Args:
            baseline: Optional baseline to use. Loads from disk if None.
            cross_file_result: Optional cross-file analysis result for context.

        Returns:
            CleanupMap with prioritized items.
        """
        baseline = baseline or self.load()

        # Group entries by rule
        rule_entries: dict[str, list[BaselineEntry]] = {}
        for entry in baseline.entries:
            if entry.suppressed:
                continue
            if entry.rule_id not in rule_entries:
                rule_entries[entry.rule_id] = []
            rule_entries[entry.rule_id].append(entry)

        # Create cleanup items
        items: list[CleanupItem] = []
        for rule_id, entries in rule_entries.items():
            count = len(entries)
            effort = self.EFFORT_MAP.get(rule_id, "medium")
            approach = self.APPROACH_MAP.get(rule_id, "Review and fix manually")

            # Sample up to 3 locations
            sample_locations = [
                f"{e.file_path}:{e.line_number}" for e in entries[:3]
            ]

            # Calculate priority based on count and effort
            priority = self._calculate_priority(count, effort, rule_id)

            # Generate impact description
            impact = self._generate_impact_description(rule_id, count)

            items.append(
                CleanupItem(
                    rule_id=rule_id,
                    count=count,
                    estimated_effort=effort,
                    priority=priority,
                    sample_locations=sample_locations,
                    suggested_approach=approach,
                    impact_description=impact,
                )
            )

        # Sort by priority (ascending, 1 is highest)
        items.sort(key=lambda x: (x.priority, -x.count))

        # Estimate total effort
        total_effort = self._estimate_total_effort(items)

        return CleanupMap(
            items=items,
            total_baseline_issues=baseline.total_entries - baseline.suppressed_count,
            estimated_total_effort=total_effort,
        )

    def reset(self) -> None:
        """Clear baseline and start fresh."""
        self._baseline = BaselineReport()
        if self.baseline_path.exists():
            self.baseline_path.unlink()

    def _compute_finding_hash(self, finding: "Finding") -> str:
        """Create stable hash for finding deduplication.

        Hash is based on rule_id and source location (file:line).

        Args:
            finding: Finding to hash.

        Returns:
            SHA256 hash string (first 16 chars).
        """
        file_path = ""
        line_number = 0
        if finding.source_ref:
            file_path = finding.source_ref.file_path
            line_number = finding.source_ref.start_line

        hash_input = f"{finding.rule_id}:{file_path}:{line_number}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _calculate_priority(self, count: int, effort: str, rule_id: str) -> int:
        """Calculate priority based on count, effort, and rule type.

        Args:
            count: Number of occurrences.
            effort: Estimated effort level.
            rule_id: The rule identifier.

        Returns:
            Priority level 1-5 (1 being highest).
        """
        # Start with base priority
        priority = 3

        # High count increases priority
        if count >= 20:
            priority -= 1
        elif count >= 10:
            priority -= 0.5

        # Low effort increases priority (easier to fix)
        if effort == "low":
            priority -= 0.5
        elif effort == "high":
            priority += 0.5

        # Token drift rules are high priority (prevent entropy)
        if "NON_TOKEN" in rule_id or "OFF_SCALE" in rule_id:
            priority -= 0.5

        # Duplicate clusters are high impact
        if "DUPLICATE" in rule_id or "CLUSTER" in rule_id:
            priority -= 0.5

        # Clamp to 1-5 range
        return max(1, min(5, round(priority)))

    def _estimate_total_effort(self, items: list[CleanupItem]) -> str:
        """Estimate total effort for all cleanup items.

        Args:
            items: List of cleanup items.

        Returns:
            Effort estimate string.
        """
        total_score = 0
        for item in items:
            effort_multiplier = {"low": 1, "medium": 2, "high": 4}.get(
                item.estimated_effort, 2
            )
            total_score += item.count * effort_multiplier

        if total_score < 20:
            return "small (a few hours)"
        elif total_score < 100:
            return "medium (a few days)"
        elif total_score < 500:
            return "large (a sprint)"
        else:
            return "very large (multiple sprints)"

    def _generate_impact_description(self, rule_id: str, count: int) -> str:
        """Generate human-readable impact description.

        Args:
            rule_id: The rule identifier.
            count: Number of occurrences.

        Returns:
            Impact description string.
        """
        if "COLOR" in rule_id:
            return f"{count} hardcoded colors not using design tokens"
        elif "SPACING" in rule_id:
            return f"{count} off-scale spacing values"
        elif "RADIUS" in rule_id:
            return f"{count} non-standard border radius values"
        elif "TYPOGRAPHY" in rule_id:
            return f"{count} typography values outside scale"
        elif "DUPLICATE" in rule_id or "CLUSTER" in rule_id:
            return f"{count} duplicate/near-duplicate patterns to consolidate"
        elif "OUTLIER" in rule_id:
            return f"{count} inconsistent role-based styles"
        elif "FOCUS" in rule_id:
            return f"{count} inconsistent focus ring implementations"
        elif "SPECIFICITY" in rule_id:
            return f"{count} CSS specificity escalations"
        elif "IMPORTANT" in rule_id:
            return f"{count} !important usages to review"
        elif "SUPPRESSION" in rule_id:
            return f"{count} suppressions missing rationale"
        else:
            return f"{count} issues of type {rule_id}"


__all__ = [
    "BaselineEntry",
    "BaselineReport",
    "CleanupItem",
    "CleanupMap",
    "BaselineManager",
]
