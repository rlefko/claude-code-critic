"""Unit tests for the session_start module."""

import json
import time
from unittest.mock import patch

import pytest

from claude_indexer.doctor.types import CheckStatus
from claude_indexer.hooks.session_start import (
    IndexFreshnessResult,
    SessionStartExecutor,
    SessionStartResult,
    run_session_start,
)


class TestIndexFreshnessResult:
    """Tests for IndexFreshnessResult dataclass."""

    def test_fresh_index(self):
        """Fresh index should have is_fresh=True."""
        result = IndexFreshnessResult(is_fresh=True)

        assert result.is_fresh is True
        assert result.suggestion is None
        assert result.commits_behind == 0

    def test_stale_by_time(self):
        """Index older than threshold should be stale."""
        result = IndexFreshnessResult(
            is_fresh=False,
            hours_since_index=48.0,
            last_indexed_time=time.time() - (48 * 3600),
            suggestion="Run: claude-indexer index -c test",
        )

        assert result.is_fresh is False
        assert result.hours_since_index == 48.0
        assert "index" in result.suggestion.lower()

    def test_stale_by_commits(self):
        """Index with new commits should be stale."""
        result = IndexFreshnessResult(
            is_fresh=False,
            commits_behind=5,
            last_indexed_commit="abc123",
            current_commit="def456",
            suggestion="Run: claude-indexer index -c test",
        )

        assert result.is_fresh is False
        assert result.commits_behind == 5
        assert result.last_indexed_commit != result.current_commit

    def test_to_dict(self):
        """Test JSON serialization."""
        result = IndexFreshnessResult(
            is_fresh=False,
            last_indexed_time=1234567890.0,
            last_indexed_commit="abc123",
            current_commit="def456",
            hours_since_index=24.5,
            commits_behind=3,
            suggestion="Run indexing",
        )

        d = result.to_dict()

        assert d["is_fresh"] is False
        assert d["last_indexed_time"] == 1234567890.0
        assert d["last_indexed_commit"] == "abc123"
        assert d["current_commit"] == "def456"
        assert d["hours_since_index"] == 24.5
        assert d["commits_behind"] == 3
        assert d["suggestion"] == "Run indexing"


