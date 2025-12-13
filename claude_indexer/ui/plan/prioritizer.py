"""Task prioritizer for implementation planning.

Prioritizes tasks based on impact, effort, and dependencies
to create an optimal execution order.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .task import Task


@dataclass
class PrioritizationConfig:
    """Configuration for task prioritization."""

    impact_weight: float = 0.6  # Weight for impact in scoring
    effort_weight: float = 0.4  # Weight for effort (inverse) in scoring
    dependency_penalty: float = 0.1  # Score reduction per dependency
    max_tasks_per_scope: int = 10  # Cap tasks per scope


class TaskPrioritizer:
    """Prioritizes and orders implementation tasks.

    Uses impact/effort ratio with dependency analysis to
    produce an optimal task ordering.
    """

    # Effort scores (higher = more effort)
    EFFORT_SCORES = {
        "low": 0.3,
        "medium": 0.6,
        "high": 1.0,
    }

    # Scope priority order (tokens first, then components, then pages)
    SCOPE_ORDER = {
        "tokens": 1,
        "components": 2,
        "pages": 3,
    }

    def __init__(self, config: PrioritizationConfig | None = None):
        """Initialize the prioritizer.

        Args:
            config: Optional prioritization configuration.
        """
        self.config = config or PrioritizationConfig()

    def calculate_priority_score(self, task: "Task") -> float:
        """Calculate priority score for a task.

        Score formula: (impact * impact_weight) / (effort * effort_weight + 1)
        Higher scores indicate higher priority.

        Args:
            task: Task to score.

        Returns:
            Priority score (higher = more priority).
        """
        effort_score = self.EFFORT_SCORES.get(task.estimated_effort, 0.6)

        # Base score: impact / (1 + effort)
        base_score = task.impact / (1 + effort_score * self.config.effort_weight)

        # Apply dependency penalty
        dependency_penalty = len(task.dependencies) * self.config.dependency_penalty
        score = base_score - dependency_penalty

        return max(0.0, score)

    def prioritize(self, tasks: list["Task"]) -> list["Task"]:
        """Sort tasks by priority score.

        Args:
            tasks: List of tasks to prioritize.

        Returns:
            Tasks sorted by priority (highest first).
        """
        # Calculate scores
        scored_tasks = [(task, self.calculate_priority_score(task)) for task in tasks]

        # Sort by score descending
        scored_tasks.sort(key=lambda x: x[1], reverse=True)

        return [task for task, _ in scored_tasks]

    def assign_priorities(self, tasks: list["Task"]) -> list["Task"]:
        """Assign priority levels (1-5) to tasks based on scores.

        Priority 1 = top 20%, Priority 2 = next 20%, etc.

        Args:
            tasks: List of tasks.

        Returns:
            Tasks with priority field updated.
        """
        if not tasks:
            return tasks

        # Calculate scores
        scored_tasks = [(task, self.calculate_priority_score(task)) for task in tasks]

        # Sort by score descending
        scored_tasks.sort(key=lambda x: x[1], reverse=True)

        # Assign priorities based on position
        total = len(scored_tasks)
        for i, (task, _) in enumerate(scored_tasks):
            percentile = i / total
            if percentile < 0.2:
                task.priority = 1
            elif percentile < 0.4:
                task.priority = 2
            elif percentile < 0.6:
                task.priority = 3
            elif percentile < 0.8:
                task.priority = 4
            else:
                task.priority = 5

        return [task for task, _ in scored_tasks]

    def identify_quick_wins(self, tasks: list["Task"]) -> list["Task"]:
        """Identify quick win tasks (high impact, low effort).

        Args:
            tasks: List of tasks.

        Returns:
            List of quick win tasks.
        """
        quick_wins = []
        for task in tasks:
            if (
                task.impact >= 0.7
                and task.estimated_effort == "low"
                or task.impact >= 0.8
                and task.estimated_effort == "medium"
            ):
                quick_wins.append(task)

        # Sort by impact descending
        quick_wins.sort(key=lambda t: t.impact, reverse=True)

        return quick_wins[:5]  # Limit to top 5 quick wins

    def resolve_dependencies(self, tasks: list["Task"]) -> list["Task"]:
        """Reorder tasks to respect dependencies.

        Ensures tasks with dependencies come after their dependencies.

        Args:
            tasks: List of tasks.

        Returns:
            Tasks reordered to respect dependencies.
        """
        # Build dependency graph
        task_by_id = {task.id: task for task in tasks}
        dependents: dict[str, list[str]] = defaultdict(list)

        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in task_by_id:
                    dependents[dep_id].append(task.id)

        # Topological sort
        visited: set[str] = set()
        result: list[Task] = []

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            visited.add(task_id)

            task = task_by_id.get(task_id)
            if task:
                # Visit dependencies first
                for dep_id in task.dependencies:
                    if dep_id in task_by_id:
                        visit(dep_id)
                result.append(task)

        # Visit all tasks
        for task in tasks:
            visit(task.id)

        return result

    def group_by_scope(self, tasks: list["Task"]) -> dict[str, list["Task"]]:
        """Group tasks by scope.

        Args:
            tasks: List of tasks.

        Returns:
            Dict mapping scope to list of tasks.
        """
        groups: dict[str, list[Task]] = defaultdict(list)
        for task in tasks:
            groups[task.scope].append(task)

        # Sort within each group by priority
        for scope in groups:
            groups[scope].sort(key=lambda t: t.priority)

        return dict(groups)

    def cap_tasks_per_scope(
        self, grouped_tasks: dict[str, list["Task"]]
    ) -> dict[str, list["Task"]]:
        """Cap number of tasks per scope.

        Args:
            grouped_tasks: Dict mapping scope to tasks.

        Returns:
            Capped dict.
        """
        max_tasks = self.config.max_tasks_per_scope
        return {scope: tasks[:max_tasks] for scope, tasks in grouped_tasks.items()}

    def full_prioritization(self, tasks: list["Task"]) -> list["Task"]:
        """Run full prioritization pipeline.

        1. Calculate and assign priorities
        2. Resolve dependencies
        3. Sort by scope order then priority

        Args:
            tasks: List of tasks.

        Returns:
            Fully prioritized task list.
        """
        if not tasks:
            return []

        # Step 1: Assign priorities
        tasks = self.assign_priorities(tasks)

        # Step 2: Resolve dependencies
        tasks = self.resolve_dependencies(tasks)

        # Step 3: Sort by scope then priority
        def sort_key(task: "Task") -> tuple[int, int, float]:
            scope_order = self.SCOPE_ORDER.get(task.scope, 99)
            return (scope_order, task.priority, -task.impact)

        tasks.sort(key=sort_key)

        return tasks


__all__ = [
    "PrioritizationConfig",
    "TaskPrioritizer",
]
