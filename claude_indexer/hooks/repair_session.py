"""
Repair session management for Claude self-repair loop.

This module tracks repair attempts across stop-check invocations to prevent
infinite loops. After 3 failed attempts with the same findings, the system
escalates to the user instead of continuing the repair loop.

Session identification uses a hash of (project_path, findings) to detect
when Claude is trying to fix the same issues repeatedly.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from ..rules.base import Finding


@dataclass
class RepairSession:
    """Tracks repair attempts for a set of findings.

    A repair session is identified by a hash of the project path and findings.
    This allows detection of repeated attempts to fix the same issues.

    Attributes:
        session_id: Unique ID derived from project + findings hash
        project_path: Absolute path to the project being checked
        findings_hash: Hash of (rule_id, file_path, line_number) tuples
        attempt_count: Number of repair attempts so far
        max_attempts: Maximum attempts before escalation (default: 3)
        created_at: Unix timestamp when session was created
        last_check_at: Unix timestamp of last stop-check invocation
    """

    session_id: str
    project_path: str
    findings_hash: str
    attempt_count: int = 0
    max_attempts: int = 3
    created_at: float = field(default_factory=time.time)
    last_check_at: float = field(default_factory=time.time)

    TTL_SECONDS: ClassVar[float] = 1800.0  # 30 minutes

    @property
    def is_expired(self) -> bool:
        """Check if session has expired due to inactivity."""
        return time.time() - self.last_check_at > self.TTL_SECONDS

    @property
    def can_retry(self) -> bool:
        """Check if more retry attempts are allowed."""
        return self.attempt_count < self.max_attempts

    @property
    def should_escalate(self) -> bool:
        """Check if session should escalate to user."""
        return self.attempt_count >= self.max_attempts

    @property
    def remaining_attempts(self) -> int:
        """Get number of remaining retry attempts."""
        return max(0, self.max_attempts - self.attempt_count)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "project_path": self.project_path,
            "findings_hash": self.findings_hash,
            "attempt_count": self.attempt_count,
            "max_attempts": self.max_attempts,
            "created_at": self.created_at,
            "last_check_at": self.last_check_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepairSession":
        """Create RepairSession from dictionary."""
        return cls(
            session_id=data["session_id"],
            project_path=data["project_path"],
            findings_hash=data["findings_hash"],
            attempt_count=data.get("attempt_count", 0),
            max_attempts=data.get("max_attempts", 3),
            created_at=data.get("created_at", time.time()),
            last_check_at=data.get("last_check_at", time.time()),
        )


class RepairSessionManager:
    """Manages repair session persistence and lifecycle.

    Sessions are stored in a JSON file within the project's .claude-code-memory
    directory. The manager handles:
    - Creating new sessions for new findings
    - Loading existing sessions for repeated findings
    - Incrementing attempt counters
    - Cleaning up expired sessions

    Attributes:
        project_path: Path to the project being managed
        state_file: Path to the repair state JSON file
    """

    STATE_DIR = ".claude-code-memory"
    STATE_FILE = "repair_state.json"
    SCHEMA_VERSION = 1

    def __init__(self, project_path: Path):
        """Initialize manager for a project.

        Args:
            project_path: Path to the project root
        """
        self.project_path = Path(project_path).resolve()
        self.state_dir = self.project_path / self.STATE_DIR
        self.state_file = self.state_dir / self.STATE_FILE

    def _ensure_state_dir(self) -> None:
        """Ensure the state directory exists."""
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict[str, Any]:
        """Load state from file, returning empty state if not found."""
        if not self.state_file.exists():
            return {
                "sessions": {},
                "schema_version": self.SCHEMA_VERSION,
                "last_cleanup": time.time(),
            }

        try:
            with open(self.state_file) as f:
                data = json.load(f)
                # Ensure required fields
                if "sessions" not in data:
                    data["sessions"] = {}
                if "schema_version" not in data:
                    data["schema_version"] = self.SCHEMA_VERSION
                return data
        except (json.JSONDecodeError, OSError):
            # Corrupted or unreadable, start fresh
            return {
                "sessions": {},
                "schema_version": self.SCHEMA_VERSION,
                "last_cleanup": time.time(),
            }

    def _save_state(self, state: dict[str, Any]) -> None:
        """Save state to file atomically using temp file + rename."""
        self._ensure_state_dir()

        # Write to temp file first
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                json.dump(state, f, indent=2)
            # Atomic rename
            temp_file.replace(self.state_file)
        except OSError:
            # Clean up temp file on failure
            if temp_file.exists():
                temp_file.unlink()
            raise

    @staticmethod
    def compute_findings_hash(findings: list[Finding]) -> str:
        """Compute stable hash of findings for session identification.

        The hash is based on (rule_id, file_path, line_number) tuples,
        sorted to ensure stability regardless of finding order.

        Args:
            findings: List of Finding objects to hash

        Returns:
            12-character hex hash string
        """
        if not findings:
            return "empty"

        # Create sorted list of identifying tuples
        identifiers = sorted(
            (f.rule_id, f.file_path, f.line_number or 0) for f in findings
        )

        # Hash the sorted identifiers
        hasher = hashlib.sha256()
        for rule_id, file_path, line_num in identifiers:
            hasher.update(f"{rule_id}:{file_path}:{line_num}".encode())

        return hasher.hexdigest()[:12]

    def _compute_session_id(self, findings_hash: str) -> str:
        """Compute session ID from project path and findings hash."""
        hasher = hashlib.sha256()
        hasher.update(str(self.project_path).encode())
        hasher.update(findings_hash.encode())
        return hasher.hexdigest()[:12]

    def get_or_create_session(self, findings: list[Finding]) -> RepairSession:
        """Get existing session for findings or create new one.

        If findings match an existing non-expired session, returns that session.
        Otherwise, creates a new session with attempt_count=0.

        Args:
            findings: List of findings to find/create session for

        Returns:
            RepairSession for the findings
        """
        findings_hash = self.compute_findings_hash(findings)
        session_id = self._compute_session_id(findings_hash)

        state = self._load_state()
        sessions = state.get("sessions", {})

        # Check for existing session
        if session_id in sessions:
            session = RepairSession.from_dict(sessions[session_id])
            if not session.is_expired:
                return session
            # Expired, will create new

        # Create new session
        session = RepairSession(
            session_id=session_id,
            project_path=str(self.project_path),
            findings_hash=findings_hash,
            attempt_count=0,
            created_at=time.time(),
            last_check_at=time.time(),
        )

        return session

    def record_attempt(self, session: RepairSession) -> RepairSession:
        """Increment attempt count and save session.

        Args:
            session: Session to update

        Returns:
            Updated session with incremented attempt_count
        """
        # Update session
        session.attempt_count += 1
        session.last_check_at = time.time()

        # Save to state
        state = self._load_state()
        state["sessions"][session.session_id] = session.to_dict()
        self._save_state(state)

        return session

    def clear_session(self, session_id: str) -> None:
        """Remove a session (e.g., after successful fix).

        Args:
            session_id: ID of session to remove
        """
        state = self._load_state()
        if session_id in state.get("sessions", {}):
            del state["sessions"][session_id]
            self._save_state(state)

    def cleanup_expired(self) -> int:
        """Remove expired sessions from state file.

        Returns:
            Number of sessions removed
        """
        state = self._load_state()
        sessions = state.get("sessions", {})

        # Find expired sessions
        expired_ids = []
        for session_id, session_data in sessions.items():
            session = RepairSession.from_dict(session_data)
            if session.is_expired:
                expired_ids.append(session_id)

        # Remove expired
        for session_id in expired_ids:
            del sessions[session_id]

        # Update cleanup timestamp
        state["last_cleanup"] = time.time()

        if expired_ids:
            self._save_state(state)

        return len(expired_ids)

    def get_all_sessions(self) -> list[RepairSession]:
        """Get all non-expired sessions.

        Returns:
            List of active RepairSession objects
        """
        state = self._load_state()
        sessions = []
        for session_data in state.get("sessions", {}).values():
            session = RepairSession.from_dict(session_data)
            if not session.is_expired:
                sessions.append(session)
        return sessions
