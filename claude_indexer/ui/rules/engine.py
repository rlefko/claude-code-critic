"""Rule engine for UI consistency checking.

This module provides the RuleEngine class that orchestrates rule
evaluation and manages rule registration.
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models import Finding, Severity, UIAnalysisResult
from .base import BaseRule, RuleContext, RuleResult

if TYPE_CHECKING:
    from ..config import UIQualityConfig


@dataclass
class RuleEngineConfig:
    """Configuration for the rule engine."""

    # Maximum time for a single rule in fast mode (ms)
    fast_rule_timeout_ms: float = 50.0
    # Whether to continue on rule errors
    continue_on_error: bool = True
    # Minimum confidence to include findings
    min_confidence: float = 0.7
    # Whether to require multi-evidence findings
    require_multi_evidence: bool = True


class RuleEngine:
    """Engine for running UI consistency rules.

    Manages rule registration, execution, and result aggregation.
    Supports both fast (pre-commit) and full (CI) evaluation modes.
    """

    def __init__(
        self,
        config: "UIQualityConfig",
        engine_config: RuleEngineConfig | None = None,
    ):
        """Initialize the rule engine.

        Args:
            config: UI quality configuration.
            engine_config: Optional engine-specific configuration.
        """
        self.config = config
        self.engine_config = engine_config or RuleEngineConfig(
            min_confidence=config.gating.min_confidence,
            require_multi_evidence=config.gating.require_multi_evidence,
        )
        self._rules: dict[str, BaseRule] = {}
        self._rules_by_category: dict[str, list[BaseRule]] = {}

    def register(self, rule: BaseRule) -> None:
        """Register a rule with the engine.

        Args:
            rule: Rule instance to register.

        Raises:
            ValueError: If a rule with the same ID is already registered.
        """
        if rule.rule_id in self._rules:
            raise ValueError(f"Rule {rule.rule_id} is already registered")

        self._rules[rule.rule_id] = rule

        # Index by category
        if rule.category not in self._rules_by_category:
            self._rules_by_category[rule.category] = []
        self._rules_by_category[rule.category].append(rule)

    def unregister(self, rule_id: str) -> None:
        """Unregister a rule by ID.

        Args:
            rule_id: ID of the rule to unregister.
        """
        if rule_id in self._rules:
            rule = self._rules[rule_id]
            del self._rules[rule_id]

            if rule.category in self._rules_by_category:
                self._rules_by_category[rule.category] = [
                    r
                    for r in self._rules_by_category[rule.category]
                    if r.rule_id != rule_id
                ]

    def get_rule(self, rule_id: str) -> BaseRule | None:
        """Get a rule by ID.

        Args:
            rule_id: ID of the rule to retrieve.

        Returns:
            Rule instance or None if not found.
        """
        return self._rules.get(rule_id)

    def get_rules_by_category(self, category: str) -> list[BaseRule]:
        """Get all rules in a category.

        Args:
            category: Rule category to filter by.

        Returns:
            List of rules in the category.
        """
        return self._rules_by_category.get(category, [])

    def get_fast_rules(self) -> list[BaseRule]:
        """Get rules suitable for pre-commit tier.

        Returns:
            List of rules where is_fast is True.
        """
        return [r for r in self._rules.values() if r.is_fast]

    def get_all_rules(self) -> list[BaseRule]:
        """Get all registered rules.

        Returns:
            List of all registered rules.
        """
        return list(self._rules.values())

    @property
    def rule_count(self) -> int:
        """Number of registered rules."""
        return len(self._rules)

    def run(
        self,
        context: RuleContext,
        rule_ids: list[str] | None = None,
    ) -> UIAnalysisResult:
        """Run rules and collect findings.

        Args:
            context: RuleContext containing evaluation data.
            rule_ids: Optional list of specific rule IDs to run.
                     If None, runs all registered rules.

        Returns:
            UIAnalysisResult with all findings.
        """
        start_time = time.time()

        # Determine which rules to run
        if rule_ids is not None:
            rules = [self._rules[rid] for rid in rule_ids if rid in self._rules]
        else:
            rules = list(self._rules.values())

        # Execute rules and collect findings
        all_findings: list[Finding] = []
        rule_results: list[RuleResult] = []

        for rule in rules:
            result = self._execute_rule(rule, context)
            rule_results.append(result)

            if result.success:
                # Filter findings by confidence and evidence requirements
                filtered = self._filter_findings(result.findings)
                all_findings.extend(filtered)

        # Calculate total execution time
        total_time_ms = (time.time() - start_time) * 1000

        # Get analyzed files
        files_analyzed = [str(p) for p in context.get_changed_files()]
        if context.file_path:
            files_analyzed.append(str(context.file_path))

        return UIAnalysisResult(
            findings=all_findings,
            files_analyzed=list(set(files_analyzed)),
            analysis_time_ms=total_time_ms,
            tier=1,  # Full analysis tier
        )

    def run_fast(
        self,
        context: RuleContext,
    ) -> UIAnalysisResult:
        """Run only fast rules for pre-commit tier.

        Args:
            context: RuleContext containing evaluation data.

        Returns:
            UIAnalysisResult with findings from fast rules only.
        """
        start_time = time.time()

        # Get only fast rules
        fast_rules = self.get_fast_rules()

        # Execute rules
        all_findings: list[Finding] = []

        for rule in fast_rules:
            result = self._execute_rule(rule, context)
            if result.success:
                filtered = self._filter_findings(result.findings)
                all_findings.extend(filtered)

        total_time_ms = (time.time() - start_time) * 1000

        files_analyzed = [str(p) for p in context.get_changed_files()]
        if context.file_path:
            files_analyzed.append(str(context.file_path))

        return UIAnalysisResult(
            findings=all_findings,
            files_analyzed=list(set(files_analyzed)),
            analysis_time_ms=total_time_ms,
            tier=0,  # Pre-commit tier
        )

    def run_category(
        self,
        context: RuleContext,
        category: str,
    ) -> UIAnalysisResult:
        """Run all rules in a specific category.

        Args:
            context: RuleContext containing evaluation data.
            category: Category of rules to run.

        Returns:
            UIAnalysisResult with findings from category rules.
        """
        rule_ids = [r.rule_id for r in self.get_rules_by_category(category)]
        return self.run(context, rule_ids)

    def _execute_rule(
        self,
        rule: BaseRule,
        context: RuleContext,
    ) -> RuleResult:
        """Execute a single rule with error handling.

        Args:
            rule: Rule to execute.
            context: Evaluation context.

        Returns:
            RuleResult with findings or error.
        """
        start_time = time.time()

        try:
            findings = rule.evaluate(context)
            execution_time_ms = (time.time() - start_time) * 1000

            return RuleResult(
                rule_id=rule.rule_id,
                findings=findings,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            if not self.engine_config.continue_on_error:
                raise

            return RuleResult(
                rule_id=rule.rule_id,
                findings=[],
                execution_time_ms=execution_time_ms,
                error=str(e),
            )

    def _filter_findings(self, findings: list[Finding]) -> list[Finding]:
        """Filter findings based on engine configuration.

        Args:
            findings: List of findings to filter.

        Returns:
            Filtered list of findings.
        """
        filtered = []

        for finding in findings:
            # Check confidence threshold
            if finding.confidence < self.engine_config.min_confidence:
                continue

            # Check multi-evidence requirement
            if (
                self.engine_config.require_multi_evidence
                and not finding.has_multi_evidence()
            ):
                # Downgrade to INFO if insufficient evidence
                finding.severity = Severity.INFO

            # Check if rule is ignored
            file_path = None
            if finding.source_ref:
                file_path = finding.source_ref.file_path
            if self.config.is_rule_ignored(finding.rule_id, file_path):
                continue

            filtered.append(finding)

        return filtered

    def register_default_rules(self) -> None:
        """Register all default rules.

        This method should be called after importing the rule modules
        to register the built-in rules.
        """
        # Import rule modules to trigger registration
        try:
            from . import token_drift

            for rule_class in [
                token_drift.ColorNonTokenRule,
                token_drift.SpacingOffScaleRule,
                token_drift.RadiusOffScaleRule,
                token_drift.TypographyOffScaleRule,
            ]:
                self.register(rule_class())
        except ImportError:
            pass

        try:
            from . import duplication

            for rule_class in [
                duplication.StyleDuplicateSetRule,
                duplication.StyleNearDuplicateSetRule,
                duplication.UtilityDuplicateSequenceRule,
                duplication.ComponentDuplicateClusterRule,
            ]:
                self.register(rule_class())
        except ImportError:
            pass

        try:
            from . import inconsistency

            for rule_class in [
                inconsistency.ButtonOutlierRule,
                inconsistency.InputOutlierRule,
                inconsistency.CardOutlierRule,
                inconsistency.FocusRingInconsistentRule,
            ]:
                self.register(rule_class())
        except ImportError:
            pass

        try:
            from . import smells

            for rule_class in [
                smells.SpecificityEscalationRule,
                smells.ImportantNewUsageRule,
                smells.SuppressionNoRationaleRule,
            ]:
                self.register(rule_class())
        except ImportError:
            pass


def create_rule_engine(
    config: "UIQualityConfig",
    register_defaults: bool = True,
) -> RuleEngine:
    """Create and configure a rule engine.

    Args:
        config: UI quality configuration.
        register_defaults: Whether to register default rules.

    Returns:
        Configured RuleEngine instance.
    """
    engine = RuleEngine(config)

    if register_defaults:
        engine.register_default_rules()

    return engine
