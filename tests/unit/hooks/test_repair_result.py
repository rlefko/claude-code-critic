"""Unit tests for repair check result."""

import json
import time

import pytest

from claude_indexer.hooks.fix_generator import FixSuggestion
from claude_indexer.hooks.repair_result import RepairCheckResult
from claude_indexer.hooks.repair_session import RepairSession
from claude_indexer.hooks.stop_check import StopCheckResult
from claude_indexer.rules.base import Finding, Severity
from claude_indexer.rules.fix import AutoFix


class TestRepairCheckResult:
    """Tests for RepairCheckResult."""

    @pytest.fixture
    def sample_findings(self):
        """Create sample findings."""
        return [
            Finding(
                rule_id="TEST.CRITICAL",
                severity=Severity.CRITICAL,
                summary="Critical issue",
                file_path="test.py",
                line_number=10,
                remediation_hints=["Fix the critical issue"],
            ),
            Finding(
                rule_id="TEST.HIGH",
                severity=Severity.HIGH,
                summary="High issue",
                file_path="test.py",
                line_number=20,
                remediation_hints=["Fix the high issue"],
            ),
        ]

    @pytest.fixture
    def base_result(self, sample_findings):
        """Create a base stop check result."""
        return StopCheckResult(
            findings=sample_findings,
            execution_time_ms=150.0,
            rules_executed=5,
            files_checked=3,
            should_block=True,
        )

    @pytest.fixture
    def session(self):
        """Create a repair session."""
        return RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=1,
            max_attempts=3,
            created_at=time.time(),
            last_check_at=time.time(),
        )

    @pytest.fixture
    def repair_result(self, base_result, session):
        """Create a repair check result."""
        return RepairCheckResult(
            base_result=base_result,
            session=session,
            fix_suggestions=[],
            is_same_issue=True,
        )

    def test_properties(self, repair_result):
        """Test property accessors."""
        assert repair_result.should_block is True
        assert repair_result.attempt_number == 1
        assert repair_result.remaining_attempts == 2
        assert len(repair_result.findings) == 2

    def test_should_escalate_not_at_max(self, repair_result):
        """Test should_escalate before max attempts."""
        assert not repair_result.should_escalate

    def test_should_escalate_at_max(self, base_result):
        """Test should_escalate at max attempts."""
        session = RepairSession(
            session_id="test123",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        assert result.should_escalate

    def test_should_escalate_different_issue(self, base_result):
        """Test should_escalate with different findings."""
        session = RepairSession(
            session_id="test123",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=False,  # Different issue, don't escalate
        )

        assert not result.should_escalate

    def test_to_dict_blocked(self, repair_result):
        """Test JSON serialization of blocked result."""
        data = repair_result.to_dict()

        assert data["status"] == "blocked"
        assert data["should_block"] is True
        assert "repair_context" in data
        assert data["repair_context"]["session_id"] == "test123"
        assert data["repair_context"]["attempt_number"] == 1
        assert data["repair_context"]["remaining_attempts"] == 2
        assert data["repair_context"]["should_escalate"] is False
        assert data["escalation"] is None
        assert "instructions" in data

    def test_to_dict_escalated(self, base_result):
        """Test JSON serialization of escalated result."""
        session = RepairSession(
            session_id="test123",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        data = result.to_dict()

        assert data["status"] == "escalated"
        assert data["repair_context"]["should_escalate"] is True
        assert data["escalation"] is not None
        assert data["escalation"]["reason"] == "max_retries_exceeded"
        assert "message_for_user" in data["escalation"]
        assert "message_for_claude" in data["escalation"]

    def test_to_dict_with_fix_suggestions(self, base_result, session, sample_findings):
        """Test JSON serialization with fix suggestions."""
        suggestion = FixSuggestion(
            finding=sample_findings[0],
            action="auto_available",
            description="Auto fix available",
            confidence=0.9,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            fix_suggestions=[suggestion],
            is_same_issue=True,
        )

        data = result.to_dict()

        assert len(data["fix_suggestions"]) == 1
        assert data["fix_suggestions"][0]["action"] == "auto_available"

    def test_to_json(self, repair_result):
        """Test JSON string conversion."""
        json_str = repair_result.to_json()
        data = json.loads(json_str)

        assert data["status"] == "blocked"

    def test_to_json_with_indent(self, repair_result):
        """Test JSON string with indentation."""
        json_str = repair_result.to_json(indent=2)

        assert "\n" in json_str
        assert "  " in json_str

    def test_instructions_not_blocking(self, session):
        """Test instructions when not blocking."""
        base = StopCheckResult(
            findings=[],
            should_block=False,
        )

        result = RepairCheckResult(
            base_result=base,
            session=session,
            is_same_issue=True,
        )

        assert result._get_instructions() == "No blocking issues found."

    def test_instructions_last_attempt(self, base_result):
        """Test instructions on last attempt."""
        session = RepairSession(
            session_id="test",
            project_path="/test",
            findings_hash="abc",
            attempt_count=2,  # One attempt left
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        instructions = result._get_instructions()
        assert "LAST attempt" in instructions

    def test_instructions_multiple_remaining(self, repair_result):
        """Test instructions with multiple attempts remaining."""
        instructions = repair_result._get_instructions()
        assert "2 attempts remaining" in instructions

    def test_format_for_claude_blocked(self, repair_result):
        """Test format_for_claude for blocked result."""
        output = repair_result.format_for_claude()

        assert "=== QUALITY CHECK BLOCKED ===" in output
        assert "Repair attempt 1 of 3" in output
        assert "Remaining attempts: 2" in output
        assert "TEST.CRITICAL" in output
        assert "TEST.HIGH" in output
        assert "Critical issue" in output
        assert "2 attempts remaining" in output

    def test_format_for_claude_escalated(self, base_result):
        """Test format_for_claude for escalated result."""
        session = RepairSession(
            session_id="test",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        output = result.format_for_claude()

        assert "=== REPAIR ESCALATED TO USER ===" in output
        assert "unable to fix" in output

    def test_format_for_claude_with_auto_fix(
        self, base_result, session, sample_findings
    ):
        """Test format_for_claude includes auto-fix info."""
        auto_fix = AutoFix(
            finding=sample_findings[0],
            old_code="old",
            new_code="new",
            line_start=10,
            line_end=10,
            description="Replace code",
        )

        suggestion = FixSuggestion(
            finding=sample_findings[0],
            auto_fix=auto_fix,
            action="auto_available",
            description="Replace code",
            confidence=0.9,
            code_preview="- old\n+ new",
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            fix_suggestions=[suggestion],
            is_same_issue=True,
        )

        output = result.format_for_claude()

        assert "Fix available" in output
        assert "90%" in output
        assert "Replace code" in output

    def test_format_escalation_message(self, base_result):
        """Test escalation message format."""
        session = RepairSession(
            session_id="test",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        message = result.format_escalation_message()

        assert "Claude attempted to fix" in message
        assert "3 times" in message
        assert "TEST.CRITICAL" in message
        assert "TEST.HIGH" in message
        assert "manual attention" in message

    def test_get_suggestion_for_finding(self, base_result, session, sample_findings):
        """Test getting suggestion for specific finding."""
        suggestion = FixSuggestion(
            finding=sample_findings[0],
            action="auto_available",
            description="Fix",
            confidence=0.9,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            fix_suggestions=[suggestion],
            is_same_issue=True,
        )

        found = result._get_suggestion_for_finding(sample_findings[0])
        assert found is suggestion

        # Different finding should return None
        not_found = result._get_suggestion_for_finding(sample_findings[1])
        assert not_found is None


class TestRepairCheckResultIntegration:
    """Integration tests for RepairCheckResult."""

    def test_full_json_cycle(self):
        """Test full JSON serialization/parsing cycle."""
        findings = [
            Finding(
                rule_id="TEST.ISSUE",
                severity=Severity.HIGH,
                summary="Test issue",
                file_path="test.py",
                line_number=10,
                remediation_hints=["Fix it"],
            ),
        ]

        base_result = StopCheckResult(
            findings=findings,
            execution_time_ms=100.0,
            rules_executed=3,
            files_checked=2,
            should_block=True,
        )

        session = RepairSession(
            session_id="test123",
            project_path="/test",
            findings_hash="abc",
            attempt_count=2,
        )

        suggestion = FixSuggestion(
            finding=findings[0],
            action="manual_required",
            description="Manual fix needed",
            confidence=0.75,
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            fix_suggestions=[suggestion],
            is_same_issue=True,
        )

        # Serialize to JSON
        json_str = result.to_json()

        # Parse JSON
        data = json.loads(json_str)

        # Verify structure
        assert data["status"] == "blocked"
        assert data["repair_context"]["attempt_number"] == 2
        assert data["repair_context"]["remaining_attempts"] == 1
        assert len(data["findings"]) == 1
        assert len(data["fix_suggestions"]) == 1
        assert data["escalation"] is None

    def test_escalation_json_structure(self):
        """Test JSON structure for escalated result."""
        findings = [
            Finding(
                rule_id="TEST.CRITICAL",
                severity=Severity.CRITICAL,
                summary="Critical issue",
                file_path="test.py",
                line_number=5,
            ),
        ]

        base_result = StopCheckResult(
            findings=findings,
            should_block=True,
        )

        session = RepairSession(
            session_id="test",
            project_path="/test",
            findings_hash="abc",
            attempt_count=3,  # Max reached
        )

        result = RepairCheckResult(
            base_result=base_result,
            session=session,
            is_same_issue=True,
        )

        data = result.to_dict()

        # Verify escalation structure
        assert data["status"] == "escalated"
        assert data["escalation"]["reason"] == "max_retries_exceeded"
        assert data["escalation"]["attempts_made"] == 3
        assert isinstance(data["escalation"]["message_for_user"], str)
        assert isinstance(data["escalation"]["message_for_claude"], str)
