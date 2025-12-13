"""Unit tests for repair session management."""

import time

import pytest

from claude_indexer.hooks.repair_session import (
    RepairSession,
    RepairSessionManager,
)
from claude_indexer.rules.base import Finding, Severity


class TestRepairSession:
    """Tests for RepairSession dataclass."""

    def test_create_session(self):
        """Test creating a new session."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=0,
        )

        assert session.session_id == "test123"
        assert session.project_path == "/test/project"
        assert session.findings_hash == "abc123"
        assert session.attempt_count == 0
        assert session.max_attempts == 3

    def test_is_expired_fresh_session(self):
        """Test fresh session is not expired."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            last_check_at=time.time(),
        )

        assert not session.is_expired

    def test_is_expired_old_session(self):
        """Test old session is expired."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            last_check_at=time.time() - 3600,  # 1 hour ago
        )

        assert session.is_expired

    def test_can_retry_new_session(self):
        """Test new session can retry."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=0,
        )

        assert session.can_retry
        assert not session.should_escalate

    def test_can_retry_after_attempts(self):
        """Test session after attempts."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=2,
        )

        assert session.can_retry
        assert not session.should_escalate
        assert session.remaining_attempts == 1

    def test_should_escalate_at_max(self):
        """Test session should escalate at max attempts."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=3,
        )

        assert not session.can_retry
        assert session.should_escalate
        assert session.remaining_attempts == 0

    def test_to_dict(self):
        """Test JSON serialization."""
        session = RepairSession(
            session_id="test123",
            project_path="/test/project",
            findings_hash="abc123",
            attempt_count=1,
            created_at=1000.0,
            last_check_at=1001.0,
        )

        data = session.to_dict()

        assert data["session_id"] == "test123"
        assert data["project_path"] == "/test/project"
        assert data["findings_hash"] == "abc123"
        assert data["attempt_count"] == 1
        assert data["created_at"] == 1000.0
        assert data["last_check_at"] == 1001.0

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "session_id": "test123",
            "project_path": "/test/project",
            "findings_hash": "abc123",
            "attempt_count": 2,
            "max_attempts": 3,
            "created_at": 1000.0,
            "last_check_at": 1001.0,
        }

        session = RepairSession.from_dict(data)

        assert session.session_id == "test123"
        assert session.attempt_count == 2