class TestSessionStartResult:
    """Tests for SessionStartResult dataclass."""

    def test_empty_result(self):
        """Test empty result with defaults."""
        result = SessionStartResult()

        assert result.qdrant_status == CheckStatus.SKIP
        assert result.collection_status == CheckStatus.SKIP
        assert result.git_branch is None
        assert result.uncommitted_files == 0
        assert result.recent_commits == []
        assert result.error is None

    def test_result_with_all_healthy(self):
        """Test result with all healthy checks."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.PASS,
            qdrant_message="Connected (localhost:6333)",
            collection_status=CheckStatus.PASS,
            collection_message="Found",
            collection_vector_count=1000,
            index_freshness=IndexFreshnessResult(is_fresh=True),
            git_branch="main",
            uncommitted_files=0,
            recent_commits=["Add feature", "Fix bug"],
            execution_time_ms=500.0,
        )

        assert result.qdrant_status == CheckStatus.PASS
        assert result.collection_status == CheckStatus.PASS
        assert result.collection_vector_count == 1000
        assert result.index_freshness.is_fresh is True
        assert result.git_branch == "main"
        assert not result.has_warnings()

    def test_has_warnings_qdrant_fail(self):
        """Test has_warnings with Qdrant failure."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.FAIL,
            qdrant_message="Connection refused",
        )

        assert result.has_warnings() is True

    def test_has_warnings_stale_index(self):
        """Test has_warnings with stale index."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.PASS,
            collection_status=CheckStatus.PASS,
            index_freshness=IndexFreshnessResult(is_fresh=False),
        )

        assert result.has_warnings() is True

    def test_to_dict(self):
        """Test JSON serialization."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.PASS,
            qdrant_message="Connected",
            collection_status=CheckStatus.PASS,
            collection_message="Found",
            collection_vector_count=500,
            index_freshness=IndexFreshnessResult(is_fresh=True),
            git_branch="feature",
            uncommitted_files=2,
            recent_commits=["Commit 1"],
            execution_time_ms=800.0,
        )

        d = result.to_dict()

        assert d["status"] == "ok"
        assert d["qdrant"]["status"] == "pass"
        assert d["collection"]["vector_count"] == 500
        assert d["git"]["branch"] == "feature"
        assert d["git"]["uncommitted_files"] == 2
        assert d["execution_time_ms"] == 800.0

    def test_to_json(self):
        """Test JSON string output."""
        result = SessionStartResult(execution_time_ms=300.0)

        json_str = result.to_json()
        parsed = json.loads(json_str)

        assert "status" in parsed
        assert "execution_time_ms" in parsed

    def test_format_welcome_message_healthy(self):
        """Test welcome message formatting with healthy status."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.PASS,
            qdrant_message="Connected (localhost:6333)",
            collection_status=CheckStatus.PASS,
            collection_message="Found",
            collection_vector_count=1000,
            index_freshness=IndexFreshnessResult(is_fresh=True),
            git_branch="main",
            uncommitted_files=0,
            recent_commits=["Add feature", "Fix bug"],
            execution_time_ms=500.0,
        )

        message = result.format_welcome_message("test-project")

        assert "Session Start" in message
        assert "[OK]" in message
        assert "test-project" in message
        assert "1,000" in message
        assert "main" in message
        assert "Memory-First" in message
        assert "500ms" in message

    def test_format_welcome_message_warnings(self):
        """Test welcome message formatting with warnings."""
        result = SessionStartResult(
            qdrant_status=CheckStatus.PASS,
            qdrant_message="Connected",
            collection_status=CheckStatus.WARN,
            collection_message="Not found",
            index_freshness=IndexFreshnessResult(
                is_fresh=False,
                hours_since_index=30.0,
                commits_behind=5,
                suggestion="Run: claude-indexer index -c project",
            ),
            execution_time_ms=800.0,
        )

        message = result.format_welcome_message("project")

        assert "[WARN]" in message
        assert "stale" in message.lower()
        assert "30h" in message or "30" in message
        assert "5" in message  # commits behind


class TestSessionStartExecutor:
    """Tests for SessionStartExecutor."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        project = tmp_path / "test-project"
        project.mkdir()
        (project / ".git").mkdir()
        (project / ".claude-indexer").mkdir()
        return project

    def test_execute_graceful_degradation(self, temp_project):
        """Execute should return result even if Qdrant unavailable."""
        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(executor, "_check_qdrant") as mock_qdrant:
            mock_qdrant.return_value = (CheckStatus.FAIL, "Connection refused", 0)
            result = executor.execute(timeout_ms=1000)

        assert isinstance(result, SessionStartResult)
        assert result.qdrant_status == CheckStatus.FAIL
        assert result.error is None  # No fatal error

    def test_check_index_freshness_no_state_file(self, temp_project):
        """Missing state file should indicate no index."""
        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        result = executor._check_index_freshness()

        assert result.is_fresh is False
        assert "No index found" in result.suggestion

    def test_check_index_freshness_stale_by_time(self, temp_project):
        """Index older than 24h should be marked stale."""
        # Create state file with old timestamp
        state_file = temp_project / ".claude-indexer" / "test-collection.json"
        old_time = time.time() - (30 * 3600)  # 30 hours ago
        state_file.write_text(
            json.dumps(
                {
                    "_last_indexed_time": old_time,
                    "_last_indexed_commit": "abc123",
                }
            )
        )

        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(executor, "_get_current_commit", return_value="abc123"):
            result = executor._check_index_freshness()

        assert result.is_fresh is False
        assert result.hours_since_index >= 30

    def test_check_index_freshness_stale_by_commits(self, temp_project):
        """New commits since last index should mark as stale."""
        state_file = temp_project / ".claude-indexer" / "test-collection.json"
        state_file.write_text(
            json.dumps(
                {
                    "_last_indexed_time": time.time(),  # Recent
                    "_last_indexed_commit": "old-sha",
                }
            )
        )

        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(executor, "_get_current_commit", return_value="new-sha"):
            with patch.object(executor, "_count_commits_since", return_value=3):
                result = executor._check_index_freshness()

        assert result.is_fresh is False
        assert result.commits_behind == 3

    def test_check_index_freshness_fresh(self, temp_project):
        """Recent index with no new commits should be fresh."""
        state_file = temp_project / ".claude-indexer" / "test-collection.json"
        state_file.write_text(
            json.dumps(
                {
                    "_last_indexed_time": time.time(),  # Just now
                    "_last_indexed_commit": "current-sha",
                }
            )
        )

        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(executor, "_get_current_commit", return_value="current-sha"):
            with patch.object(executor, "_count_commits_since", return_value=0):
                result = executor._check_index_freshness()

        assert result.is_fresh is True

    def test_get_git_context_in_git_repo(self, temp_project):
        """Git context should be extracted in git repo."""
        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(
            executor,
            "_run_git_command",
            side_effect=["main", "M file.py\nA new.py", "Commit 1\nCommit 2"],
        ):
            branch, uncommitted, commits = executor._get_git_context()

        assert branch == "main"
        assert uncommitted == 2
        assert len(commits) == 2

    def test_execute_collects_all_data(self, temp_project):
        """Execute should collect all health data."""
        executor = SessionStartExecutor(
            project_path=temp_project,
            collection_name="test-collection",
        )

        with patch.object(executor, "_check_qdrant") as mock_qdrant:
            mock_qdrant.return_value = (CheckStatus.PASS, "Connected", 5)
            with patch.object(executor, "_check_collection") as mock_collection:
                mock_collection.return_value = (CheckStatus.PASS, "Found", 1000)
                with patch.object(executor, "_check_index_freshness") as mock_fresh:
                    mock_fresh.return_value = IndexFreshnessResult(is_fresh=True)
                    with patch.object(executor, "_get_git_context") as mock_git:
                        mock_git.return_value = ("main", 0, ["Commit 1"])
                        result = executor.execute()

        assert result.qdrant_status == CheckStatus.PASS
        assert result.collection_status == CheckStatus.PASS
        assert result.collection_vector_count == 1000
        assert result.index_freshness.is_fresh is True
        assert result.git_branch == "main"
        assert result.execution_time_ms > 0


