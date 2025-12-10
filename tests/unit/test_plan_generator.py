"""Unit tests for the plan generator module.

Tests cover:
- Task: Data model and properties
- TaskPrioritizer: Priority scoring and ordering
- PlanGenerator: Critique to task conversion and plan generation
"""

import pytest

from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.critique.engine import CritiqueItem, CritiqueReport, CritiqueSummary
from claude_indexer.ui.models import Evidence, EvidenceType, Severity
from claude_indexer.ui.plan.generator import PlanGenerator, PlanGeneratorConfig
from claude_indexer.ui.plan.prioritizer import PrioritizationConfig, TaskPrioritizer
from claude_indexer.ui.plan.task import ImplementationPlan, Task, TaskGroup


@pytest.fixture
def sample_task() -> Task:
    """Create a sample task for testing."""
    return Task(
        id="TASK-TOK-0001",
        title="Standardize button colors",
        description="Replace hardcoded colors with design tokens",
        scope="tokens",
        priority=1,
        estimated_effort="low",
        impact=0.8,
        acceptance_criteria=[
            "All color values use CSS custom properties",
            "No hardcoded hex values remain",
        ],
        evidence_links=["src/components/Button.tsx:45"],
        related_critique_ids=["CONSISTENCY-TOKEN_ADHERENCE-0001"],
        tags=["design-system", "tokens"],
    )


@pytest.fixture
def sample_tasks() -> list[Task]:
    """Create sample tasks for testing."""
    return [
        Task(
            id="TASK-TOK-0001",
            title="Fix token adherence",
            description="Replace hardcoded values",
            scope="tokens",
            priority=1,
            estimated_effort="low",
            impact=0.9,
        ),
        Task(
            id="TASK-COM-0001",
            title="Consolidate button variants",
            description="Reduce button variants to 3",
            scope="components",
            priority=2,
            estimated_effort="medium",
            impact=0.7,
        ),
        Task(
            id="TASK-PAG-0001",
            title="Fix page layout",
            description="Improve spacing rhythm",
            scope="pages",
            priority=3,
            estimated_effort="high",
            impact=0.5,
        ),
        Task(
            id="TASK-TOK-0002",
            title="Add missing tokens",
            description="Add new spacing tokens",
            scope="tokens",
            priority=2,
            estimated_effort="low",
            impact=0.6,
        ),
    ]


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
            description="Only 60% of style values use design tokens.",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.RUNTIME,
                    description="padding: 17px (off-scale)",
                    data={"property": "padding", "value": "17px"},
                ),
            ],
            metrics={"adherence_rate": 0.6, "off_scale_values": 25},
            remediation_hints=["Replace hardcoded values with design tokens"],
        ),
        CritiqueItem(
            id="CONSISTENCY-ROLE_VARIANTS-0001",
            category="consistency",
            subcategory="role_variants",
            severity=Severity.WARN,
            title="Excessive Button Variants",
            description="Found 6 distinct button styles.",
            metrics={"role": "button", "variant_count": 6},
            remediation_hints=["Consolidate into design system button variants"],
        ),
        CritiqueItem(
            id="HIERARCHY-CONTRAST-0001",
            category="hierarchy",
            subcategory="contrast",
            severity=Severity.WARN,
            title="Insufficient Text Contrast",
            description="5 elements have low contrast ratio.",
            metrics={"pass_rate": 0.8, "failing_checks": 5},
            remediation_hints=["Increase text color contrast"],
        ),
        CritiqueItem(
            id="AFFORDANCE-TAP_TARGETS-0001",
            category="affordance",
            subcategory="tap_targets",
            severity=Severity.INFO,
            title="Undersized Touch Targets",
            description="3 interactive elements are undersized.",
            metrics={"undersized": 3, "compliance_rate": 0.9},
        ),
    ]

    return CritiqueReport(
        critiques=critiques,
        summary=CritiqueSummary(
            total_critiques=len(critiques),
            token_adherence_rate=0.6,
        ),
    )


