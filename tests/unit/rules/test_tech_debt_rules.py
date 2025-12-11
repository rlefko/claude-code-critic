"""
Unit tests for tech debt rules.

Tests for all tech debt rules in claude_indexer/rules/tech_debt/.
"""

from pathlib import Path

import pytest

from claude_indexer.rules.base import RuleContext, Severity


# =============================================================================
# Test Fixtures
# =============================================================================


def create_context(
    content: str, language: str, file_path: str = "test.py"
) -> RuleContext:
    """Create a RuleContext for testing."""
    return RuleContext(
        file_path=Path(file_path),
        content=content,
        language=language,
    )


# =============================================================================
# Large Files Rule Tests
# =============================================================================


class TestLargeFilesRule:
    """Tests for TECH_DEBT.LARGE_FILES rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.large_files import LargeFilesRule

        return LargeFilesRule()

    def test_detects_large_file(self, rule):
        # Create a file with 600 lines (over default 500)
        content = "\n".join([f"line {i}" for i in range(600)])
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 1
        assert "600 lines" in findings[0].summary
        assert "exceeds 500" in findings[0].summary

    def test_ignores_small_file(self, rule):
        content = "\n".join([f"line {i}" for i in range(100)])
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_provides_remediation_hints(self, rule):
        content = "\n".join([f"line {i}" for i in range(600)])
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings[0].remediation_hints) > 0
        assert any("split" in hint.lower() for hint in findings[0].remediation_hints)

    def test_has_correct_metadata(self, rule):
        assert rule.rule_id == "TECH_DEBT.LARGE_FILES"
        assert rule.category == "tech_debt"
        assert rule.default_severity == Severity.LOW


# =============================================================================
# Commented Code Rule Tests
# =============================================================================


class TestCommentedCodeRule:
    """Tests for TECH_DEBT.COMMENTED_CODE rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.commented_code import CommentedCodeRule

        return CommentedCodeRule()

    def test_detects_commented_python_code(self, rule):
        content = """
def active_function():
    pass

# def old_function():
#     x = 1
#     return x
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 1
        assert "commented code" in findings[0].summary.lower()

    def test_detects_commented_javascript_code(self, rule):
        content = """
function activeFunction() {}

// function oldFunction() {
//     const x = 1;
//     return x;
// }
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) == 1

    def test_ignores_regular_comments(self, rule):
        content = """
# This is a documentation comment
# that spans multiple lines
# but doesn't contain code
def my_function():
    pass
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_has_auto_fix(self, rule):
        assert rule.can_auto_fix() is True


# =============================================================================
# Magic Numbers Rule Tests
# =============================================================================


class TestMagicNumbersRule:
    """Tests for TECH_DEBT.MAGIC_NUMBERS rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.magic_numbers import MagicNumbersRule

        return MagicNumbersRule()

    def test_detects_magic_number(self, rule):
        content = """
def calculate_price(quantity):
    return quantity * 42.50
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert any("42" in f.summary for f in findings)

    def test_ignores_common_numbers(self, rule):
        content = """
x = 0
y = 1
z = -1
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_constants(self, rule):
        content = """
MAX_RETRIES = 5
TIMEOUT_SECONDS = 30
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_test_files(self, rule):
        content = """
def test_something():
    assert result == 42
"""
        context = create_context(content, "python", "test_example.py")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_ignores_array_indices(self, rule):
        content = """
x = items[5]
y = data[0:10]
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        # Array indices should be ignored
        assert all("5" not in f.summary and "10" not in f.summary for f in findings)


# =============================================================================
# Complexity Rule Tests
# =============================================================================


class TestComplexityRule:
    """Tests for TECH_DEBT.COMPLEXITY rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.complexity import ComplexityRule

        return ComplexityRule()

    def test_detects_high_complexity(self, rule):
        # Function with many decision points
        content = """
def complex_function(a, b, c, d):
    if a:
        if b:
            if c:
                return 1
            elif d:
                return 2
            else:
                return 3
        else:
            for i in range(10):
                if i > 5:
                    break
            return 4
    elif b and c:
        while True:
            if d or a:
                return 5
            break
    else:
        try:
            return 6
        except Exception:
            return 7
    return 8
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "complexity" in findings[0].summary.lower()

    def test_ignores_simple_function(self, rule):
        content = """
def simple_function(x):
    if x > 0:
        return x
    return 0
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_detects_javascript_complexity(self, rule):
        content = """
function complexFunc(a, b, c) {
    if (a) {
        if (b) {
            if (c) {
                return 1;
            } else if (a && b) {
                return 2;
            } else {
                return 3;
            }
        }
        for (let i = 0; i < 10; i++) {
            if (i > 5) break;
        }
        switch(c) {
            case 1: return 4;
            case 2: return 5;
            case 3: return 6;
        }
    }
    return a || b ? c : 0;
}
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) >= 1


# =============================================================================
# Deprecated APIs Rule Tests
# =============================================================================


class TestDeprecatedAPIsRule:
    """Tests for TECH_DEBT.DEPRECATED_APIS rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.deprecated_apis import DeprecatedAPIsRule

        return DeprecatedAPIsRule()

    def test_detects_python_deprecated_collections(self, rule):
        content = """
from collections import Mapping
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "collections" in findings[0].summary.lower()

    def test_detects_asyncio_coroutine(self, rule):
        content = """
@asyncio.coroutine
def my_coroutine():
    yield from asyncio.sleep(1)
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_javascript_substr(self, rule):
        content = """
