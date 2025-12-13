"""
Session start executor for Claude Code Memory.

Runs once at session start to:
1. Verify Qdrant connectivity (graceful degradation)
2. Check index freshness (suggest re-index if stale)
3. Load project-specific configuration
4. Display welcome message with health status

Performance target: <2s total (graceful if services unavailable)
Exit codes: 0 = healthy, 1 = warnings (never blocks)
"""

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config.config_loader import ConfigLoader
from ..doctor.checkers import check_collection_exists, check_qdrant_connection
from ..doctor.types import CheckStatus
from ..session.manager import SessionManager


@dataclass
class IndexFreshnessResult:
    """Result of index freshness check."""

    is_fresh: bool
    last_indexed_time: float | None = None
    last_indexed_commit: str | None = None
    current_commit: str | None = None
    hours_since_index: float | None = None
    commits_behind: int = 0
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "is_fresh": self.is_fresh,
            "last_indexed_time": self.last_indexed_time,
            "last_indexed_commit": self.last_indexed_commit,
            "current_commit": self.current_commit,
            "hours_since_index": self.hours_since_index,
            "commits_behind": self.commits_behind,
            "suggestion": self.suggestion,
        }


@dataclass
class SessionStartResult:
    """Result of session start checks."""

    # Session context (Milestone 5.2)
    session_id: str | None = None
    project_path: str | None = None

    # Health checks
    qdrant_status: CheckStatus = CheckStatus.SKIP
    qdrant_message: str = ""
    collection_status: CheckStatus = CheckStatus.SKIP
    collection_message: str = ""
    collection_vector_count: int = 0

    # Index freshness
    index_freshness: IndexFreshnessResult | None = None

    # Git context
    git_branch: str | None = None
    uncommitted_files: int = 0
    recent_commits: list[str] = field(default_factory=list)

    # Execution
    execution_time_ms: float = 0.0
    error: str | None = None

    def has_warnings(self) -> bool:
        """Check if there are any warnings in the result."""
        if self.qdrant_status in (CheckStatus.WARN, CheckStatus.FAIL):
            return True
        if self.collection_status in (CheckStatus.WARN, CheckStatus.FAIL):
            return True
        return bool(self.index_freshness and not self.index_freshness.is_fresh)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        status = "warn" if self.has_warnings() else "ok"
        return {
            "status": status,
            "session": {
                "session_id": self.session_id,
                "project_path": self.project_path,
            },
            "qdrant": {
                "status": self.qdrant_status.value,
                "message": self.qdrant_message,
            },
            "collection": {
                "status": self.collection_status.value,
                "message": self.collection_message,
                "vector_count": self.collection_vector_count,
            },
            "index_freshness": (
                self.index_freshness.to_dict() if self.index_freshness else None
            ),
            "git": {
                "branch": self.git_branch,
                "uncommitted_files": self.uncommitted_files,
                "recent_commits": self.recent_commits,
            },
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def format_welcome_message(self, collection_name: str) -> str:
        """Format human-readable welcome message with status indicators."""
        lines = ["", "=== Claude Code Memory - Session Start ===", ""]

        # Session info (Milestone 5.2)
        if self.session_id:
            lines.append(f"Session: {self.session_id}")
            lines.append("")

        # System Health section
        lines.append("System Health:")

        # Qdrant status
        qdrant_indicator = self._status_indicator(self.qdrant_status)
        lines.append(f"  {qdrant_indicator} Qdrant: {self.qdrant_message}")

        # Collection status
        collection_indicator = self._status_indicator(self.collection_status)
        if self.collection_vector_count > 0:
            lines.append(
                f"  {collection_indicator} Collection '{collection_name}' "
                f"({self.collection_vector_count:,} vectors)"
            )
        else:
            lines.append(
                f"  {collection_indicator} Collection '{collection_name}': "
                f"{self.collection_message}"
            )

        # Index freshness
        if self.index_freshness:
            if self.index_freshness.is_fresh:
                lines.append("  [OK] Index is current")
            else:
                # Build reason string
                reasons = []
                if (
                    self.index_freshness.hours_since_index
                    and self.index_freshness.hours_since_index > 24
                ):
                    reasons.append(
                        f"last indexed {self.index_freshness.hours_since_index:.0f}h ago"
                    )
                if self.index_freshness.commits_behind > 0:
                    reasons.append(
                        f"{self.index_freshness.commits_behind} new commit(s)"
                    )

                reason_str = ", ".join(reasons) if reasons else "needs update"
                lines.append(f"  [WARN] Index stale ({reason_str})")
                if self.index_freshness.suggestion:
                    lines.append(f"         {self.index_freshness.suggestion}")

        # Git Context section
        lines.append("")
        lines.append("Git Context:")

        if self.git_branch:
            lines.append(f"  Branch: {self.git_branch}")
        else:
            lines.append("  Branch: (not a git repo)")

        if self.uncommitted_files > 0:
            lines.append(f"  Uncommitted: {self.uncommitted_files} file(s)")

        if self.recent_commits:
            lines.append("  Recent commits:")
            for commit in self.recent_commits[:3]:
                # Truncate long commit messages
                msg = commit[:60] + "..." if len(commit) > 60 else commit
                lines.append(f"    - {msg}")

        # Memory-First Reminder
        lines.append("")
        lines.append("Memory-First Reminder:")
        mcp_prefix = f"mcp__{collection_name}-memory__"
        lines.append(f"  Use {mcp_prefix}search_similar() before reading files")
        lines.append(f"  Use {mcp_prefix}read_graph() to understand relationships")

        # Execution time
        lines.append("")
        lines.append(f"Ready in {self.execution_time_ms:.0f}ms")
        lines.append("")

        return "\n".join(lines)

    def _status_indicator(self, status: CheckStatus) -> str:
        """Convert CheckStatus to display indicator."""
        indicators = {
            CheckStatus.PASS: "[OK]",
            CheckStatus.WARN: "[WARN]",
            CheckStatus.FAIL: "[FAIL]",
            CheckStatus.SKIP: "[SKIP]",
        }
        return indicators.get(status, "[?]")


class SessionStartExecutor:
    """Executor for session start health checks and context.

    Unlike other hooks, SessionStart never blocks (always informational).
    It uses graceful degradation - if services are unavailable, it reports
    status but allows the session to proceed.

    Example usage:
        executor = SessionStartExecutor(
            project_path=Path("/path/to/project"),
            collection_name="my-project",
        )
        result = executor.execute()
        print(result.format_welcome_message("my-project"))
    """

    STALE_THRESHOLD_HOURS = 24

    def __init__(
        self,
        project_path: Path,
        collection_name: str,
        config_loader: ConfigLoader | None = None,
    ):
        """Initialize session start executor.

        Args:
            project_path: Root directory of the project
            collection_name: Name of the Qdrant collection
            config_loader: Optional config loader (creates one if not provided)
        """
        self.project_path = project_path
        self.collection_name = collection_name
        self.config_loader = config_loader or ConfigLoader()
        self._config: Any | None = None

    def execute(self, timeout_ms: int = 2000) -> SessionStartResult:
        """Execute all session start checks.

        Returns SessionStartResult with health status and context.
        Always returns (never raises) for graceful degradation.

        Args:
            timeout_ms: Total execution timeout (soft limit)

        Returns:
            SessionStartResult with aggregated check results
        """
        start_time = time.time()
        result = SessionStartResult()

        try:
            # Initialize session (Milestone 5.2)
            try:
                session_manager = SessionManager(
                    project_path=self.project_path,
                    collection_name=self.collection_name,
                    config_loader=self.config_loader,
                )
                session_context = session_manager.initialize()
                result.session_id = session_context.session_id
                result.project_path = str(session_context.project_path)
            except Exception:
                # Session initialization is optional - continue without it
                pass

            # Load configuration
            self._load_config()

            # Check Qdrant connectivity
            qdrant_status, qdrant_msg, collection_count = self._check_qdrant()
            result.qdrant_status = qdrant_status
            result.qdrant_message = qdrant_msg

            # Check collection exists
            if qdrant_status == CheckStatus.PASS:
                (
                    result.collection_status,
                    result.collection_message,
                    result.collection_vector_count,
                ) = self._check_collection()
            else:
                result.collection_status = CheckStatus.SKIP
                result.collection_message = "Skipped (Qdrant unavailable)"

            # Check index freshness
            result.index_freshness = self._check_index_freshness()

            # Get git context
            (
                result.git_branch,
                result.uncommitted_files,
                result.recent_commits,
            ) = self._get_git_context()

        except Exception as e:
            result.error = str(e)

        elapsed_ms = (time.time() - start_time) * 1000
        result.execution_time_ms = elapsed_ms

        return result

    def _load_config(self) -> None:
        """Load project configuration."""
        try:
            self._config = self.config_loader.load()
        except Exception:
            # Config loading is optional - continue without it
            self._config = None

    def _check_qdrant(self) -> tuple[CheckStatus, str, int]:
        """Check Qdrant connectivity.

        Returns:
            Tuple of (status, message, collection_count)
        """
        try:
            check_result = check_qdrant_connection(self._config)
            collection_count = (
                check_result.details.get("collection_count", 0)
                if check_result.details
                else 0
            )

            if check_result.status == CheckStatus.PASS:
                url = (
                    check_result.details.get("url", "localhost:6333")
                    if check_result.details
                    else "localhost:6333"
                )
                return CheckStatus.PASS, f"Connected ({url})", collection_count
            else:
                return check_result.status, check_result.message, 0
        except Exception as e:
            return CheckStatus.FAIL, f"Connection failed: {str(e)[:50]}", 0

    def _check_collection(self) -> tuple[CheckStatus, str, int]:
        """Check if collection exists and get stats.

        Returns:
            Tuple of (status, message, vector_count)
        """
        try:
            check_result = check_collection_exists(self._config, self.collection_name)

            if check_result.status == CheckStatus.PASS:
                vector_count = (
                    check_result.details.get("vector_count", 0)
                    if check_result.details
                    else 0
                )
                return CheckStatus.PASS, "Found", vector_count
            elif check_result.status == CheckStatus.WARN:
                return (
                    CheckStatus.WARN,
                    f"Not found - run: claude-indexer index -c {self.collection_name}",
                    0,
                )
            else:
                return check_result.status, check_result.message, 0
        except Exception as e:
            return CheckStatus.FAIL, f"Check failed: {str(e)[:50]}", 0

    def _check_index_freshness(self) -> IndexFreshnessResult:
        """Check if index needs re-indexing.

        Checks:
        1. State file exists
        2. Time since last index (stale if >24h)
        3. Commits since last indexed commit

        Returns:
            IndexFreshnessResult with freshness status
        """
        result = IndexFreshnessResult(is_fresh=True)

        # Look for state file in .claude-indexer directory
        state_file = (
            self.project_path / ".claude-indexer" / f"{self.collection_name}.json"
        )

        if not state_file.exists():
            result.is_fresh = False
            result.suggestion = (
                f"No index found. Run: claude-indexer index -c {self.collection_name}"
            )
            return result

        try:
            with open(state_file) as f:
                state = json.load(f)
        except (OSError, json.JSONDecodeError):
            result.is_fresh = False
            result.suggestion = f"Index state corrupted. Run: claude-indexer index -c {self.collection_name}"
            return result

        # Check time freshness
        last_time = state.get("_last_indexed_time")
        if last_time:
            result.last_indexed_time = last_time
            hours_ago = (time.time() - last_time) / 3600
            result.hours_since_index = round(hours_ago, 1)

            if hours_ago > self.STALE_THRESHOLD_HOURS:
                result.is_fresh = False

        # Check commit freshness
        last_commit = state.get("_last_indexed_commit")
        if last_commit:
            result.last_indexed_commit = last_commit
            result.current_commit = self._get_current_commit()

            if result.current_commit and last_commit != result.current_commit:
                commits_behind = self._count_commits_since(last_commit)
                result.commits_behind = commits_behind
                if commits_behind > 0:
                    result.is_fresh = False

        # Generate suggestion if stale
        if not result.is_fresh and not result.suggestion:
            result.suggestion = f"Run: claude-indexer index -c {self.collection_name}"

        return result

    def _get_git_context(self) -> tuple[str | None, int, list[str]]:
        """Get current git context.

        Returns:
            Tuple of (branch, uncommitted_count, recent_commits)
        """
        branch: str | None = None
        uncommitted_count = 0
        recent_commits: list[str] = []

        # Get current branch
        branch_result = self._run_git_command(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"]
        )
        if branch_result:
            branch = branch_result

        # Get uncommitted changes count
        status_result = self._run_git_command(["git", "status", "--porcelain"])
        if status_result:
            uncommitted_count = len(status_result.strip().split("\n"))

        # Get recent commits
        log_result = self._run_git_command(
            ["git", "log", "--oneline", "-3", "--format=%s"]
        )
        if log_result:
            recent_commits = log_result.strip().split("\n")[:3]

        return branch, uncommitted_count, recent_commits

    def _get_current_commit(self) -> str | None:
        """Get current HEAD commit SHA."""
        return self._run_git_command(["git", "rev-parse", "HEAD"])

    def _count_commits_since(self, since_commit: str) -> int:
        """Count commits since the given SHA.

        Args:
            since_commit: SHA to count from

        Returns:
            Number of commits between since_commit and HEAD
        """
        result = self._run_git_command(
            ["git", "rev-list", "--count", f"{since_commit}..HEAD"]
        )
        if result:
            try:
                return int(result.strip())
            except ValueError:
                pass
        return 0

    def _run_git_command(self, cmd: list[str]) -> str | None:
        """Run a git command and return output.

        Args:
            cmd: Command as list of strings

        Returns:
            Command output or None on error
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None


def run_session_start(
    project_path: Path,
    collection_name: str,
    timeout_ms: int = 2000,
    json_output: bool = False,
) -> tuple[SessionStartResult, int]:
    """Run session start check and return result with exit code.

    This is the main entry point for the CLI command.

    Args:
        project_path: Path to project directory
        collection_name: Name of Qdrant collection
        timeout_ms: Timeout in milliseconds
        json_output: Whether to format as JSON

    Returns:
        Tuple of (SessionStartResult, exit_code)

    Exit codes:
        0 = All healthy
        1 = Warnings present (index stale, etc.)

    Never returns exit code 2 (never blocks).
    """
    executor = SessionStartExecutor(
        project_path=project_path,
        collection_name=collection_name,
    )

    result = executor.execute(timeout_ms=timeout_ms)

    # Determine exit code (never 2 - session start never blocks)
    exit_code = 1 if result.has_warnings() else 0

    return result, exit_code
