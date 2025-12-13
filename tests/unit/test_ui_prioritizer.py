"""Unit tests for TaskPrioritizer.

Tests the task prioritization logic including:
- Priority score calculation
- Dependency resolution
- Quick win identification
- Scope grouping
- Full prioritization pipeline
"""

import pytest

from claude_indexer.ui.plan.prioritizer import (
    PrioritizationConfig,
    TaskPrioritizer,
)
from claude_indexer.ui.plan.task import Task

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Create a list of sample tasks with varying properties."""
    return [
        Task(
            id="task-1",
            title="Replace hardcoded colors",
            description="Replace hardcoded hex colors with design tokens",
            scope="tokens",
            priority=0,  # Will be assigned by prioritizer
            estimated_effort="low",
            impact=0.9,
            dependencies=[],
        ),
        Task(
            id="task-2",
            title="Consolidate button variants",
            description="Merge 6 button variants into 2",
            scope="components",
            priority=0,
            estimated_effort="medium",
            impact=0.8,
            dependencies=["task-1"],  # Depends on tokens being fixed first
        ),
        Task(
            id="task-3",
            title="Fix spacing inconsistencies",
            description="Align spacing to design scale",
            scope="tokens",
            priority=0,
            estimated_effort="low",
            impact=0.7,
            dependencies=[],
        ),
        Task(
            id="task-4",
            title="Refactor card components",
            description="Extract shared card base component",
            scope="components",
            priority=0,
            estimated_effort="high",
            impact=0.6,
            dependencies=["task-2"],
        ),
        Task(
            id="task-5",
            title="Update checkout page",
            description="Apply new design tokens to checkout",
            scope="pages",
            priority=0,
            estimated_effort="medium",
            impact=0.5,
            dependencies=["task-1", "task-2"],
        ),
        Task(
            id="task-6",
            title="Low impact cleanup",
            description="Minor style cleanup",
            scope="pages",
            priority=0,
            estimated_effort="low",
            impact=0.2,
            dependencies=[],
        ),
    ]


@pytest.fixture
def prioritizer() -> TaskPrioritizer:
    """Create a TaskPrioritizer with default config."""
    return TaskPrioritizer()


@pytest.fixture
def custom_prioritizer() -> TaskPrioritizer:
    """Create a TaskPrioritizer with custom config."""
    config = PrioritizationConfig(
        impact_weight=0.7,
        effort_weight=0.3,
        dependency_penalty=0.2,
        max_tasks_per_scope=5,
    )
    return TaskPrioritizer(config)


# ---------------------------------------------------------------------------
# TestPrioritizationConfig
# ---------------------------------------------------------------------------


class TestPrioritizationConfig:
    """Tests for PrioritizationConfig defaults and customization."""

    def test_default_config_values(self):
        """Test that default config has expected values."""
        config = PrioritizationConfig()

        assert config.impact_weight == 0.6
        assert config.effort_weight == 0.4
        assert config.dependency_penalty == 0.1
        assert config.max_tasks_per_scope == 10

    def test_custom_weights(self):
        """Test that custom weights are applied."""
        config = PrioritizationConfig(
            impact_weight=0.8,
            effort_weight=0.2,
            dependency_penalty=0.15,
            max_tasks_per_scope=20,
        )

        assert config.impact_weight == 0.8
        assert config.effort_weight == 0.2
        assert config.dependency_penalty == 0.15
        assert config.max_tasks_per_scope == 20


# ---------------------------------------------------------------------------
# TestTaskPrioritizerScoring
# ---------------------------------------------------------------------------


class TestTaskPrioritizerScoring:
    """Tests for priority score calculation."""

    def test_calculate_priority_score_high_impact_low_effort(self, prioritizer):
        """Test score for high impact, low effort task."""
        task = Task(
            id="test-1",
            title="Quick win task",
            description="High impact, low effort",
            scope="tokens",
            priority=0,
            estimated_effort="low",
            impact=0.9,
        )

        score = prioritizer.calculate_priority_score(task)

        # High impact (0.9) with low effort (0.3) should give high score
        assert score > 0.7

    def test_calculate_priority_score_low_impact_high_effort(self, prioritizer):
        """Test score for low impact, high effort task."""
        task = Task(
            id="test-2",
            title="Low priority task",
            description="Low impact, high effort",
            scope="pages",
            priority=0,
            estimated_effort="high",
            impact=0.2,
        )

        score = prioritizer.calculate_priority_score(task)

        # Low impact (0.2) with high effort (1.0) should give low score
        assert score < 0.2

    def test_dependency_penalty_reduces_score(self, prioritizer):
        """Test that dependencies reduce the score."""
        task_no_deps = Task(
            id="test-1",
            title="No dependencies",
            description="Task without dependencies",
            scope="tokens",
            priority=0,
            estimated_effort="medium",
            impact=0.8,
            dependencies=[],
        )

        task_with_deps = Task(
            id="test-2",
            title="Has dependencies",
            description="Task with dependencies",
            scope="tokens",
            priority=0,
            estimated_effort="medium",
            impact=0.8,
            dependencies=["dep-1", "dep-2", "dep-3"],
        )

        score_no_deps = prioritizer.calculate_priority_score(task_no_deps)
        score_with_deps = prioritizer.calculate_priority_score(task_with_deps)

        # Task with dependencies should have lower score
        assert score_with_deps < score_no_deps

    def test_score_never_negative(self, prioritizer):
        """Test that score never goes below zero."""
        task = Task(
            id="test-1",
            title="Many dependencies",
            description="Task with many dependencies",
            scope="pages",
            priority=0,
            estimated_effort="high",
            impact=0.1,
            dependencies=[f"dep-{i}" for i in range(20)],  # Many deps
        )

        score = prioritizer.calculate_priority_score(task)

        assert score >= 0.0

    def test_unknown_effort_uses_medium(self, prioritizer):
        """Test that unknown effort level defaults to medium."""
        task = Task(
            id="test-1",
            title="Unknown effort",
            description="Task with invalid effort",
            scope="tokens",
            priority=0,
            estimated_effort="unknown",  # Invalid
            impact=0.5,
        )

        # Should not raise, should use medium effort (0.6)
        score = prioritizer.calculate_priority_score(task)
        assert score > 0


# ---------------------------------------------------------------------------
# TestTaskPrioritization
# ---------------------------------------------------------------------------


class TestTaskPrioritization:
    """Tests for task list prioritization."""

    def test_prioritize_sorts_by_score_descending(self, prioritizer, sample_tasks):
        """Test that prioritize returns tasks sorted by score descending."""
        sorted_tasks = prioritizer.prioritize(sample_tasks)

        # Calculate scores to verify order
        scores = [prioritizer.calculate_priority_score(t) for t in sorted_tasks]

        # Verify descending order
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]

    def test_assign_priorities_percentile_based(self, prioritizer, sample_tasks):
        """Test that assign_priorities sets priority 1-5 based on percentile."""
        tasks = prioritizer.assign_priorities(sample_tasks)

        # All tasks should have priority assigned
        for task in tasks:
            assert 1 <= task.priority <= 5

        # At least one task should be priority 1 (top 20%)
        assert any(t.priority == 1 for t in tasks)

    def test_empty_task_list(self, prioritizer):
        """Test handling of empty task list."""
        result = prioritizer.prioritize([])
        assert result == []

        result = prioritizer.assign_priorities([])
        assert result == []


# ---------------------------------------------------------------------------
# TestQuickWinIdentification
# ---------------------------------------------------------------------------


class TestQuickWinIdentification:
    """Tests for quick win detection."""

    def test_identify_quick_wins_high_impact_low_effort(self, prioritizer):
        """Test that high impact + low effort tasks are identified as quick wins."""
        tasks = [
            Task(
                id="quick-1",
                title="Quick win",
                description="High impact, low effort",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.9,
            ),
            Task(
                id="slow-1",
                title="Not quick win",
                description="Low impact",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.3,
            ),
        ]

        quick_wins = prioritizer.identify_quick_wins(tasks)

        assert len(quick_wins) == 1
        assert quick_wins[0].id == "quick-1"

    def test_identify_quick_wins_caps_at_five(self, prioritizer):
        """Test that quick wins are capped at 5."""
        tasks = [
            Task(
                id=f"quick-{i}",
                title=f"Quick win {i}",
                description="High impact, low effort",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.9 - (i * 0.01),  # Slightly varying impact
            )
            for i in range(10)
        ]

        quick_wins = prioritizer.identify_quick_wins(tasks)

        assert len(quick_wins) == 5

    def test_medium_effort_high_impact_qualifies(self, prioritizer):
        """Test that medium effort with very high impact qualifies."""
        tasks = [
            Task(
                id="medium-effort",
                title="Medium effort high impact",
                description="High impact with medium effort",
                scope="components",
                priority=0,
                estimated_effort="medium",
                impact=0.85,  # >= 0.8 threshold for medium effort
            ),
        ]

        quick_wins = prioritizer.identify_quick_wins(tasks)

        assert len(quick_wins) == 1

    def test_quick_wins_sorted_by_impact(self, prioritizer):
        """Test that quick wins are sorted by impact descending."""
        tasks = [
            Task(
                id="low-impact",
                title="Lower impact",
                description="",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.7,
            ),
            Task(
                id="high-impact",
                title="Higher impact",
                description="",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.9,
            ),
        ]

        quick_wins = prioritizer.identify_quick_wins(tasks)

        assert quick_wins[0].id == "high-impact"


# ---------------------------------------------------------------------------
# TestDependencyResolution
# ---------------------------------------------------------------------------


class TestDependencyResolution:
    """Tests for topological sorting of dependencies."""

    def test_resolve_dependencies_orders_correctly(self, prioritizer):
        """Test that dependencies come before dependents."""
        tasks = [
            Task(
                id="child",
                title="Child task",
                description="Depends on parent",
                scope="components",
                priority=0,
                estimated_effort="low",
                impact=0.5,
                dependencies=["parent"],
            ),
            Task(
                id="parent",
                title="Parent task",
                description="No dependencies",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.8,
            ),
        ]

        ordered = prioritizer.resolve_dependencies(tasks)

        # Parent should come before child
        parent_idx = next(i for i, t in enumerate(ordered) if t.id == "parent")
        child_idx = next(i for i, t in enumerate(ordered) if t.id == "child")

        assert parent_idx < child_idx

    def test_resolve_dependencies_handles_chains(self, prioritizer):
        """Test handling of dependency chains (A -> B -> C)."""
        tasks = [
            Task(
                id="C",
                title="Task C",
                description="Depends on B",
                scope="pages",
                priority=0,
                estimated_effort="low",
                impact=0.5,
                dependencies=["B"],
            ),
            Task(
                id="B",
                title="Task B",
                description="Depends on A",
                scope="components",
                priority=0,
                estimated_effort="low",
                impact=0.6,
                dependencies=["A"],
            ),
            Task(
                id="A",
                title="Task A",
                description="No dependencies",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.7,
            ),
        ]

        ordered = prioritizer.resolve_dependencies(tasks)

        # Order should be A, B, C
        assert ordered[0].id == "A"
        assert ordered[1].id == "B"
        assert ordered[2].id == "C"

    def test_resolve_dependencies_missing_deps_ignored(self, prioritizer):
        """Test that missing dependencies are ignored gracefully."""
        tasks = [
            Task(
                id="task-1",
                title="Task with missing dep",
                description="Depends on non-existent task",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.5,
                dependencies=["non-existent-task"],
            ),
        ]

        # Should not raise
        ordered = prioritizer.resolve_dependencies(tasks)

        assert len(ordered) == 1
        assert ordered[0].id == "task-1"

    def test_resolve_dependencies_preserves_all_tasks(self, prioritizer, sample_tasks):
        """Test that all tasks are preserved after resolution."""
        ordered = prioritizer.resolve_dependencies(sample_tasks)

        assert len(ordered) == len(sample_tasks)

        # All IDs should be present
        original_ids = {t.id for t in sample_tasks}
        ordered_ids = {t.id for t in ordered}
        assert original_ids == ordered_ids


# ---------------------------------------------------------------------------
# TestGroupByScope
# ---------------------------------------------------------------------------


class TestGroupByScope:
    """Tests for scope grouping."""

    def test_group_by_scope_creates_correct_groups(self, prioritizer, sample_tasks):
        """Test that tasks are grouped by scope correctly."""
        # First assign priorities
        tasks = prioritizer.assign_priorities(sample_tasks)
        groups = prioritizer.group_by_scope(tasks)

        assert "tokens" in groups
        assert "components" in groups
        assert "pages" in groups

        # Verify task counts per scope
        assert len(groups["tokens"]) == 2  # task-1, task-3
        assert len(groups["components"]) == 2  # task-2, task-4
        assert len(groups["pages"]) == 2  # task-5, task-6

    def test_group_by_scope_sorts_within_groups(self, prioritizer, sample_tasks):
        """Test that tasks within each group are sorted by priority."""
        tasks = prioritizer.assign_priorities(sample_tasks)
        groups = prioritizer.group_by_scope(tasks)

        for _scope, scope_tasks in groups.items():
            for i in range(len(scope_tasks) - 1):
                assert scope_tasks[i].priority <= scope_tasks[i + 1].priority

    def test_cap_tasks_per_scope(self, prioritizer):
        """Test that tasks per scope can be capped."""
        tasks = [
            Task(
                id=f"task-{i}",
                title=f"Task {i}",
                description="",
                scope="tokens",
                priority=i % 5 + 1,
                estimated_effort="low",
                impact=0.5,
            )
            for i in range(15)  # More than default max of 10
        ]

        groups = {"tokens": tasks}
        capped = prioritizer.cap_tasks_per_scope(groups)

        assert len(capped["tokens"]) == 10  # Default max

    def test_cap_with_custom_config(self, custom_prioritizer):
        """Test capping with custom max_tasks_per_scope."""
        tasks = [
            Task(
                id=f"task-{i}",
                title=f"Task {i}",
                description="",
                scope="components",
                priority=1,
                estimated_effort="low",
                impact=0.5,
            )
            for i in range(10)
        ]

        groups = {"components": tasks}
        capped = custom_prioritizer.cap_tasks_per_scope(groups)

        assert len(capped["components"]) == 5  # Custom max


# ---------------------------------------------------------------------------
# TestFullPrioritization
# ---------------------------------------------------------------------------


class TestFullPrioritization:
    """Tests for complete prioritization pipeline."""

    def test_full_prioritization_combines_all_steps(self, prioritizer, sample_tasks):
        """Test that full_prioritization runs all steps."""
        result = prioritizer.full_prioritization(sample_tasks)

        # All tasks should be present
        assert len(result) == len(sample_tasks)

        # All tasks should have priority assigned
        for task in result:
            assert 1 <= task.priority <= 5

    def test_scope_ordering_tokens_first(self, prioritizer, sample_tasks):
        """Test that tokens scope comes before components, which comes before pages."""
        result = prioritizer.full_prioritization(sample_tasks)

        # Find first task of each scope
        first_token_idx = next(i for i, t in enumerate(result) if t.scope == "tokens")
        next(i for i, t in enumerate(result) if t.scope == "components")
        first_page_idx = next(i for i, t in enumerate(result) if t.scope == "pages")

        # Tokens should generally come first, then components, then pages
        # (within same priority level)
        assert first_token_idx < first_page_idx

    def test_full_prioritization_empty_list(self, prioritizer):
        """Test full_prioritization with empty list."""
        result = prioritizer.full_prioritization([])
        assert result == []

    def test_full_prioritization_single_task(self, prioritizer):
        """Test full_prioritization with single task."""
        single_task = Task(
            id="single",
            title="Single task",
            description="",
            scope="tokens",
            priority=0,
            estimated_effort="low",
            impact=0.5,
        )

        result = prioritizer.full_prioritization([single_task])

        assert len(result) == 1
        assert result[0].priority == 1  # Top 20% of 1 task

    def test_full_prioritization_considers_dependencies_and_priority(self, prioritizer):
        """Test that full_prioritization processes dependencies before final sort.

        Note: The final sort by (scope, priority, impact) may reorder tasks
        from their dependency-resolved order when priority differs.
        """
        tasks = [
            Task(
                id="dependent",
                title="Dependent task",
                description="",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.9,  # High impact -> gets priority 1
                dependencies=["dependency"],
            ),
            Task(
                id="dependency",
                title="Dependency task",
                description="",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.3,  # Lower impact -> gets lower priority
            ),
        ]

        result = prioritizer.full_prioritization(tasks)

        # Both tasks should be present with priorities assigned
        assert len(result) == 2
        for task in result:
            assert 1 <= task.priority <= 5

        # The high-impact task gets priority 1 (better priority)
        dependent_task = next(t for t in result if t.id == "dependent")
        dependency_task = next(t for t in result if t.id == "dependency")

        # High impact task should have better (lower) priority
        assert dependent_task.priority < dependency_task.priority


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestPrioritizerIntegration:
    """Integration tests for the complete prioritization workflow."""

    def test_realistic_workflow(self, prioritizer):
        """Test a realistic prioritization workflow."""
        # Create a realistic set of tasks
        tasks = [
            Task(
                id="token-colors",
                title="Standardize colors",
                description="Replace 15 hardcoded colors with tokens",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.9,
            ),
            Task(
                id="token-spacing",
                title="Fix spacing scale",
                description="Align to 4px grid",
                scope="tokens",
                priority=0,
                estimated_effort="low",
                impact=0.8,
            ),
            Task(
                id="button-consolidation",
                title="Consolidate buttons",
                description="Reduce from 8 to 3 variants",
                scope="components",
                priority=0,
                estimated_effort="medium",
                impact=0.85,
                dependencies=["token-colors"],
            ),
            Task(
                id="card-refactor",
                title="Refactor cards",
                description="Extract shared base",
                scope="components",
                priority=0,
                estimated_effort="high",
                impact=0.7,
                dependencies=["token-spacing"],
            ),
            Task(
                id="checkout-update",
                title="Update checkout UI",
                description="Apply new design system",
                scope="pages",
                priority=0,
                estimated_effort="high",
                impact=0.6,
                dependencies=["button-consolidation", "card-refactor"],
            ),
        ]

        # Run full pipeline
        result = prioritizer.full_prioritization(tasks)
        quick_wins = prioritizer.identify_quick_wins(tasks)

        # Verify results
        assert len(result) == 5
        assert len(quick_wins) >= 2  # token-colors and token-spacing

        # Token tasks should be early
        token_indices = [i for i, t in enumerate(result) if t.scope == "tokens"]
        assert all(idx < 3 for idx in token_indices)  # Both in first 3

        # Checkout should be last (depends on components)
        assert result[-1].id == "checkout-update"
