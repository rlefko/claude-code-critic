"""Unit tests for claude_indexer.rules.engine module."""

from pathlib import Path

from claude_indexer.rules.base import (
    BaseRule,
    Finding,
    RuleContext,
    Severity,
    Trigger,
)
from claude_indexer.rules.config import PerformanceConfig, RuleEngineConfig
from claude_indexer.rules.engine import (
    RuleEngine,
    RuleEngineResult,
    RuleError,
    RuleExecutionResult,
)


class MockRule(BaseRule):
    """A mock rule for testing."""

    def __init__(
        self,
        rule_id: str = "TEST.MOCK",
        name: str = "Mock Rule",
        category: str = "test",
        severity: Severity = Severity.LOW,
        findings: list[Finding] | None = None,
        is_fast: bool = True,
        supported_languages: list[str] | None = None,
        triggers: list[Trigger] | None = None,
    ):
        self._rule_id = rule_id
        self._name = name
        self._category = category
        self._severity = severity
        self._findings = findings or []
        self._is_fast = is_fast
        self._supported_languages = supported_languages
        self._triggers = triggers or [
            Trigger.ON_WRITE,
            Trigger.ON_STOP,
            Trigger.ON_COMMIT,
        ]

    @property
    def rule_id(self) -> str:
        return self._rule_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def category(self) -> str:
        return self._category

    @property
    def default_severity(self) -> Severity:
        return self._severity

    @property
    def is_fast(self) -> bool:
        return self._is_fast

    @property
    def supported_languages(self) -> list[str] | None:
        return self._supported_languages

    @property
    def triggers(self) -> list[Trigger]:
        return self._triggers

    def check(self, context: RuleContext) -> list[Finding]:
        return self._findings


class FailingRule(BaseRule):
    """A rule that always raises an exception."""

    @property
    def rule_id(self) -> str:
        return "TEST.FAILING"

    @property
    def name(self) -> str:
        return "Failing Rule"

    @property
    def category(self) -> str:
        return "test"

    @property
    def default_severity(self) -> Severity:
        return Severity.HIGH

    def check(self, context: RuleContext) -> list[Finding]:
        raise ValueError("Rule execution failed")


class TestRuleError:
    """Tests for RuleError dataclass."""

    def test_rule_error_creation(self):
        """Test creating a RuleError."""
        error = RuleError(
            rule_id="TEST.RULE",
            error_message="Something went wrong",
            exception_type="ValueError",
        )
        assert error.rule_id == "TEST.RULE"
        assert error.error_message == "Something went wrong"
        assert error.exception_type == "ValueError"

    def test_rule_error_to_dict(self):
        """Test RuleError serialization."""
        error = RuleError(
            rule_id="TEST.RULE",
            error_message="Error",
            exception_type="RuntimeError",
        )
        d = error.to_dict()
        assert d["rule_id"] == "TEST.RULE"
        assert d["error_message"] == "Error"
        assert d["exception_type"] == "RuntimeError"


class TestRuleExecutionResult:
    """Tests for RuleExecutionResult dataclass."""

    def test_execution_result_success(self):
        """Test successful execution result."""
        result = RuleExecutionResult(
            rule_id="TEST.RULE",
            findings=[
                Finding(
                    rule_id="TEST.RULE",
                    severity=Severity.LOW,
                    summary="Test",
                    file_path="test.py",
                )
            ],
            execution_time_ms=10.5,
        )
        assert result.success is True
        assert result.finding_count == 1
        assert result.execution_time_ms == 10.5

    def test_execution_result_with_error(self):
        """Test execution result with error."""
        error = RuleError("TEST.RULE", "Failed")
        result = RuleExecutionResult(
            rule_id="TEST.RULE",
            error=error,
            execution_time_ms=5.0,
        )
        assert result.success is False
        assert result.finding_count == 0


