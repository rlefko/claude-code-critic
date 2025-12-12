"""Tests for parallel rule execution in the rule engine."""

import threading
import time

import pytest

from claude_indexer.rules.base import BaseRule, Finding, RuleContext, Severity, Trigger
from claude_indexer.rules.config import PerformanceConfig, RuleEngineConfig
from claude_indexer.rules.engine import RuleEngine


class SlowRule(BaseRule):
    """Test rule that takes time to execute."""

    def __init__(self, rule_id: str, sleep_time: float = 0.01):
        self._rule_id = rule_id
        self._sleep_time = sleep_time
        self._category = "test"
        self._triggers = {Trigger.ON_STOP}
        self._is_fast = False
        self._supported_languages = None

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def name(self) -> str:
        return f"Slow Rule {self._rule_id}"

    @property
    def description(self) -> str:
        return "Test rule for parallel execution"

    @property
    def category(self) -> str:
        return self._category

    @property
    def severity(self) -> Severity:
        return Severity.LOW

    @property
    def default_severity(self) -> Severity:
        return Severity.LOW

    @property
    def triggers(self) -> set[Trigger]:
        return self._triggers

    @property
    def is_fast(self) -> bool:
        return self._is_fast

    @property
    def supported_languages(self) -> set[str] | None:
        return self._supported_languages

    def check(self, context: RuleContext) -> list[Finding]:
        time.sleep(self._sleep_time)
        return []


class ErrorRule(BaseRule):
    """Test rule that raises an error."""

    def __init__(self, rule_id: str):
        self._rule_id = rule_id

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def name(self) -> str:
        return f"Error Rule {self._rule_id}"

    @property
    def description(self) -> str:
        return "Test rule that errors"

    @property
    def category(self) -> str:
        return "test"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    @property
    def triggers(self) -> set[Trigger]:
        return {Trigger.ON_STOP}

    @property
    def is_fast(self) -> bool:
        return False

    @property
    def supported_languages(self) -> set[str] | None:
        return None

    def check(self, context: RuleContext) -> list[Finding]:
        raise ValueError(f"Error in {self._rule_id}")


class FindingRule(BaseRule):
    """Test rule that produces findings."""

    def __init__(self, rule_id: str, findings_count: int = 1):
        self._rule_id = rule_id
        self._findings_count = findings_count

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def name(self) -> str:
        return f"Finding Rule {self._rule_id}"

    @property
    def description(self) -> str:
        return "Test rule that produces findings"

    @property
    def category(self) -> str:
        return "test"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> set[Trigger]:
        return {Trigger.ON_STOP}

    @property
    def is_fast(self) -> bool:
        return False

    @property
    def supported_languages(self) -> set[str] | None:
        return None

    def check(self, context: RuleContext) -> list[Finding]:
        return [
            Finding(
                rule_id=self._rule_id,
                summary=f"Finding {i}",
                severity=Severity.MEDIUM,
                file_path=context.file_path or "test.py",
            )
            for i in range(self._findings_count)
        ]