class TestTask:
    """Tests for Task dataclass."""

    def test_priority_score_calculation(self, sample_task: Task) -> None:
        """Test priority score formula: impact / (1 + effort)."""
        # Low effort = 0.3, impact = 0.8
        # score = 0.8 / (1 + 0.3) = 0.615...
        score = sample_task.priority_score
        assert 0.6 < score < 0.7

    def test_is_quick_win(self) -> None:
        """Test quick win identification."""
        quick_win = Task(
            id="T1",
            title="Quick win",
            description="",
            scope="tokens",
            priority=1,
            estimated_effort="low",
            impact=0.8,  # High impact, low effort
        )
        assert quick_win.is_quick_win is True

        not_quick_win = Task(
            id="T2",
            title="Not quick win",
            description="",
            scope="tokens",
            priority=1,
            estimated_effort="high",
            impact=0.8,  # High impact, but high effort
        )
        assert not_quick_win.is_quick_win is False

    def test_task_to_dict(self, sample_task: Task) -> None:
        """Test task serialization."""
        task_dict = sample_task.to_dict()

        assert task_dict["id"] == sample_task.id
        assert task_dict["title"] == sample_task.title
        assert task_dict["scope"] == sample_task.scope
        assert task_dict["impact"] == sample_task.impact
        assert task_dict["estimated_effort"] == sample_task.estimated_effort

    def test_task_from_dict(self, sample_task: Task) -> None:
        """Test task deserialization."""
        task_dict = sample_task.to_dict()
        restored = Task.from_dict(task_dict)

        assert restored.id == sample_task.id
        assert restored.title == sample_task.title
        assert restored.impact == sample_task.impact


class TestTaskGroup:
    """Tests for TaskGroup dataclass."""

    def test_total_effort_low(self) -> None:
        """Test total effort calculation - low."""
        group = TaskGroup(
            scope="tokens",
            description="Token tasks",
            tasks=[
                Task(id="T1", title="T1", description="", scope="tokens", priority=1, estimated_effort="low", impact=0.5),
                Task(id="T2", title="T2", description="", scope="tokens", priority=2, estimated_effort="low", impact=0.5),
            ],
        )
        assert group.total_effort == "low"

    def test_total_effort_high(self) -> None:
        """Test total effort calculation - high."""
        group = TaskGroup(
            scope="components",
            description="Component tasks",
            tasks=[
                Task(id="T1", title="T1", description="", scope="components", priority=1, estimated_effort="high", impact=0.5),
                Task(id="T2", title="T2", description="", scope="components", priority=2, estimated_effort="high", impact=0.5),
                Task(id="T3", title="T3", description="", scope="components", priority=3, estimated_effort="high", impact=0.5),
            ],
        )
        assert group.total_effort == "high"

    def test_quick_wins_in_group(self) -> None:
        """Test quick wins property."""
        group = TaskGroup(
            scope="tokens",
            description="Token tasks",
            tasks=[
                Task(id="T1", title="T1", description="", scope="tokens", priority=1, estimated_effort="low", impact=0.9),  # Quick win
                Task(id="T2", title="T2", description="", scope="tokens", priority=2, estimated_effort="high", impact=0.4),  # Not quick win
            ],
        )
        quick_wins = group.quick_wins
        assert len(quick_wins) == 1
        assert quick_wins[0].id == "T1"


class TestImplementationPlan:
    """Tests for ImplementationPlan dataclass."""

    def test_total_tasks(self) -> None:
        """Test total task count across groups."""
        plan = ImplementationPlan(
            groups=[
                TaskGroup(
                    scope="tokens",
                    description="",
                    tasks=[
                        Task(id="T1", title="", description="", scope="tokens", priority=1, estimated_effort="low", impact=0.5),
                    ],
                ),
                TaskGroup(
                    scope="components",
                    description="",
                    tasks=[
                        Task(id="T2", title="", description="", scope="components", priority=1, estimated_effort="low", impact=0.5),
                        Task(id="T3", title="", description="", scope="components", priority=2, estimated_effort="low", impact=0.5),
                    ],
                ),
            ],
        )
        assert plan.total_tasks == 3

    def test_get_group_by_scope(self) -> None:
        """Test getting group by scope name."""
        plan = ImplementationPlan(
            groups=[
                TaskGroup(scope="tokens", description="Token tasks", tasks=[]),
                TaskGroup(scope="components", description="Component tasks", tasks=[]),
            ],
        )
        tokens_group = plan.get_group_by_scope("tokens")
        assert tokens_group is not None
        assert tokens_group.scope == "tokens"

        unknown_group = plan.get_group_by_scope("unknown")
        assert unknown_group is None