class TestRuleEngineResult:
    """Tests for RuleEngineResult dataclass."""

    def test_engine_result_empty(self):
        """Test empty engine result."""
        result = RuleEngineResult()
        assert result.findings == []
        assert result.errors == []
        assert result.rules_executed == 0
        assert result.should_block() is False

    def test_engine_result_with_findings(self):
        """Test engine result with findings."""
        findings = [
            Finding(
                rule_id="TEST.1",
                severity=Severity.CRITICAL,
                summary="Critical issue",
                file_path="test.py",
            ),
            Finding(
                rule_id="TEST.2",
                severity=Severity.HIGH,
                summary="High issue",
                file_path="test.py",
            ),
            Finding(
                rule_id="TEST.3",
                severity=Severity.MEDIUM,
                summary="Medium issue",
                file_path="test.py",
            ),
            Finding(
                rule_id="TEST.4",
                severity=Severity.LOW,
                summary="Low issue",
                file_path="test.py",
            ),
        ]
        result = RuleEngineResult(findings=findings, rules_executed=4)
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 1
        assert result.low_count == 1

    def test_engine_result_should_block_critical(self):
        """Test should_block with critical findings."""
        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.CRITICAL,
                summary="Critical",
                file_path="test.py",
            )
        ]
        result = RuleEngineResult(findings=findings)
        assert result.should_block(Severity.CRITICAL) is True
        assert result.should_block(Severity.HIGH) is True
        assert result.should_block(Severity.MEDIUM) is True
        assert result.should_block(Severity.LOW) is True

    def test_engine_result_should_block_threshold(self):
        """Test should_block with different thresholds."""
        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.MEDIUM,
                summary="Medium",
                file_path="test.py",
            )
        ]
        result = RuleEngineResult(findings=findings)
        assert result.should_block(Severity.CRITICAL) is False
        assert result.should_block(Severity.HIGH) is False
        assert result.should_block(Severity.MEDIUM) is True
        assert result.should_block(Severity.LOW) is True

    def test_engine_result_get_findings_by_severity(self):
        """Test filtering findings by severity."""
        findings = [
            Finding(
                rule_id="TEST.1",
                severity=Severity.HIGH,
                summary="High 1",
                file_path="test.py",
            ),
            Finding(
                rule_id="TEST.2",
                severity=Severity.HIGH,
                summary="High 2",
                file_path="test.py",
            ),
            Finding(
                rule_id="TEST.3",
                severity=Severity.LOW,
                summary="Low",
                file_path="test.py",
            ),
        ]
        result = RuleEngineResult(findings=findings)
        high_findings = result.get_findings_by_severity(Severity.HIGH)
        assert len(high_findings) == 2

    def test_engine_result_to_dict(self):
        """Test engine result serialization."""
        findings = [
            Finding(
                rule_id="TEST",
                severity=Severity.HIGH,
                summary="Test",
                file_path="test.py",
            )
        ]
        result = RuleEngineResult(
            findings=findings,
            execution_time_ms=100.0,
            rules_executed=5,
        )
        d = result.to_dict()
        assert d["rules_executed"] == 5
        assert d["execution_time_ms"] == 100.0
        assert len(d["findings"]) == 1
        assert d["summary"]["high"] == 1