const result = str.substr(0, 5);
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "substr" in findings[0].summary.lower()

    def test_detects_buffer_constructor(self, rule):
        content = """
const buf = new Buffer(10);
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "Buffer" in findings[0].summary

    def test_ignores_safe_code(self, rule):
        content = """
from collections.abc import Mapping
import argparse
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0


# =============================================================================
# Dead Code Rule Tests
# =============================================================================


class TestDeadCodeRule:
    """Tests for TECH_DEBT.DEAD_CODE rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.dead_code import DeadCodeRule

        return DeadCodeRule()

    def test_detects_code_after_return(self, rule):
        content = """
def example():
    return 1
    x = 2
    print(x)
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "unreachable" in findings[0].summary.lower()

    def test_detects_code_after_raise(self, rule):
        content = """
def example():
    raise ValueError("error")
    cleanup()
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_detects_code_after_break(self, rule):
        content = """
for i in range(10):
    break
    print(i)
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_code_in_different_scope(self, rule):
        content = """
def example():
    if condition:
        return 1
    return 2
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_detects_javascript_unreachable(self, rule):
        content = """
function example() {
    return 1;
    console.log("unreachable");
}
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_has_auto_fix(self, rule):
        assert rule.can_auto_fix() is True


# =============================================================================
# Naming Conventions Rule Tests
# =============================================================================


class TestNamingConventionsRule:
    """Tests for TECH_DEBT.NAMING_CONVENTIONS rule."""

    @pytest.fixture
    def rule(self):
        from claude_indexer.rules.tech_debt.naming_conventions import (
            NamingConventionsRule,
        )

        return NamingConventionsRule()

    def test_detects_python_function_camelcase(self, rule):
        content = """
def myFunction():
    pass
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "myFunction" in findings[0].summary

    def test_detects_python_class_lowercase(self, rule):
        content = """
class myclass:
    pass
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        assert "myclass" in findings[0].summary

    def test_ignores_correct_python_naming(self, rule):
        content = """
def my_function():
    pass

class MyClass:
    pass

MY_CONSTANT = 42
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_detects_javascript_function_snake_case(self, rule):
        content = """
function my_function() {}
"""
        context = create_context(content, "javascript", "test.js")
        findings = rule.check(context)
        assert len(findings) >= 1

    def test_ignores_dunder_methods(self, rule):
        content = """
def __init__(self):
    pass
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) == 0

    def test_has_auto_fix(self, rule):
        assert rule.can_auto_fix() is True

    def test_provides_suggested_name(self, rule):
        content = """
def myFunction():
    pass
"""
        context = create_context(content, "python")
        findings = rule.check(context)
        assert len(findings) >= 1
        # Should suggest snake_case
        assert any("my_function" in hint for hint in findings[0].remediation_hints)


# =============================================================================
# Rule Discovery Tests
# =============================================================================


class TestTechDebtRuleDiscovery:
    """Test that all tech debt rules are discoverable."""

    def test_all_rules_discoverable(self):
        from claude_indexer.rules.discovery import RuleDiscovery

        discovery = RuleDiscovery()
        rule_classes = discovery.discover_all()

        # Check for tech debt rules
        tech_debt_rule_ids = []
        for rule_id, rule_cls in rule_classes.items():
            rule_instance = rule_cls()
            if rule_instance.category == "tech_debt":
                tech_debt_rule_ids.append(rule_id)

        expected_rules = [
            "TECH_DEBT.TODO_MARKERS",
            "TECH_DEBT.FIXME_MARKERS",
            "TECH_DEBT.DEBUG_STATEMENTS",
            "TECH_DEBT.BREAKPOINTS",
            "TECH_DEBT.LARGE_FILES",
            "TECH_DEBT.COMMENTED_CODE",
            "TECH_DEBT.MAGIC_NUMBERS",
            "TECH_DEBT.COMPLEXITY",
            "TECH_DEBT.DEPRECATED_APIS",
            "TECH_DEBT.DEAD_CODE",
            "TECH_DEBT.NAMING_CONVENTIONS",
        ]

        for rule_id in expected_rules:
            assert rule_id in tech_debt_rule_ids, f"Missing rule: {rule_id}"

    def test_tech_debt_rules_have_correct_category(self):
        from claude_indexer.rules.discovery import RuleDiscovery

        discovery = RuleDiscovery()
        rule_classes = discovery.discover_category("tech_debt")

        for rule_id, rule_cls in rule_classes.items():
            rule_instance = rule_cls()
            assert rule_instance.category == "tech_debt"


# =============================================================================
# Rule Engine Integration Tests
# =============================================================================


class TestTechDebtRulesWithEngine:
    """Test tech debt rules work with the rule engine."""

    def test_engine_runs_tech_debt_rules(self):
        from claude_indexer.rules.base import Trigger
        from claude_indexer.rules.engine import RuleEngine

        engine = RuleEngine()
        engine.load_rules()

        # Create context with various tech debt issues
        content = """
def myBadFunction():
    # def old_code():
    #     return 1
    #     x = 2
    return 42
    unreachable_code()

MAX = 500
"""
        context = create_context(content, "python")

        result = engine.run(context, trigger=Trigger.ON_COMMIT)

        # Should find multiple tech debt issues
        assert result.rules_executed > 0

    def test_engine_result_filters_by_category(self):
        from claude_indexer.rules.base import Trigger
        from claude_indexer.rules.engine import RuleEngine

        engine = RuleEngine()
        engine.load_rules()

        content = """
def myFunction():
    return 1
"""
        context = create_context(content, "python")

        result = engine.run_category(context, "tech_debt")

        # All findings should be from tech_debt category
        for finding in result.findings:
            assert finding.rule_id.startswith("TECH_DEBT.")
