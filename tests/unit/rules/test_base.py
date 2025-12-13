"""Unit tests for claude_indexer.rules.base module."""

from pathlib import Path

from claude_indexer.rules.base import (
    BaseRule,
    DiffHunk,
    Evidence,
    Finding,
    RuleContext,
    Severity,
    Trigger,
)


class TestSeverity:
    """Tests for Severity enum."""

    def test_severity_values(self):
        """Test that severity values are correct."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"

    def test_severity_comparison_less_than(self):
        """Test that severities can be compared with <."""
        assert Severity.LOW < Severity.MEDIUM
        assert Severity.MEDIUM < Severity.HIGH
        assert Severity.HIGH < Severity.CRITICAL

    def test_severity_comparison_greater_than(self):
        """Test that severities can be compared with >."""
        assert Severity.CRITICAL > Severity.HIGH
        assert Severity.HIGH > Severity.MEDIUM
        assert Severity.MEDIUM > Severity.LOW

    def test_severity_comparison_equal(self):
        """Test severity equality."""
        assert Severity.LOW == Severity.LOW
        assert not (Severity.LOW > Severity.LOW)
        assert not (Severity.LOW < Severity.LOW)

    def test_severity_comparison_le_ge(self):
        """Test <= and >= comparisons."""
        assert Severity.LOW <= Severity.LOW
        assert Severity.LOW <= Severity.MEDIUM
        assert Severity.CRITICAL >= Severity.CRITICAL
        assert Severity.CRITICAL >= Severity.HIGH


class TestTrigger:
    """Tests for Trigger enum."""

    def test_trigger_values(self):
        """Test that trigger values are correct."""
        assert Trigger.ON_WRITE.value == "on_write"
        assert Trigger.ON_STOP.value == "on_stop"
        assert Trigger.ON_COMMIT.value == "on_commit"
        assert Trigger.ON_DEMAND.value == "on_demand"


class TestDiffHunk:
    """Tests for DiffHunk dataclass."""

    def test_diff_hunk_creation(self):
        """Test creating a DiffHunk."""
        hunk = DiffHunk(
            old_start=10,
            old_count=5,
            new_start=10,
            new_count=7,
            lines=["+added line", " context", "-removed", "+new"],
        )
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 10
        assert hunk.new_count == 7

    def test_diff_hunk_added_lines(self):
        """Test getting added line numbers from a hunk."""
        hunk = DiffHunk(
            old_start=1,
            old_count=3,
            new_start=1,
            new_count=4,
            lines=["+line 1", " line 2", "+line 3", " line 4"],
        )
        added = hunk.added_lines
        assert 1 in added  # First added line
        assert 3 in added  # Third line added


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_evidence_creation(self):
        """Test creating Evidence."""
        evidence = Evidence(
            description="Found SQL injection",
            line_number=42,
            code_snippet="query = f'SELECT * FROM {table}'",
            data={"severity": "critical"},
        )
        assert evidence.description == "Found SQL injection"
        assert evidence.line_number == 42
        assert evidence.code_snippet == "query = f'SELECT * FROM {table}'"
        assert evidence.data["severity"] == "critical"

    def test_evidence_to_dict(self):
        """Test Evidence serialization."""
        evidence = Evidence(
            description="Test",
            line_number=10,
            code_snippet="print('hello')",
        )
        d = evidence.to_dict()
        assert d["description"] == "Test"
        assert d["line_number"] == 10
        assert d["code_snippet"] == "print('hello')"

    def test_evidence_minimal(self):
        """Test Evidence with only required fields."""
        evidence = Evidence(description="Minimal evidence")
        assert evidence.description == "Minimal evidence"
        assert evidence.line_number is None
        assert evidence.code_snippet is None
        assert evidence.data == {}


class TestFinding:
    """Tests for Finding dataclass."""

    def test_finding_creation(self):
        """Test creating a Finding."""
        finding = Finding(
            rule_id="SECURITY.SQL_INJECTION",
            severity=Severity.CRITICAL,
            summary="SQL injection vulnerability detected",
            file_path="/path/to/file.py",
            line_number=42,
        )
        assert finding.rule_id == "SECURITY.SQL_INJECTION"
        assert finding.severity == Severity.CRITICAL
        assert finding.summary == "SQL injection vulnerability detected"
        assert finding.file_path == "/path/to/file.py"
        assert finding.line_number == 42

    def test_finding_to_dict(self):
        """Test Finding serialization."""
        finding = Finding(
            rule_id="TEST.RULE",
            severity=Severity.HIGH,
            summary="Test finding",
            file_path="test.py",
            line_number=1,
            evidence=[Evidence(description="Test evidence")],
            remediation_hints=["Fix the issue"],
        )
        d = finding.to_dict()
        assert d["rule_id"] == "TEST.RULE"
        assert d["severity"] == "high"
        assert d["summary"] == "Test finding"
        assert d["file_path"] == "test.py"
        assert d["line_number"] == 1
        assert len(d["evidence"]) == 1
        assert d["remediation_hints"] == ["Fix the issue"]

    def test_finding_from_dict(self):
        """Test Finding deserialization."""
        d = {
            "rule_id": "TEST.RULE",
            "severity": "medium",
            "summary": "Test",
            "file_path": "test.py",
            "evidence": [{"description": "Evidence", "line_number": 5}],
        }
        finding = Finding.from_dict(d)
        assert finding.rule_id == "TEST.RULE"
        assert finding.severity == Severity.MEDIUM
        assert finding.summary == "Test"
        assert len(finding.evidence) == 1
        assert finding.evidence[0].line_number == 5

    def test_finding_defaults(self):
        """Test Finding default values."""
        finding = Finding(
            rule_id="TEST",
            severity=Severity.LOW,
            summary="Test",
            file_path="test.py",
        )
        assert finding.line_number is None
        assert finding.end_line is None
        assert finding.evidence == []
        assert finding.remediation_hints == []
        assert finding.can_auto_fix is False
        assert finding.confidence == 1.0
        assert finding.is_new is True


class TestRuleContext:
    """Tests for RuleContext dataclass."""

    def test_rule_context_creation(self):
        """Test creating a RuleContext."""
        context = RuleContext(
            file_path=Path("/path/to/file.py"),
            content="def foo():\n    pass\n",
            language="python",
        )
        assert context.file_path == Path("/path/to/file.py")
        assert context.content == "def foo():\n    pass\n"
        assert context.language == "python"

    def test_rule_context_lines(self):
        """Test getting lines from content."""
        context = RuleContext(
            file_path=Path("test.py"),
            content="line1\nline2\nline3",
            language="python",
        )
        assert context.lines == ["line1", "line2", "line3"]

    def test_rule_context_is_line_in_diff_no_diff(self):
        """Test is_line_in_diff when no diff info available."""
        context = RuleContext(
            file_path=Path("test.py"),
            content="content",
            language="python",
        )
        # When no diff info, assume all lines are in scope
        assert context.is_line_in_diff(1) is True
        assert context.is_line_in_diff(100) is True

    def test_rule_context_is_line_in_diff_with_diff(self):
        """Test is_line_in_diff with diff info."""
        context = RuleContext(
            file_path=Path("test.py"),
            content="line1\nline2\nline3\nline4",
            language="python",
            changed_lines={2, 4},
        )
        assert context.is_line_in_diff(1) is False
        assert context.is_line_in_diff(2) is True
        assert context.is_line_in_diff(3) is False
        assert context.is_line_in_diff(4) is True

    def test_rule_context_get_line_content(self):
        """Test getting specific line content."""
        context = RuleContext(
            file_path=Path("test.py"),
            content="line1\nline2\nline3",
            language="python",
        )
        assert context.get_line_content(1) == "line1"
        assert context.get_line_content(2) == "line2"
        assert context.get_line_content(3) == "line3"
        assert context.get_line_content(0) is None
        assert context.get_line_content(4) is None

    def test_rule_context_from_file(self, tmp_path):
        """Test creating context from a file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        context = RuleContext.from_file(test_file)
        assert context.file_path == test_file
        assert context.content == "print('hello')"
        assert context.language == "python"

    def test_rule_context_language_detection(self, tmp_path):
        """Test language detection from file extension."""
        # Python
        py_file = tmp_path / "test.py"
        py_file.write_text("")
        assert RuleContext.from_file(py_file).language == "python"

        # JavaScript
        js_file = tmp_path / "test.js"
        js_file.write_text("")
        assert RuleContext.from_file(js_file).language == "javascript"

        # TypeScript
        ts_file = tmp_path / "test.ts"
        ts_file.write_text("")
        assert RuleContext.from_file(ts_file).language == "typescript"

        # Unknown
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("")
        assert RuleContext.from_file(txt_file).language == "unknown"