class TestRuleEngine:
    """Tests for RuleEngine class."""

    def test_engine_creation(self):
        """Test creating a rule engine."""
        engine = RuleEngine()
        assert engine.config is not None
        assert len(engine.get_all_rules()) == 0

    def test_engine_register_rule(self):
        """Test registering a rule."""
        engine = RuleEngine()
        rule = MockRule()
        engine.register(rule)
        assert engine.get_rule("TEST.MOCK") is rule
        assert len(engine.get_all_rules()) == 1

    def test_engine_register_multiple_rules(self):
        """Test registering multiple rules."""
        engine = RuleEngine()
        rule1 = MockRule(rule_id="TEST.1", category="cat1")
        rule2 = MockRule(rule_id="TEST.2", category="cat1")
        rule3 = MockRule(rule_id="TEST.3", category="cat2")
        engine.register(rule1)
        engine.register(rule2)
        engine.register(rule3)
        assert len(engine.get_all_rules()) == 3
        assert len(engine.get_rules_by_category("cat1")) == 2
        assert len(engine.get_rules_by_category("cat2")) == 1

    def test_engine_unregister_rule(self):
        """Test unregistering a rule."""
        engine = RuleEngine()
        rule = MockRule()
        engine.register(rule)
        assert engine.unregister("TEST.MOCK") is True
        assert engine.get_rule("TEST.MOCK") is None
        assert engine.unregister("NONEXISTENT") is False

    def test_engine_run_empty(self):
        """Test running with no rules."""
        engine = RuleEngine()
        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run(context)
        assert result.rules_executed == 0
        assert len(result.findings) == 0

    def test_engine_run_with_findings(self):
        """Test running rules that produce findings."""
        engine = RuleEngine()
        finding = Finding(
            rule_id="TEST.MOCK",
            severity=Severity.HIGH,
            summary="Test finding",
            file_path="test.py",
        )
        rule = MockRule(findings=[finding])
        engine.register(rule)

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run(context)
        assert result.rules_executed == 1
        assert len(result.findings) == 1
        assert result.findings[0].summary == "Test finding"

    def test_engine_run_fast(self):
        """Test running only fast rules."""
        engine = RuleEngine()
        fast_rule = MockRule(rule_id="TEST.FAST", is_fast=True)
        slow_rule = MockRule(rule_id="TEST.SLOW", is_fast=False)
        engine.register(fast_rule)
        engine.register(slow_rule)

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run_fast(context)
        # Only fast rule should run
        assert result.rules_executed == 1
        assert result.rules_skipped == 1

    def test_engine_run_by_category(self):
        """Test running rules by category."""
        engine = RuleEngine()
        security_rule = MockRule(rule_id="TEST.SECURITY", category="security")
        tech_debt_rule = MockRule(rule_id="TEST.TECH_DEBT", category="tech_debt")
        engine.register(security_rule)
        engine.register(tech_debt_rule)

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run_category(context, "security")
        assert result.rules_executed == 1

    def test_engine_run_specific_rules(self):
        """Test running specific rules by ID."""
        engine = RuleEngine()
        rule1 = MockRule(rule_id="TEST.1")
        rule2 = MockRule(rule_id="TEST.2")
        rule3 = MockRule(rule_id="TEST.3")
        engine.register(rule1)
        engine.register(rule2)
        engine.register(rule3)

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run(context, rule_ids=["TEST.1", "TEST.3"])
        assert result.rules_executed == 2

    def test_engine_filter_by_language(self):
        """Test filtering rules by language."""
        engine = RuleEngine()
        python_rule = MockRule(
            rule_id="TEST.PYTHON",
            supported_languages=["python"],
        )
        js_rule = MockRule(
            rule_id="TEST.JS",
            supported_languages=["javascript"],
        )
        any_rule = MockRule(
            rule_id="TEST.ANY",
            supported_languages=None,
        )
        engine.register(python_rule)
        engine.register(js_rule)
        engine.register(any_rule)

        # Python file
        py_context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        py_result = engine.run(py_context)
        # Should run python_rule and any_rule
        assert py_result.rules_executed == 2

        # JavaScript file
        js_context = RuleContext(
            file_path=Path("test.js"),
            content="test",
            language="javascript",
        )
        js_result = engine.run(js_context)
        # Should run js_rule and any_rule
        assert js_result.rules_executed == 2

    def test_engine_handles_rule_error(self):
        """Test engine handling of rule errors."""
        engine = RuleEngine(config=RuleEngineConfig(continue_on_error=True))
        engine.register(FailingRule())
        engine.register(MockRule())

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run(context)
        # Both rules should be attempted
        assert result.rules_executed == 2
        assert len(result.errors) == 1
        assert result.errors[0].rule_id == "TEST.FAILING"

    def test_engine_stop_on_error(self):
        """Test engine stopping on first error (sequential execution)."""
        # Disable parallel execution to test sequential stop-on-error behavior
        config = RuleEngineConfig(
            continue_on_error=False,
            performance=PerformanceConfig(parallel_execution=False),
        )
        engine = RuleEngine(config=config)
        engine.register(FailingRule())
        engine.register(MockRule(rule_id="TEST.AFTER"))

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        result = engine.run(context)
        # Should stop after first error in sequential mode
        assert result.rules_executed == 1
        assert len(result.errors) == 1

    def test_engine_disabled_rule(self):
        """Test that disabled rules are not registered."""
        config = RuleEngineConfig()
        config.rules["TEST.DISABLED"] = type(
            "MockConfig",
            (),
            {"enabled": False, "severity_override": None, "parameters": {}},
        )()

        engine = RuleEngine(config=config)
        rule = MockRule(rule_id="TEST.DISABLED")
        engine.register(rule)

        # Rule should not be registered because it's disabled
        assert engine.get_rule("TEST.DISABLED") is None

    def test_engine_filter_by_trigger(self):
        """Test filtering rules by trigger."""
        engine = RuleEngine()
        on_write_rule = MockRule(
            rule_id="TEST.WRITE",
            triggers=[Trigger.ON_WRITE],
        )
        on_commit_rule = MockRule(
            rule_id="TEST.COMMIT",
            triggers=[Trigger.ON_COMMIT],
        )
        engine.register(on_write_rule)
        engine.register(on_commit_rule)

        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )

        # ON_WRITE trigger
        write_result = engine.run(context, trigger=Trigger.ON_WRITE)
        assert write_result.rules_executed == 1

        # ON_COMMIT trigger
        commit_result = engine.run(context, trigger=Trigger.ON_COMMIT)
        assert commit_result.rules_executed == 1
