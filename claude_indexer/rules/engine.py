"""
Rule engine coordinator for executing code quality rules.

This module provides the RuleEngine class that orchestrates rule
execution, result aggregation, and provides filtering by trigger,
category, and language.

Supports parallel rule execution for improved performance using
ThreadPoolExecutor when multiple rules need to run.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .base import BaseRule, Finding, RuleContext, Severity, Trigger
from .config import RuleConfig, RuleEngineConfig, RuleEngineConfigLoader
from .discovery import RuleDiscovery

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class RuleError:
    """Error that occurred during rule execution."""

    rule_id: str
    error_message: str
    exception_type: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "error_message": self.error_message,
            "exception_type": self.exception_type,
        }


@dataclass
class RuleExecutionResult:
    """Result of executing a single rule."""

    rule_id: str
    findings: list[Finding] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error: RuleError | None = None

    @property
    def success(self) -> bool:
        """Check if the rule executed successfully."""
        return self.error is None

    @property
    def finding_count(self) -> int:
        """Get the number of findings."""
        return len(self.findings)


@dataclass
class RuleEngineResult:
    """Result of rule engine execution."""

    findings: list[Finding] = field(default_factory=list)
    errors: list[RuleError] = field(default_factory=list)
    execution_time_ms: float = 0.0
    rules_executed: int = 0
    rules_skipped: int = 0

    def should_block(self, severity_threshold: Severity = Severity.HIGH) -> bool:
        """Check if any findings should block the operation.

        Args:
            severity_threshold: Minimum severity to block

        Returns:
            True if any findings meet or exceed the threshold
        """
        for finding in self.findings:
            if finding.severity >= severity_threshold:
                return True
        return False

    @property
    def critical_count(self) -> int:
        """Get count of critical findings."""
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Get count of high findings."""
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        """Get count of medium findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        """Get count of low findings."""
        return sum(1 for f in self.findings if f.severity == Severity.LOW)

    def get_findings_by_severity(self, severity: Severity) -> list[Finding]:
        """Get findings filtered by severity.

        Args:
            severity: Severity level to filter by

        Returns:
            List of findings with the specified severity
        """
        return [f for f in self.findings if f.severity == severity]

    def get_findings_by_rule(self, rule_id: str) -> list[Finding]:
        """Get findings filtered by rule ID.

        Args:
            rule_id: Rule identifier to filter by

        Returns:
            List of findings from the specified rule
        """
        return [f for f in self.findings if f.rule_id == rule_id]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "errors": [e.to_dict() for e in self.errors],
            "execution_time_ms": self.execution_time_ms,
            "rules_executed": self.rules_executed,
            "rules_skipped": self.rules_skipped,
            "summary": {
                "total_findings": len(self.findings),
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
        }


class RuleEngine:
    """Engine for executing code quality rules.

    The RuleEngine orchestrates rule discovery, registration, and execution.
    It supports filtering by trigger, category, and language, and provides
    result aggregation with timing information.

    Example usage:
        engine = RuleEngine()
        engine.load_rules()  # Auto-discover rules

        context = RuleContext.from_file(Path("my_file.py"))
        result = engine.run(context, trigger=Trigger.ON_STOP)

        if result.should_block():
            print("Blocking due to critical/high findings")
    """

    def __init__(
        self,
        config: RuleEngineConfig | None = None,
        config_loader: RuleEngineConfigLoader | None = None,
    ):
        """Initialize the rule engine.

        Args:
            config: Optional pre-loaded configuration
            config_loader: Optional config loader for loading from files
        """
        if config:
            self.config = config
        elif config_loader:
            self.config = config_loader.load()
        else:
            self.config = RuleEngineConfig()

        self._rules: dict[str, BaseRule] = {}
        self._rules_by_category: dict[str, list[BaseRule]] = {}
        self._rules_by_trigger: dict[Trigger, list[BaseRule]] = {}

    def load_rules(self, discovery: RuleDiscovery | None = None) -> int:
        """Load rules using discovery.

        Args:
            discovery: Optional RuleDiscovery instance

        Returns:
            Number of rules loaded
        """
        if discovery is None:
            discovery = RuleDiscovery()

        rule_classes = discovery.discover_all()
        loaded = 0

        for rule_id, rule_class in rule_classes.items():
            if self.config.is_rule_enabled(rule_id):
                try:
                    rule = rule_class()
                    self.register(rule)
                    loaded += 1
                except Exception as e:
                    logger.warning(f"Could not instantiate rule {rule_id}: {e}")

        logger.info(f"Loaded {loaded} rules")
        return loaded

    def register(self, rule: BaseRule) -> None:
        """Register a rule with the engine.

        Args:
            rule: Rule instance to register
        """
        rule_id = rule.rule_id

        # Check if enabled in config
        if not self.config.is_rule_enabled(rule_id, rule.category):
            logger.debug(f"Rule {rule_id} is disabled in config, skipping")
            return

        self._rules[rule_id] = rule

        # Index by category
        category = rule.category
        if category not in self._rules_by_category:
            self._rules_by_category[category] = []
        self._rules_by_category[category].append(rule)

        # Index by trigger
        for trigger in rule.triggers:
            if trigger not in self._rules_by_trigger:
                self._rules_by_trigger[trigger] = []
            self._rules_by_trigger[trigger].append(rule)

        logger.debug(f"Registered rule: {rule_id}")

    def unregister(self, rule_id: str) -> bool:
        """Unregister a rule from the engine.

        Args:
            rule_id: Rule identifier to unregister

        Returns:
            True if rule was found and removed, False otherwise
        """
        if rule_id not in self._rules:
            return False

        rule = self._rules[rule_id]

        # Remove from main registry
        del self._rules[rule_id]

        # Remove from category index
        category = rule.category
        if category in self._rules_by_category:
            self._rules_by_category[category] = [
                r for r in self._rules_by_category[category] if r.rule_id != rule_id
            ]

        # Remove from trigger index
        for trigger in rule.triggers:
            if trigger in self._rules_by_trigger:
                self._rules_by_trigger[trigger] = [
                    r for r in self._rules_by_trigger[trigger] if r.rule_id != rule_id
                ]

        return True

    def get_rule(self, rule_id: str) -> BaseRule | None:
        """Get a rule by its ID.

        Args:
            rule_id: Rule identifier

        Returns:
            Rule instance or None if not found
        """
        return self._rules.get(rule_id)

    def get_rules_by_category(self, category: str) -> list[BaseRule]:
        """Get all rules for a specific category.

        Args:
            category: Category name

        Returns:
            List of rules in the category
        """
        return self._rules_by_category.get(category, []).copy()

    def get_rules_by_trigger(self, trigger: Trigger) -> list[BaseRule]:
        """Get all rules for a specific trigger.

        Args:
            trigger: Trigger type

        Returns:
            List of rules with the trigger
        """
        return self._rules_by_trigger.get(trigger, []).copy()

    def get_fast_rules(self) -> list[BaseRule]:
        """Get all fast rules suitable for on-write checks.

        Returns:
            List of rules marked as fast
        """
        return [r for r in self._rules.values() if r.is_fast]

    def get_all_rules(self) -> list[BaseRule]:
        """Get all registered rules.

        Returns:
            List of all registered rules
        """
        return list(self._rules.values())

    def run(
        self,
        context: RuleContext,
        trigger: Trigger = Trigger.ON_STOP,
        rule_ids: list[str] | None = None,
        categories: list[str] | None = None,
        parallel: bool | None = None,
    ) -> RuleEngineResult:
        """Run rules and collect findings.

        Supports parallel execution for improved performance when running
        multiple rules. Parallel execution is controlled by the performance
        config or can be overridden per-call.

        Args:
            context: RuleContext with file content, diff info, etc.
            trigger: Trigger type to filter rules
            rule_ids: Optional list of specific rule IDs to run
            categories: Optional list of categories to run
            parallel: Override parallel execution (None = use config)

        Returns:
            RuleEngineResult with findings and execution info
        """
        start_time = time.time()
        rules_skipped = 0

        # Select rules to run
        if rule_ids:
            rules = [self._rules[rid] for rid in rule_ids if rid in self._rules]
        elif categories:
            rules = []
            for cat in categories:
                rules.extend(self.get_rules_by_category(cat))
        else:
            rules = self._rules_by_trigger.get(trigger, [])

        # Filter by language if applicable
        rules = self._filter_by_language(rules, context.language)

        # Filter fast rules for ON_WRITE trigger
        if trigger == Trigger.ON_WRITE:
            original_count = len(rules)
            rules = [r for r in rules if r.is_fast]
            rules_skipped = original_count - len(rules)

        # Determine execution mode
        use_parallel = parallel if parallel is not None else self.config.performance.parallel_execution

        # Execute rules (parallel or sequential)
        if use_parallel and len(rules) > 1:
            findings, errors, rules_executed = self._execute_rules_parallel(rules, context)
        else:
            findings, errors, rules_executed = self._execute_rules_sequential(rules, context)

        return RuleEngineResult(
            findings=findings,
            errors=errors,
            execution_time_ms=(time.time() - start_time) * 1000,
            rules_executed=rules_executed,
            rules_skipped=rules_skipped,
        )

    def _execute_rules_sequential(
        self,
        rules: list[BaseRule],
        context: RuleContext,
    ) -> tuple[list[Finding], list[RuleError], int]:
        """Execute rules sequentially.

        Args:
            rules: List of rules to execute.
            context: RuleContext for rule execution.

        Returns:
            Tuple of (findings, errors, rules_executed_count).
        """
        findings: list[Finding] = []
        errors: list[RuleError] = []
        rules_executed = 0

        for rule in rules:
            result = self._execute_rule(rule, context)
            rules_executed += 1

            if result.error:
                errors.append(result.error)
                if not self.config.continue_on_error:
                    break
            else:
                findings.extend(result.findings)

        return findings, errors, rules_executed

    def _execute_rules_parallel(
        self,
        rules: list[BaseRule],
        context: RuleContext,
    ) -> tuple[list[Finding], list[RuleError], int]:
        """Execute rules in parallel using ThreadPoolExecutor.

        Uses ThreadPoolExecutor to run multiple rules concurrently,
        which can significantly reduce total execution time when
        multiple independent rules need to run.

        Args:
            rules: List of rules to execute.
            context: RuleContext for rule execution.

        Returns:
            Tuple of (findings, errors, rules_executed_count).
        """
        findings: list[Finding] = []
        errors: list[RuleError] = []
        rules_executed = 0

        max_workers = min(
            self.config.performance.max_parallel_workers,
            len(rules),
        )
        timeout_seconds = self.config.performance.parallel_rule_timeout_ms / 1000.0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all rules
            future_to_rule = {
                executor.submit(self._execute_rule, rule, context): rule
                for rule in rules
            }

            # Collect results as they complete
            for future in as_completed(future_to_rule):
                rule = future_to_rule[future]
                rules_executed += 1

                try:
                    result = future.result(timeout=timeout_seconds)

                    if result.error:
                        errors.append(result.error)
                        if not self.config.continue_on_error:
                            # Cancel remaining futures
                            for f in future_to_rule:
                                f.cancel()
                            break
                    else:
                        findings.extend(result.findings)

                except TimeoutError:
                    error = RuleError(
                        rule_id=rule.rule_id,
                        error_message=f"Rule timed out after {timeout_seconds}s",
                        exception_type="TimeoutError",
                    )
                    errors.append(error)
                    logger.warning(f"Rule {rule.rule_id} timed out in parallel execution")

                except Exception as e:
                    error = RuleError(
                        rule_id=rule.rule_id,
                        error_message=f"Parallel execution failed: {e}",
                        exception_type=type(e).__name__,
                    )
                    errors.append(error)
                    logger.warning(f"Rule {rule.rule_id} failed in parallel: {e}")

        return findings, errors, rules_executed

    def run_fast(self, context: RuleContext) -> RuleEngineResult:
        """Run only fast rules (for on-write checks).

        Args:
            context: RuleContext with file content

        Returns:
            RuleEngineResult with findings
        """
        return self.run(context, trigger=Trigger.ON_WRITE)

    def run_category(
        self, context: RuleContext, category: str
    ) -> RuleEngineResult:
        """Run all rules in a specific category.

        Args:
            context: RuleContext with file content
            category: Category name

        Returns:
            RuleEngineResult with findings
        """
        return self.run(context, categories=[category])

    def _execute_rule(
        self, rule: BaseRule, context: RuleContext
    ) -> RuleExecutionResult:
        """Execute a single rule.

        Args:
            rule: Rule to execute
            context: RuleContext

        Returns:
            RuleExecutionResult with findings or error
        """
        start_time = time.time()

        try:
            findings = rule.check(context)
            execution_time_ms = (time.time() - start_time) * 1000

            return RuleExecutionResult(
                rule_id=rule.rule_id,
                findings=findings,
                execution_time_ms=execution_time_ms,
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000

            error = RuleError(
                rule_id=rule.rule_id,
                error_message=str(e),
                exception_type=type(e).__name__,
            )

            logger.warning(f"Rule {rule.rule_id} failed: {e}")

            return RuleExecutionResult(
                rule_id=rule.rule_id,
                execution_time_ms=execution_time_ms,
                error=error,
            )

    def _filter_by_language(
        self, rules: list[BaseRule], language: str
    ) -> list[BaseRule]:
        """Filter rules by supported language.

        Args:
            rules: List of rules to filter
            language: Target language

        Returns:
            Filtered list of rules
        """
        result = []
        for rule in rules:
            supported = rule.supported_languages
            if supported is None or language in supported:
                result.append(rule)
        return result


def create_rule_engine(
    config: RuleEngineConfig | None = None,
    project_path=None,
    auto_load: bool = True,
) -> RuleEngine:
    """Factory function to create and configure a rule engine.

    Args:
        config: Optional pre-loaded configuration
        project_path: Optional project path for config loading
        auto_load: Whether to auto-load rules

    Returns:
        Configured RuleEngine instance
    """
    if config is None and project_path:
        config_loader = RuleEngineConfigLoader(project_path)
        engine = RuleEngine(config_loader=config_loader)
    else:
        engine = RuleEngine(config=config)

    if auto_load:
        engine.load_rules()

    return engine