class TestBaseRule:
    """Tests for BaseRule abstract class."""

    def test_concrete_rule_implementation(self):
        """Test that a concrete rule can be implemented."""

        class TestRule(BaseRule):
            @property
            def rule_id(self) -> str:
                return "TEST.EXAMPLE"

            @property
            def name(self) -> str:
                return "Example Rule"

            @property
            def category(self) -> str:
                return "test"

            @property
            def default_severity(self) -> Severity:
                return Severity.MEDIUM

            def check(self, context: RuleContext) -> list[Finding]:
                return []

        rule = TestRule()
        assert rule.rule_id == "TEST.EXAMPLE"
        assert rule.name == "Example Rule"
        assert rule.category == "test"
        assert rule.default_severity == Severity.MEDIUM

    def test_rule_default_properties(self):
        """Test default property values for a rule."""

        class MinimalRule(BaseRule):
            @property
            def rule_id(self) -> str:
                return "TEST.MINIMAL"

            @property
            def name(self) -> str:
                return "Minimal Rule"

            @property
            def category(self) -> str:
                return "test"

            @property
            def default_severity(self) -> Severity:
                return Severity.LOW

            def check(self, context: RuleContext) -> list[Finding]:
                return []

        rule = MinimalRule()
        # Check default values
        assert rule.triggers == [
            Trigger.ON_WRITE,
            Trigger.ON_STOP,
            Trigger.ON_COMMIT,
        ]
        assert rule.supported_languages is None  # All languages
        assert rule.is_fast is True
        assert rule.can_auto_fix() is False
        assert "TEST.MINIMAL" in rule.description

    def test_rule_create_finding_helper(self):
        """Test the _create_finding helper method."""

        class FindingRule(BaseRule):
            @property
            def rule_id(self) -> str:
                return "TEST.FINDING"

            @property
            def name(self) -> str:
                return "Finding Rule"

            @property
            def category(self) -> str:
                return "test"

            @property
            def default_severity(self) -> Severity:
                return Severity.HIGH

            def check(self, context: RuleContext) -> list[Finding]:
                return [
                    self._create_finding(
                        summary="Test finding",
                        file_path=str(context.file_path),
                        line_number=1,
                    )
                ]

        rule = FindingRule()
        context = RuleContext(
            file_path=Path("test.py"),
            content="test",
            language="python",
        )
        findings = rule.check(context)
        assert len(findings) == 1
        assert findings[0].rule_id == "TEST.FINDING"
        assert findings[0].severity == Severity.HIGH
        assert findings[0].summary == "Test finding"

    def test_rule_with_auto_fix(self):
        """Test a rule that supports auto-fix."""

        class FixableRule(BaseRule):
            @property
            def rule_id(self) -> str:
                return "TEST.FIXABLE"

            @property
            def name(self) -> str:
                return "Fixable Rule"

            @property
            def category(self) -> str:
                return "test"

            @property
            def default_severity(self) -> Severity:
                return Severity.LOW

            def check(self, context: RuleContext) -> list[Finding]:
                return []

            def can_auto_fix(self) -> bool:
                return True

        rule = FixableRule()
        assert rule.can_auto_fix() is True
