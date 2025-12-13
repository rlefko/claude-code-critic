"""Plan generator for creating implementation plans from critiques.

Converts critique reports into actionable implementation plans
with tasks grouped by scope and prioritized by impact/effort.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ci.audit_runner import CIAuditResult
    from ..ci.cross_file_analyzer import CrossFileClusterResult
    from ..config import UIQualityConfig
    from ..critique.engine import CritiqueItem, CritiqueReport

from ..models import Severity
from .prioritizer import PrioritizationConfig, TaskPrioritizer
from .task import ImplementationPlan, Task, TaskGroup


@dataclass
class PlanGeneratorConfig:
    """Configuration for plan generation."""

    max_tasks_per_scope: int = 10
    min_impact_threshold: float = 0.3  # Skip tasks below this impact
    include_info_severity: bool = False  # Include INFO severity as tasks
    group_related_tasks: bool = True


class PlanGenerator:
    """Generates implementation plans from critique reports.

    Converts critiques into tasks, groups by scope, prioritizes
    by impact/effort, and generates acceptance criteria.
    """

    # Scope order (tokens first as they're foundational)
    SCOPE_ORDER = ["tokens", "components", "pages"]

    # Scope descriptions
    SCOPE_DESCRIPTIONS = {
        "tokens": "Design token updates and standardization",
        "components": "Component consolidation and consistency improvements",
        "pages": "Page-level layout and structure refinements",
    }

    # Critique subcategory to scope mapping
    SUBCATEGORY_TO_SCOPE = {
        "token_adherence": "tokens",
        "role_variants": "components",
        "outlier": "components",
        "heading_scale": "tokens",
        "contrast": "tokens",
        "spacing_rhythm": "tokens",
        "focus_visibility": "components",
        "focus_consistency": "components",
        "tap_targets": "components",
        "form_labels": "pages",
        "feedback_states": "components",
        "static_analysis": "components",
    }

    # Effort estimation based on subcategory
    SUBCATEGORY_EFFORT = {
        "token_adherence": "low",  # Usually just replacing values
        "role_variants": "medium",  # Component refactoring
        "outlier": "low",  # Single value fix
        "heading_scale": "low",  # Token updates
        "contrast": "low",  # Color changes
        "spacing_rhythm": "low",  # Spacing updates
        "focus_visibility": "medium",  # Need to add focus styles
        "focus_consistency": "low",  # Standardizing existing styles
        "tap_targets": "medium",  # Layout changes
        "form_labels": "medium",  # Adding labels/ARIA
        "feedback_states": "high",  # Adding new states
        "static_analysis": "medium",
    }

    def __init__(
        self,
        config: "UIQualityConfig | None" = None,
        generator_config: PlanGeneratorConfig | None = None,
    ):
        """Initialize the plan generator.

        Args:
            config: UI quality configuration.
            generator_config: Plan generation configuration.
        """
        self.config = config
        self.generator_config = generator_config or PlanGeneratorConfig()
        self.prioritizer = TaskPrioritizer(
            PrioritizationConfig(
                max_tasks_per_scope=self.generator_config.max_tasks_per_scope
            )
        )
        self._task_counter = 0

    def _generate_task_id(self, scope: str) -> str:
        """Generate unique task ID."""
        self._task_counter += 1
        return f"TASK-{scope.upper()[:3]}-{self._task_counter:04d}"

    def _critique_to_task(self, critique: "CritiqueItem") -> Task | None:
        """Convert a critique to a task.

        Args:
            critique: Critique item to convert.

        Returns:
            Task if conversion successful, None otherwise.
        """
        # Determine scope
        scope = self.SUBCATEGORY_TO_SCOPE.get(critique.subcategory, "components")

        # Determine effort
        effort = self.SUBCATEGORY_EFFORT.get(critique.subcategory, "medium")

        # Determine impact from severity and metrics
        impact = self._calculate_impact(critique)

        # Skip low-impact tasks if below threshold
        if impact < self.generator_config.min_impact_threshold:
            return None

        # Skip INFO severity unless configured to include
        if (
            critique.severity == Severity.INFO
            and not self.generator_config.include_info_severity
        ):
            return None

        # Generate acceptance criteria
        acceptance_criteria = self._generate_acceptance_criteria(critique)

        # Collect evidence links
        evidence_links = []
        for ev in critique.evidence:
            if ev.source_ref:
                evidence_links.append(str(ev.source_ref))
        evidence_links.extend(critique.screenshots[:3])

        # Generate task title
        title = self._generate_task_title(critique)

        # Generate description
        description = self._generate_task_description(critique)

        return Task(
            id=self._generate_task_id(scope),
            title=title,
            description=description,
            scope=scope,
            priority=3,  # Will be updated by prioritizer
            estimated_effort=effort,
            impact=impact,
            acceptance_criteria=acceptance_criteria,
            evidence_links=evidence_links,
            related_critique_ids=[critique.id],
            tags=self._generate_tags(critique),
        )

    def _calculate_impact(self, critique: "CritiqueItem") -> float:
        """Calculate task impact from critique.

        Args:
            critique: Critique item.

        Returns:
            Impact score 0.0-1.0.
        """
        # Base impact from severity
        severity_impact = {
            Severity.FAIL: 0.9,
            Severity.WARN: 0.6,
            Severity.INFO: 0.3,
        }
        base_impact = severity_impact.get(critique.severity, 0.5)

        # Adjust based on metrics
        metrics = critique.metrics
        if "adherence_rate" in metrics:
            # Lower adherence = higher impact
            adherence = metrics["adherence_rate"]
            base_impact = max(base_impact, 1.0 - adherence)
        if "variant_count" in metrics:
            # More variants = higher impact
            variants = metrics["variant_count"]
            if variants > 5:
                base_impact = max(base_impact, 0.8)
            elif variants > 3:
                base_impact = max(base_impact, 0.6)
        if "pass_rate" in metrics:
            # Lower pass rate = higher impact
            pass_rate = metrics["pass_rate"]
            base_impact = max(base_impact, 1.0 - pass_rate)

        return min(1.0, base_impact)

    def _generate_task_title(self, critique: "CritiqueItem") -> str:
        """Generate concise task title.

        Args:
            critique: Critique item.

        Returns:
            Task title string.
        """
        subcategory_titles = {
            "token_adherence": "Standardize design token usage",
            "role_variants": f"Consolidate {critique.title.split()[0].lower()} variants",
            "outlier": f"Fix style outlier: {critique.metrics.get('property_name', 'unknown')}",
            "heading_scale": "Standardize heading typography scale",
            "contrast": "Improve text contrast ratios",
            "spacing_rhythm": "Align spacing to design scale",
            "focus_visibility": "Add visible focus indicators",
            "focus_consistency": "Standardize focus ring styles",
            "tap_targets": "Increase tap target sizes",
            "form_labels": "Add proper form labels",
            "feedback_states": "Add component feedback states",
        }
        return subcategory_titles.get(critique.subcategory, critique.title)

    def _generate_task_description(self, critique: "CritiqueItem") -> str:
        """Generate task description with context.

        Args:
            critique: Critique item.

        Returns:
            Task description string.
        """
        # Start with critique description
        description = critique.description

        # Add remediation hints
        if critique.remediation_hints:
            description += "\n\nRecommended approach:\n"
            for hint in critique.remediation_hints[:3]:
                description += f"- {hint}\n"

        return description

    def _generate_acceptance_criteria(self, critique: "CritiqueItem") -> list[str]:
        """Generate testable acceptance criteria.

        Args:
            critique: Critique item.

        Returns:
            List of acceptance criteria strings.
        """
        criteria: list[str] = []
        metrics = critique.metrics

        subcategory = critique.subcategory

        if subcategory == "token_adherence":
            criteria.append(
                "All color values use CSS custom properties from design tokens"
            )
            criteria.append(
                "All spacing values are from the spacing scale (4, 8, 12, 16, 24...)"
            )
            if "adherence_rate" in metrics:
                target = min(0.95, metrics["adherence_rate"] + 0.15)
                criteria.append(f"Token adherence rate reaches {target:.0%} or higher")

        elif subcategory == "role_variants":
            role = metrics.get("role", "element")
            criteria.append(f"All {role}s use shared component with variant prop")
            criteria.append("Maximum 3 intentional variants documented")
            criteria.append("Visual regression tests pass")

        elif subcategory == "outlier":
            prop = metrics.get("property_name", "property")
            majority = metrics.get("majority_value", "standard")
            criteria.append(f"All elements use {prop}: {majority}")
            criteria.append("Intentional exceptions documented in code comments")

        elif subcategory == "heading_scale":
            criteria.append("Heading sizes follow consistent scale ratio (1.2-1.3)")
            criteria.append("All heading sizes defined in design tokens")
            criteria.append("Typography scale documented")

        elif subcategory == "contrast":
            criteria.append("All text meets WCAG 2.1 AA contrast ratio (4.5:1)")
            criteria.append("Large text meets 3:1 minimum contrast")
            criteria.append("WebAIM contrast checker passes")

        elif subcategory == "spacing_rhythm":
            criteria.append("All spacing values are multiples of 4px")
            criteria.append("Custom spacing values added to scale if intentional")

        elif subcategory == "focus_visibility":
            criteria.append("All interactive elements have visible focus indicator")
            criteria.append("Focus ring has 3:1 contrast ratio against background")
            criteria.append("Keyboard navigation test passes")

        elif subcategory == "tap_targets":
            criteria.append("All interactive elements are minimum 44x44px")
            criteria.append("Touch target test passes on mobile viewport")

        elif subcategory == "form_labels":
            criteria.append("All form inputs have associated <label> elements")
            criteria.append("Labels use for attribute or wrap inputs")
            criteria.append("Accessibility audit passes")

        elif subcategory == "feedback_states":
            criteria.append("Loading state shows spinner or skeleton")
            criteria.append("Disabled state has reduced opacity and cursor:not-allowed")
            criteria.append("Error state has visible error styling and message")

        else:
            criteria.append("Issue resolved per critique description")
            criteria.append("Visual regression tests pass")

        return criteria

    def _generate_tags(self, critique: "CritiqueItem") -> list[str]:
        """Generate tags for task categorization.

        Args:
            critique: Critique item.

        Returns:
            List of tag strings.
        """
        tags = [critique.category, critique.subcategory]

        if critique.severity == Severity.FAIL:
            tags.append("blocking")
        if critique.severity == Severity.WARN:
            tags.append("important")

        # Add specific tags based on subcategory
        if critique.subcategory in [
            "contrast",
            "focus_visibility",
            "tap_targets",
            "form_labels",
        ]:
            tags.append("accessibility")
        if critique.subcategory in [
            "token_adherence",
            "heading_scale",
            "spacing_rhythm",
        ]:
            tags.append("design-system")
        if critique.subcategory in ["role_variants", "outlier"]:
            tags.append("consistency")

        return tags

    def _group_related_tasks(self, tasks: list[Task]) -> list[Task]:
        """Merge related tasks to avoid duplication.

        Args:
            tasks: List of tasks.

        Returns:
            Consolidated task list.
        """
        if not self.generator_config.group_related_tasks:
            return tasks

        # Group by (scope, subcategory-prefix)
        grouped: dict[str, list[Task]] = {}
        for task in tasks:
            # Extract subcategory from tags
            subcategory = next(
                (
                    t
                    for t in task.tags
                    if t
                    not in [
                        "blocking",
                        "important",
                        "accessibility",
                        "design-system",
                        "consistency",
                    ]
                ),
                "general",
            )
            key = f"{task.scope}:{subcategory}"
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(task)

        # Merge groups with >1 task
        result: list[Task] = []
        for _key, group_tasks in grouped.items():
            if len(group_tasks) == 1:
                result.append(group_tasks[0])
            else:
                # Merge into single task
                merged = self._merge_tasks(group_tasks)
                result.append(merged)

        return result

    def _merge_tasks(self, tasks: list[Task]) -> Task:
        """Merge multiple related tasks into one.

        Args:
            tasks: List of related tasks.

        Returns:
            Single merged task.
        """
        if len(tasks) == 1:
            return tasks[0]

        # Use highest impact task as base
        tasks.sort(key=lambda t: t.impact, reverse=True)
        base = tasks[0]

        # Merge evidence and criteria from others
        all_evidence = set(base.evidence_links)
        all_criteria = set(base.acceptance_criteria)
        all_critique_ids = set(base.related_critique_ids)

        for task in tasks[1:]:
            all_evidence.update(task.evidence_links)
            all_criteria.update(task.acceptance_criteria)
            all_critique_ids.update(task.related_critique_ids)

        # Update title to indicate multiple items
        title = f"{base.title} ({len(tasks)} related issues)"

        # Recalculate effort (more items = higher effort)
        effort = base.estimated_effort
        if len(tasks) > 3:
            effort = "high"
        elif len(tasks) > 1 and effort == "low":
            effort = "medium"

        return Task(
            id=base.id,
            title=title,
            description=base.description,
            scope=base.scope,
            priority=base.priority,
            estimated_effort=effort,
            impact=max(t.impact for t in tasks),  # Highest impact
            acceptance_criteria=list(all_criteria)[:5],
            evidence_links=list(all_evidence)[:10],
            related_critique_ids=list(all_critique_ids),
            tags=base.tags,
        )

    def _create_task_groups(self, tasks: list[Task]) -> list[TaskGroup]:
        """Create task groups from tasks.

        Args:
            tasks: Prioritized task list.

        Returns:
            List of TaskGroups ordered by scope.
        """
        # Group by scope
        grouped = self.prioritizer.group_by_scope(tasks)

        # Cap tasks per scope
        grouped = self.prioritizer.cap_tasks_per_scope(grouped)

        # Create TaskGroups in scope order
        groups: list[TaskGroup] = []
        for scope in self.SCOPE_ORDER:
            if scope in grouped and grouped[scope]:
                groups.append(
                    TaskGroup(
                        scope=scope,
                        description=self.SCOPE_DESCRIPTIONS.get(scope, ""),
                        tasks=grouped[scope],
                    )
                )

        return groups

    def _generate_summary(
        self,
        plan: ImplementationPlan,
        critique_report: "CritiqueReport | None" = None,
    ) -> str:
        """Generate plan summary.

        Args:
            plan: Generated plan.
            critique_report: Original critique report.

        Returns:
            Summary string.
        """
        summary_parts = []

        summary_parts.append(f"Implementation plan with {plan.total_tasks} tasks")
        summary_parts.append(f"across {len(plan.groups)} scope areas.")

        if plan.quick_wins:
            summary_parts.append(f"\n{len(plan.quick_wins)} quick wins identified.")

        summary_parts.append(
            f"\nEstimated total effort: {plan.estimated_total_effort}."
        )

        if critique_report and critique_report.fail_count > 0:
            summary_parts.append(
                f"\nAddresses {critique_report.fail_count} critical issues."
            )

        return " ".join(summary_parts)

    def generate(
        self,
        critique_report: "CritiqueReport",
        ci_result: "CIAuditResult | None" = None,
        cross_file_result: "CrossFileClusterResult | None" = None,
        focus_area: str | None = None,
    ) -> ImplementationPlan:
        """Generate implementation plan from critique report.

        Args:
            critique_report: Critique report with design issues.
            ci_result: Optional CI audit result for additional context.
            cross_file_result: Optional cross-file analysis for deduplication.
            focus_area: Optional focus area filter.

        Returns:
            ImplementationPlan with prioritized tasks.
        """
        self._task_counter = 0  # Reset counter

        # Convert critiques to tasks
        tasks: list[Task] = []
        for critique in critique_report.critiques:
            task = self._critique_to_task(critique)
            if task:
                tasks.append(task)

        if not tasks:
            return ImplementationPlan(
                summary="No actionable tasks identified.",
                focus_area=focus_area,
            )

        # Group related tasks
        tasks = self._group_related_tasks(tasks)

        # Prioritize tasks
        tasks = self.prioritizer.full_prioritization(tasks)

        # Identify quick wins
        quick_wins = self.prioritizer.identify_quick_wins(tasks)

        # Create task groups
        groups = self._create_task_groups(tasks)

        # Build plan
        plan = ImplementationPlan(
            groups=groups,
            quick_wins=quick_wins,
            focus_area=focus_area,
        )

        # Generate summary
        plan.summary = self._generate_summary(plan, critique_report)

        return plan


__all__ = [
    "PlanGenerator",
    "PlanGeneratorConfig",
]
