"""Task data models for implementation plans.

Defines Task, TaskGroup, and ImplementationPlan dataclasses
for structured implementation planning.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Task:
    """Single implementation task.

    Represents an actionable item in the implementation plan
    with priority, effort, and acceptance criteria.
    """

    id: str
    title: str
    description: str
    scope: str  # "tokens" | "components" | "pages"
    priority: int  # 1-5, 1 being highest priority
    estimated_effort: str  # "low" | "medium" | "high"
    impact: float  # 0.0-1.0, how much it improves consistency
    acceptance_criteria: list[str] = field(default_factory=list)
    evidence_links: list[str] = field(default_factory=list)  # file:line or screenshot paths
    related_critique_ids: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)  # task IDs
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "scope": self.scope,
            "priority": self.priority,
            "estimated_effort": self.estimated_effort,
            "impact": self.impact,
            "acceptance_criteria": self.acceptance_criteria,
            "evidence_links": self.evidence_links,
            "related_critique_ids": self.related_critique_ids,
            "dependencies": self.dependencies,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            scope=data["scope"],
            priority=data["priority"],
            estimated_effort=data["estimated_effort"],
            impact=data["impact"],
            acceptance_criteria=data.get("acceptance_criteria", []),
            evidence_links=data.get("evidence_links", []),
            related_critique_ids=data.get("related_critique_ids", []),
            dependencies=data.get("dependencies", []),
            tags=data.get("tags", []),
        )

    @property
    def priority_score(self) -> float:
        """Calculate priority score: impact / (1 + effort_score).

        Higher scores indicate higher priority (high impact, low effort).
        """
        effort_map = {"low": 0.3, "medium": 0.6, "high": 1.0}
        effort_score = effort_map.get(self.estimated_effort, 0.6)
        return self.impact / (1 + effort_score)

    @property
    def is_quick_win(self) -> bool:
        """Check if task is a quick win (high impact, low effort)."""
        return self.impact >= 0.7 and self.estimated_effort == "low"


@dataclass
class TaskGroup:
    """Group of related tasks by scope.

    Tasks are grouped by scope (tokens, components, pages)
    and ordered by priority within each group.
    """

    scope: str
    description: str
    tasks: list[Task] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "scope": self.scope,
            "description": self.description,
            "tasks": [t.to_dict() for t in self.tasks],
            "total_tasks": len(self.tasks),
            "total_effort": self.total_effort,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskGroup":
        """Create from dictionary."""
        return cls(
            scope=data["scope"],
            description=data["description"],
            tasks=[Task.from_dict(t) for t in data.get("tasks", [])],
        )

    @property
    def total_effort(self) -> str:
        """Estimate total effort for group.

        Returns combined effort level based on task counts.
        """
        effort_counts = {"low": 0, "medium": 0, "high": 0}
        for task in self.tasks:
            effort_counts[task.estimated_effort] = (
                effort_counts.get(task.estimated_effort, 0) + 1
            )

        # Weight: low=1, medium=2, high=4
        total_weight = (
            effort_counts["low"] * 1
            + effort_counts["medium"] * 2
            + effort_counts["high"] * 4
        )

        if total_weight <= 3:
            return "low"
        elif total_weight <= 8:
            return "medium"
        else:
            return "high"

    @property
    def quick_wins(self) -> list[Task]:
        """Get quick win tasks in this group."""
        return [t for t in self.tasks if t.is_quick_win]


@dataclass
class ImplementationPlan:
    """Complete implementation plan with grouped tasks.

    Contains all tasks organized by scope with summary
    statistics and quick win identification.
    """

    groups: list[TaskGroup] = field(default_factory=list)
    quick_wins: list[Task] = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    focus_area: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "groups": [g.to_dict() for g in self.groups],
            "quick_wins": [t.to_dict() for t in self.quick_wins],
            "generated_at": self.generated_at,
            "focus_area": self.focus_area,
            "summary": self.summary,
            "total_tasks": self.total_tasks,
            "estimated_total_effort": self.estimated_total_effort,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImplementationPlan":
        """Create from dictionary."""
        return cls(
            groups=[TaskGroup.from_dict(g) for g in data.get("groups", [])],
            quick_wins=[Task.from_dict(t) for t in data.get("quick_wins", [])],
            generated_at=data.get("generated_at", datetime.now().isoformat()),
            focus_area=data.get("focus_area"),
            summary=data.get("summary", ""),
        )

    @property
    def total_tasks(self) -> int:
        """Total number of tasks across all groups."""
        return sum(len(g.tasks) for g in self.groups)

    @property
    def estimated_total_effort(self) -> str:
        """Estimate total effort for entire plan.

        Returns combined effort level based on all tasks.
        """
        effort_counts = {"low": 0, "medium": 0, "high": 0}
        for group in self.groups:
            for task in group.tasks:
                effort_counts[task.estimated_effort] = (
                    effort_counts.get(task.estimated_effort, 0) + 1
                )

        total_weight = (
            effort_counts["low"] * 1
            + effort_counts["medium"] * 2
            + effort_counts["high"] * 4
        )

        if total_weight <= 5:
            return "low"
        elif total_weight <= 15:
            return "medium"
        else:
            return "high"

    @property
    def all_tasks(self) -> list[Task]:
        """Get all tasks from all groups."""
        tasks = []
        for group in self.groups:
            tasks.extend(group.tasks)
        return tasks

    def get_tasks_by_priority(self, max_priority: int = 3) -> list[Task]:
        """Get high-priority tasks.

        Args:
            max_priority: Maximum priority level to include (1=highest).

        Returns:
            Tasks with priority <= max_priority.
        """
        return [t for t in self.all_tasks if t.priority <= max_priority]

    def get_group_by_scope(self, scope: str) -> TaskGroup | None:
        """Get task group by scope.

        Args:
            scope: Scope name (tokens, components, pages).

        Returns:
            TaskGroup if found, None otherwise.
        """
        for group in self.groups:
            if group.scope == scope:
                return group
        return None


__all__ = [
    "Task",
    "TaskGroup",
    "ImplementationPlan",
]