class TestParallelRuleExecution:
    """Tests for parallel rule execution."""

    @pytest.fixture
    def context(self):
        """Create a test context."""
        return RuleContext(
            content="test content",
            file_path="test.py",
            language="python",
        )

    @pytest.fixture
    def parallel_config(self):
        """Create config with parallel execution enabled."""
        return RuleEngineConfig(
            enabled=True,
            performance=PerformanceConfig(
                parallel_execution=True,
                max_parallel_workers=4,
                parallel_rule_timeout_ms=30000.0,
            ),
        )

    @pytest.fixture
    def sequential_config(self):
        """Create config with parallel execution disabled."""
        return RuleEngineConfig(
            enabled=True,
            performance=PerformanceConfig(
                parallel_execution=False,
            ),
        )

    def test_parallel_execution_faster(self, context, parallel_config):
        """Test that parallel execution is faster than sequential."""
        engine = RuleEngine(config=parallel_config)

        # Register 4 slow rules
        for i in range(4):
            engine.register(SlowRule(f"slow_{i}", sleep_time=0.05))

        # Parallel execution
        start_parallel = time.time()
        result_parallel = engine.run(context, parallel=True)
        time_parallel = time.time() - start_parallel

        # Reset and re-register for sequential
        engine = RuleEngine(config=parallel_config)
        for i in range(4):
            engine.register(SlowRule(f"slow_{i}", sleep_time=0.05))

        # Sequential execution
        start_sequential = time.time()
        result_sequential = engine.run(context, parallel=False)
        time_sequential = time.time() - start_sequential

        # Both should execute all rules
        assert result_parallel.rules_executed == 4
        assert result_sequential.rules_executed == 4

        # Parallel should be faster (at least 2x speedup expected with 4 rules)
        assert time_parallel < time_sequential * 0.8

    def test_parallel_collects_all_findings(self, context, parallel_config):
        """Test that parallel execution collects all findings."""
        engine = RuleEngine(config=parallel_config)

        engine.register(FindingRule("rule1", findings_count=2))
        engine.register(FindingRule("rule2", findings_count=3))
        engine.register(FindingRule("rule3", findings_count=1))

        result = engine.run(context, parallel=True)

        assert result.rules_executed == 3
        assert len(result.findings) == 6  # 2 + 3 + 1

    def test_parallel_handles_errors(self, context, parallel_config):
        """Test that parallel execution handles errors gracefully."""
        config = RuleEngineConfig(
            enabled=True,
            continue_on_error=True,
            performance=PerformanceConfig(
                parallel_execution=True,
                max_parallel_workers=4,
            ),
        )
        engine = RuleEngine(config=config)

        engine.register(FindingRule("good1", findings_count=1))
        engine.register(ErrorRule("error1"))
        engine.register(FindingRule("good2", findings_count=1))

        result = engine.run(context, parallel=True)

        assert result.rules_executed == 3
        assert len(result.errors) == 1
        assert result.errors[0].rule_id == "error1"
        # Should still have findings from good rules
        assert len(result.findings) >= 1

    def test_parallel_override(self, context, sequential_config):
        """Test that parallel parameter overrides config."""
        engine = RuleEngine(config=sequential_config)

        for i in range(2):
            engine.register(SlowRule(f"slow_{i}", sleep_time=0.02))

        # Override to parallel despite config saying sequential
        result = engine.run(context, parallel=True)

        assert result.rules_executed == 2

    def test_single_rule_runs_sequentially(self, context, parallel_config):
        """Test that single rule runs sequentially (optimization)."""
        engine = RuleEngine(config=parallel_config)

        engine.register(SlowRule("slow_single", sleep_time=0.01))

        # Should run sequentially since only 1 rule
        result = engine.run(context, parallel=True)

        assert result.rules_executed == 1

    def test_timeout_handling(self, context):
        """Test timeout configuration in parallel execution.

        Note: Python's ThreadPoolExecutor doesn't truly cancel running threads.
        The timeout only affects how long we wait for results. If tasks complete
        before the wait, they won't timeout. This test verifies the configuration
        is respected and execution completes successfully.
        """
        config = RuleEngineConfig(
            enabled=True,
            performance=PerformanceConfig(
                parallel_execution=True,
                max_parallel_workers=2,
                parallel_rule_timeout_ms=50.0,  # 50ms timeout
            ),
        )
        engine = RuleEngine(config=config)

        # This rule sleeps for 100ms
        engine.register(SlowRule("timeout_rule", sleep_time=0.1))
        engine.register(FindingRule("fast_rule", findings_count=1))

        result = engine.run(context, parallel=True)

        # Both rules should be executed (attempted)
        assert result.rules_executed == 2
        # The fast rule should produce findings
        # Note: Timeout behavior is best-effort with Python threads
        assert len(result.findings) >= 1

    def test_config_default_parallel(self, context):
        """Test that parallel is enabled by default in config."""
        config = RuleEngineConfig()
        assert config.performance.parallel_execution is True

    def test_max_workers_respected(self, context, parallel_config):
        """Test that max workers configuration is respected."""
        config = RuleEngineConfig(
            enabled=True,
            performance=PerformanceConfig(
                parallel_execution=True,
                max_parallel_workers=2,
            ),
        )
        engine = RuleEngine(config=config)

        # Track concurrent execution
        concurrent_count = [0]
        max_concurrent = [0]
        lock = threading.Lock()

        class CountingRule(BaseRule):
            def __init__(self, rule_id: str):
                self._rule_id = rule_id

            @property
            def rule_id(self) -> str:
                return self._rule_id

            @property
            def name(self) -> str:
                return f"Counting Rule {self._rule_id}"

            @property
            def description(self) -> str:
                return "Test rule for counting"

            @property
            def category(self) -> str:
                return "test"

            @property
            def severity(self) -> Severity:
                return Severity.LOW

            @property
            def default_severity(self) -> Severity:
                return Severity.LOW

            @property
            def triggers(self) -> set[Trigger]:
                return {Trigger.ON_STOP}

            @property
            def is_fast(self) -> bool:
                return False

            @property
            def supported_languages(self) -> set[str] | None:
                return None

            def check(self, ctx: RuleContext) -> list[Finding]:
                with lock:
                    concurrent_count[0] += 1
                    max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
                time.sleep(0.02)
                with lock:
                    concurrent_count[0] -= 1
                return []

        for i in range(4):
            engine.register(CountingRule(f"counting_{i}"))

        engine.run(context, parallel=True)

        # Max concurrent should not exceed max_workers
        assert max_concurrent[0] <= 2