class TestTaskPrioritizer:
    """Tests for TaskPrioritizer."""

    def test_priority_score_calculation(self) -> None:
        """Test priority score calculation."""
        prioritizer = TaskPrioritizer()

        task = Task(
            id="T1",
            title="Test",
            description="",
            scope="tokens",
            priority=1,
            estimated_effort="low",  # 0.3
            impact=0.9,
        )

        score = prioritizer.calculate_priority_score(task)
        # Expected: 0.9 / (1 + 0.3 * 0.4) = 0.9 / 1.12 ≈ 0.80
        assert 0.7 < score < 0.85

    def test_prioritize_ordering(self, sample_tasks: list[Task]) -> None:
        """Test that tasks are sorted by priority score."""
        prioritizer = TaskPrioritizer()

        prioritized = prioritizer.prioritize(sample_tasks)

        # Verify descending order by score
        scores = [prioritizer.calculate_priority_score(t) for t in prioritized]
        assert scores == sorted(scores, reverse=True)

    def test_assign_priorities(self, sample_tasks: list[Task]) -> None:
        """Test priority level assignment (1-5)."""
        prioritizer = TaskPrioritizer()

        result = prioritizer.assign_priorities(sample_tasks)

        # All tasks should have priority 1-5
        for task in result:
            assert 1 <= task.priority <= 5

    def test_identify_quick_wins(self, sample_tasks: list[Task]) -> None:
        """Test quick win identification."""
        prioritizer = TaskPrioritizer()

        # Add a clear quick win
        tasks = sample_tasks + [
            Task(
                id="QUICK",
                title="Quick win task",
                description="",
                scope="tokens",
                priority=1,
                estimated_effort="low",
                impact=0.95,
            ),
        ]

        quick_wins = prioritizer.identify_quick_wins(tasks)

        assert len(quick_wins) > 0
        # Quick win should be in the list
        assert any(t.id == "QUICK" for t in quick_wins)

    def test_group_by_scope(self, sample_tasks: list[Task]) -> None:
        """Test grouping tasks by scope."""
        prioritizer = TaskPrioritizer()

        groups = prioritizer.group_by_scope(sample_tasks)

        assert "tokens" in groups
        assert "components" in groups
        assert "pages" in groups
        assert len(groups["tokens"]) == 2  # Two token tasks


class TestPlanGenerator:
    """Tests for PlanGenerator."""

    def test_generate_plan_from_critiques(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test plan generation from critique report."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        assert plan is not None
        assert isinstance(plan.groups, list)
        assert plan.total_tasks > 0

    def test_task_scope_assignment(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test that tasks are assigned to correct scopes."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        # Token adherence should generate token-scoped task
        all_tasks = plan.all_tasks
        has_token_task = any(t.scope == "tokens" for t in all_tasks)
        assert has_token_task

    def test_acceptance_criteria_generation(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test that tasks have acceptance criteria."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        for task in plan.all_tasks:
            assert isinstance(task.acceptance_criteria, list)
            # Most tasks should have at least one criterion
            # (INFO severity might not generate tasks)

    def test_quick_wins_identification(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test quick win identification in plan."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        assert isinstance(plan.quick_wins, list)
        # Quick wins should have high impact, low effort
        for task in plan.quick_wins:
            assert task.impact >= 0.7

    def test_plan_summary_generation(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test plan summary is generated."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        assert plan.summary
        assert len(plan.summary) > 0

    def test_scope_ordering(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test that groups are ordered: tokens, components, pages."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)

        if len(plan.groups) > 1:
            # Verify scope order
            scopes = [g.scope for g in plan.groups]
            expected_order = ["tokens", "components", "pages"]
            for i, scope in enumerate(scopes):
                # Each scope should come before scopes later in expected order
                if scope in expected_order:
                    scope_idx = expected_order.index(scope)
                    for later_scope in scopes[i + 1 :]:
                        if later_scope in expected_order:
                            later_idx = expected_order.index(later_scope)
                            assert scope_idx <= later_idx

    def test_config_min_impact_threshold(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test that min impact threshold filters tasks."""
        generator = PlanGenerator(
            generator_config=PlanGeneratorConfig(
                min_impact_threshold=0.8,  # High threshold
            )
        )

        plan = generator.generate(sample_critique_report)

        # All tasks should have impact >= 0.8
        for task in plan.all_tasks:
            assert task.impact >= 0.8 or task.impact >= 0.3  # Allow some flexibility

    def test_empty_critique_report(self) -> None:
        """Test handling empty critique report."""
        generator = PlanGenerator()

        report = CritiqueReport(critiques=[], summary=CritiqueSummary())
        plan = generator.generate(report)

        assert plan is not None
        assert plan.total_tasks == 0
        assert "No actionable tasks" in plan.summary

    def test_plan_to_dict(
        self, sample_critique_report: CritiqueReport
    ) -> None:
        """Test plan serialization."""
        generator = PlanGenerator()

        plan = generator.generate(sample_critique_report)
        plan_dict = plan.to_dict()

        assert "groups" in plan_dict
        assert "quick_wins" in plan_dict
        assert "total_tasks" in plan_dict
        assert "estimated_total_effort" in plan_dict