class TestRunSessionStart:
    """Tests for run_session_start function."""

    def test_returns_exit_code_0_on_healthy(self, tmp_path):
        """Healthy system should return exit code 0."""
        with patch(
            "claude_indexer.hooks.session_start.SessionStartExecutor"
        ) as MockExec:
            mock_result = SessionStartResult(
                qdrant_status=CheckStatus.PASS,
                collection_status=CheckStatus.PASS,
                index_freshness=IndexFreshnessResult(is_fresh=True),
            )
            MockExec.return_value.execute.return_value = mock_result

            result, exit_code = run_session_start(
                project_path=tmp_path,
                collection_name="test",
            )

        assert exit_code == 0

    def test_returns_exit_code_1_on_warnings(self, tmp_path):
        """Warnings should return exit code 1."""
        with patch(
            "claude_indexer.hooks.session_start.SessionStartExecutor"
        ) as MockExec:
            mock_result = SessionStartResult(
                qdrant_status=CheckStatus.PASS,
                collection_status=CheckStatus.WARN,
                index_freshness=IndexFreshnessResult(is_fresh=False),
            )
            MockExec.return_value.execute.return_value = mock_result

            result, exit_code = run_session_start(
                project_path=tmp_path,
                collection_name="test",
            )

        assert exit_code == 1

    def test_never_returns_exit_code_2(self, tmp_path):
        """Session start should never block (never exit code 2)."""
        with patch(
            "claude_indexer.hooks.session_start.SessionStartExecutor"
        ) as MockExec:
            mock_result = SessionStartResult(
                qdrant_status=CheckStatus.FAIL,
                collection_status=CheckStatus.FAIL,
                error="Everything failed",
            )
            MockExec.return_value.execute.return_value = mock_result

            result, exit_code = run_session_start(
                project_path=tmp_path,
                collection_name="test",
            )

        assert exit_code in (0, 1)  # Never 2

    def test_passes_timeout_to_executor(self, tmp_path):
        """Timeout should be passed to executor."""
        with patch(
            "claude_indexer.hooks.session_start.SessionStartExecutor"
        ) as MockExec:
            mock_result = SessionStartResult()
            mock_instance = MockExec.return_value
            mock_instance.execute.return_value = mock_result

            run_session_start(
                project_path=tmp_path,
                collection_name="test",
                timeout_ms=3000,
            )

            mock_instance.execute.assert_called_once_with(timeout_ms=3000)