class TestRepairSessionManager:
    """Tests for RepairSessionManager."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        return tmp_path / "test_project"

    @pytest.fixture
    def manager(self, temp_project):
        """Create a manager for testing."""
        temp_project.mkdir(parents=True, exist_ok=True)
        return RepairSessionManager(temp_project)

    @pytest.fixture
    def sample_findings(self):
        """Create sample findings for testing."""
        return [
            Finding(
                rule_id="TEST.RULE_1",
                severity=Severity.HIGH,
                summary="Test issue 1",
                file_path="test.py",
                line_number=10,
            ),
            Finding(
                rule_id="TEST.RULE_2",
                severity=Severity.MEDIUM,
                summary="Test issue 2",
                file_path="test.py",
                line_number=20,
            ),
        ]

    def test_compute_findings_hash_empty(self):
        """Test hash for empty findings."""
        hash_val = RepairSessionManager.compute_findings_hash([])
        assert hash_val == "empty"

    def test_compute_findings_hash_consistent(self, sample_findings):
        """Test hash is consistent for same findings."""
        hash1 = RepairSessionManager.compute_findings_hash(sample_findings)
        hash2 = RepairSessionManager.compute_findings_hash(sample_findings)

        assert hash1 == hash2
        assert len(hash1) == 12  # 12-char hash

    def test_compute_findings_hash_order_independent(self, sample_findings):
        """Test hash is order-independent."""
        hash1 = RepairSessionManager.compute_findings_hash(sample_findings)
        hash2 = RepairSessionManager.compute_findings_hash(
            list(reversed(sample_findings))
        )

        assert hash1 == hash2

    def test_compute_findings_hash_different(self, sample_findings):
        """Test different findings produce different hash."""
        hash1 = RepairSessionManager.compute_findings_hash(sample_findings)

        different_findings = [
            Finding(
                rule_id="DIFFERENT.RULE",
                severity=Severity.HIGH,
                summary="Different issue",
                file_path="other.py",
                line_number=5,
            ),
        ]
        hash2 = RepairSessionManager.compute_findings_hash(different_findings)

        assert hash1 != hash2

    def test_get_or_create_session_new(self, manager, sample_findings):
        """Test creating a new session."""
        session = manager.get_or_create_session(sample_findings)

        assert session is not None
        assert session.attempt_count == 0
        assert not session.is_expired

    def test_get_or_create_session_existing(self, manager, sample_findings):
        """Test getting existing session."""
        # Create and save a session
        session1 = manager.get_or_create_session(sample_findings)
        session1 = manager.record_attempt(session1)

        # Get the same session
        session2 = manager.get_or_create_session(sample_findings)

        assert session2.session_id == session1.session_id
        assert session2.attempt_count == 1

    def test_record_attempt(self, manager, sample_findings):
        """Test recording an attempt."""
        session = manager.get_or_create_session(sample_findings)
        assert session.attempt_count == 0

        session = manager.record_attempt(session)
        assert session.attempt_count == 1

        session = manager.record_attempt(session)
        assert session.attempt_count == 2

    def test_clear_session(self, manager, sample_findings):
        """Test clearing a session."""
        session = manager.get_or_create_session(sample_findings)
        session = manager.record_attempt(session)

        # Clear it
        manager.clear_session(session.session_id)

        # New session should start fresh
        new_session = manager.get_or_create_session(sample_findings)
        assert new_session.attempt_count == 0

    def test_cleanup_expired(self, manager, sample_findings):
        """Test cleanup of expired sessions."""
        session = manager.get_or_create_session(sample_findings)
        session = manager.record_attempt(session)

        # Manually expire the session
        state = manager._load_state()
        state["sessions"][session.session_id]["last_check_at"] = (
            time.time() - 7200  # 2 hours ago
        )
        manager._save_state(state)

        # Cleanup
        removed = manager.cleanup_expired()
        assert removed == 1

        # Session should be gone
        new_session = manager.get_or_create_session(sample_findings)
        assert new_session.attempt_count == 0

    def test_state_file_persistence(self, manager, sample_findings):
        """Test state persists to disk."""
        session = manager.get_or_create_session(sample_findings)
        session = manager.record_attempt(session)
        session = manager.record_attempt(session)

        # Create new manager
        new_manager = RepairSessionManager(manager.project_path)
        loaded_session = new_manager.get_or_create_session(sample_findings)

        assert loaded_session.session_id == session.session_id
        assert loaded_session.attempt_count == 2

    def test_state_file_corrupted(self, manager, sample_findings):
        """Test handling of corrupted state file."""
        # Write invalid JSON
        manager._ensure_state_dir()
        with open(manager.state_file, "w") as f:
            f.write("invalid json{{{")

        # Should recover gracefully
        session = manager.get_or_create_session(sample_findings)
        assert session.attempt_count == 0

    def test_get_all_sessions(self, manager, sample_findings):
        """Test getting all sessions."""
        # Create two sessions with different findings
        session1 = manager.get_or_create_session(sample_findings)
        manager.record_attempt(session1)

        other_findings = [
            Finding(
                rule_id="OTHER.RULE",
                severity=Severity.HIGH,
                summary="Other issue",
                file_path="other.py",
                line_number=1,
            ),
        ]
        session2 = manager.get_or_create_session(other_findings)
        manager.record_attempt(session2)

        sessions = manager.get_all_sessions()
        assert len(sessions) == 2

    def test_session_expires_and_resets(self, manager, sample_findings):
        """Test session resets when expired."""
        session = manager.get_or_create_session(sample_findings)
        session = manager.record_attempt(session)
        session = manager.record_attempt(session)
        assert session.attempt_count == 2

        # Manually expire
        state = manager._load_state()
        state["sessions"][session.session_id]["last_check_at"] = time.time() - 7200
        manager._save_state(state)

        # New session should start fresh
        new_session = manager.get_or_create_session(sample_findings)
        assert new_session.attempt_count == 0


class TestRepairSessionIntegration:
    """Integration tests for repair session flow."""

    def test_full_repair_cycle(self, tmp_path):
        """Test complete repair cycle from fresh to escalation."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        manager = RepairSessionManager(project_path)

        findings = [
            Finding(
                rule_id="TEST.ISSUE",
                severity=Severity.HIGH,
                summary="Test issue",
                file_path="test.py",
                line_number=1,
            ),
        ]

        # Attempt 1
        session = manager.get_or_create_session(findings)
        assert session.can_retry
        assert not session.should_escalate
        session = manager.record_attempt(session)
        assert session.attempt_count == 1

        # Attempt 2
        session = manager.get_or_create_session(findings)
        assert session.can_retry
        session = manager.record_attempt(session)
        assert session.attempt_count == 2

        # Attempt 3
        session = manager.get_or_create_session(findings)
        assert session.can_retry
        session = manager.record_attempt(session)
        assert session.attempt_count == 3

        # Should escalate now
        session = manager.get_or_create_session(findings)
        assert not session.can_retry
        assert session.should_escalate

    def test_different_findings_reset(self, tmp_path):
        """Test that different findings start a new session."""
        project_path = tmp_path / "project"
        project_path.mkdir()

        manager = RepairSessionManager(project_path)

        findings1 = [
            Finding(
                rule_id="TEST.ISSUE_1",
                severity=Severity.HIGH,
                summary="Test issue 1",
                file_path="test.py",
                line_number=1,
            ),
        ]

        findings2 = [
            Finding(
                rule_id="TEST.ISSUE_2",
                severity=Severity.HIGH,
                summary="Test issue 2",
                file_path="test.py",
                line_number=2,
            ),
        ]

        # Multiple attempts on findings1
        session1 = manager.get_or_create_session(findings1)
        manager.record_attempt(session1)
        manager.record_attempt(manager.get_or_create_session(findings1))

        # findings2 should start fresh
        session2 = manager.get_or_create_session(findings2)
        assert session2.attempt_count == 0
        assert session2.session_id != session1.session_id
