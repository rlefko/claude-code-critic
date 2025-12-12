"""Unified status command for aggregating all subsystem statuses.

This module provides a single command to view the health and status
of all Claude Indexer components: Qdrant, Service, Hooks, Index, and Health.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ..indexer_logging import get_logger

logger = get_logger()


class StatusLevel(Enum):
    """Status level for subsystem health."""

    OK = "ok"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class SubsystemStatus:
    """Status of a single subsystem.

    Attributes:
        name: Subsystem name (e.g., "Qdrant", "Service").
        level: Status level (OK, WARN, FAIL, UNKNOWN).
        message: Human-readable status message.
        details: Additional details dict.
    """

    name: str
    level: StatusLevel
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "level": self.level.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class SystemStatus:
    """Aggregated status of all subsystems.

    Attributes:
        qdrant: Qdrant vector database status.
        service: Background service status.
        hooks: Git/Claude hooks status.
        index: Index freshness status.
        health: Overall health check summary.
        timestamp: When status was collected.
    """

    qdrant: SubsystemStatus | None = None
    service: SubsystemStatus | None = None
    hooks: SubsystemStatus | None = None
    index: SubsystemStatus | None = None
    health: SubsystemStatus | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def overall_level(self) -> StatusLevel:
        """Calculate overall status level."""
        subsystems = [self.qdrant, self.service, self.hooks, self.index, self.health]
        active = [s for s in subsystems if s is not None]

        if not active:
            return StatusLevel.UNKNOWN

        if any(s.level == StatusLevel.FAIL for s in active):
            return StatusLevel.FAIL
        if any(s.level == StatusLevel.WARN for s in active):
            return StatusLevel.WARN
        if all(s.level == StatusLevel.OK for s in active):
            return StatusLevel.OK
        return StatusLevel.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "overall": self.overall_level.value,
            "subsystems": {},
        }

        for name in ["qdrant", "service", "hooks", "index", "health"]:
            subsystem = getattr(self, name)
            if subsystem is not None:
                result["subsystems"][name] = subsystem.to_dict()

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class StatusCollector:
    """Collects status from all subsystems.

    Example:
        >>> collector = StatusCollector(project_path="/path/to/project")
        >>> status = collector.collect_all()
        >>> print(status.to_text())
    """

    def __init__(
        self,
        project_path: Path | str | None = None,
        collection_name: str | None = None,
    ):
        """Initialize the status collector.

        Args:
            project_path: Optional project directory path.
            collection_name: Optional collection name.
        """
        self.project_path = Path(project_path) if project_path else None
        self.collection_name = collection_name
        self._config: Any = None

    def _load_config(self) -> Any:
        """Load configuration, caching the result."""
        if self._config is not None:
            return self._config

        try:
            from ..config.config_loader import ConfigLoader

            loader = ConfigLoader()
            self._config = loader.load(project_path=self.project_path)
            return self._config
        except Exception as e:
            logger.debug(f"Config loading failed: {e}")
            return None

    def collect_qdrant(self) -> SubsystemStatus:
        """Collect Qdrant vector database status.

        Returns:
            SubsystemStatus for Qdrant connection and collections.
        """
        try:
            config = self._load_config()
            qdrant_url = "http://localhost:6333"

            if config and hasattr(config, "qdrant_url"):
                qdrant_url = config.qdrant_url

            from qdrant_client import QdrantClient

            client = QdrantClient(
                url=qdrant_url,
                api_key=getattr(config, "qdrant_api_key", None) if config else None,
                timeout=5,
            )

            collections = client.get_collections().collections
            collection_count = len(collections)

            return SubsystemStatus(
                name="Qdrant",
                level=StatusLevel.OK,
                message=f"Connected ({qdrant_url})",
                details={"url": qdrant_url, "collections": collection_count},
            )

        except Exception as e:
            return SubsystemStatus(
                name="Qdrant",
                level=StatusLevel.FAIL,
                message=f"Connection failed: {e}",
                details={"error": str(e)},
            )

    def collect_service(self) -> SubsystemStatus:
        """Collect background service status.

        Returns:
            SubsystemStatus for the indexing service.
        """
        try:
            from ..service import IndexingService

            service = IndexingService()
            config = service.load_config()
            projects = config.get("projects", [])

            # Check if service is running (would need PID file or similar)
            # For now, just report configuration
            return SubsystemStatus(
                name="Service",
                level=StatusLevel.UNKNOWN,
                message=f"Configured ({len(projects)} projects)",
                details={"projects": len(projects)},
            )

        except ImportError:
            return SubsystemStatus(
                name="Service",
                level=StatusLevel.WARN,
                message="Not available (watchdog not installed)",
                details={},
            )
        except Exception as e:
            return SubsystemStatus(
                name="Service",
                level=StatusLevel.FAIL,
                message=f"Error: {e}",
                details={"error": str(e)},
            )

    def collect_hooks(self) -> SubsystemStatus:
        """Collect Git/Claude hooks status.

        Returns:
            SubsystemStatus for installed hooks.
        """
        if not self.project_path:
            return SubsystemStatus(
                name="Hooks",
                level=StatusLevel.UNKNOWN,
                message="No project specified",
                details={},
            )

        try:
            installed_hooks = []

            # Check for Claude hooks
            claude_hooks_dir = self.project_path / ".claude" / "hooks"
            if claude_hooks_dir.exists():
                for hook_file in claude_hooks_dir.glob("*.sh"):
                    installed_hooks.append(f"claude:{hook_file.stem}")

            # Check for git hooks
            git_hooks_dir = self.project_path / ".git" / "hooks"
            if git_hooks_dir.exists():
                for hook_name in ["pre-commit", "post-commit", "pre-push"]:
                    hook_path = git_hooks_dir / hook_name
                    if hook_path.exists() and not hook_path.name.endswith(".sample"):
                        installed_hooks.append(f"git:{hook_name}")

            if installed_hooks:
                return SubsystemStatus(
                    name="Hooks",
                    level=StatusLevel.OK,
                    message=f"Installed ({len(installed_hooks)} hooks)",
                    details={"hooks": installed_hooks},
                )
            else:
                return SubsystemStatus(
                    name="Hooks",
                    level=StatusLevel.WARN,
                    message="No hooks installed",
                    details={},
                )

        except Exception as e:
            return SubsystemStatus(
                name="Hooks",
                level=StatusLevel.FAIL,
                message=f"Error: {e}",
                details={"error": str(e)},
            )

    def collect_index(self) -> SubsystemStatus:
        """Collect index freshness status.

        Returns:
            SubsystemStatus for index state.
        """
        if not self.project_path or not self.collection_name:
            return SubsystemStatus(
                name="Index",
                level=StatusLevel.UNKNOWN,
                message="No project/collection specified",
                details={},
            )

        try:
            # Check for state file
            state_file = self.project_path / ".index_cache" / "state.json"
            if not state_file.exists():
                return SubsystemStatus(
                    name="Index",
                    level=StatusLevel.WARN,
                    message="Not indexed yet",
                    details={"suggestion": "Run 'claude-indexer index' to index"},
                )

            with open(state_file) as f:
                state = json.load(f)

            file_count = state.get("_file_count", len(state) - 2)  # Exclude meta keys
            last_indexed = state.get("_last_indexed_time")

            # Calculate staleness
            if last_indexed:
                last_dt = datetime.fromisoformat(last_indexed)
                age = datetime.now() - last_dt
                age_hours = age.total_seconds() / 3600

                if age_hours > 24:
                    level = StatusLevel.WARN
                    age_str = f"{int(age_hours)}h ago (stale)"
                elif age_hours > 1:
                    level = StatusLevel.OK
                    age_str = f"{int(age_hours)}h ago"
                else:
                    level = StatusLevel.OK
                    age_str = f"{int(age.total_seconds() / 60)}m ago"
            else:
                level = StatusLevel.OK
                age_str = "Unknown"

            return SubsystemStatus(
                name="Index",
                level=level,
                message=f"{file_count} files, {age_str}",
                details={
                    "file_count": file_count,
                    "last_indexed": last_indexed,
                    "collection": self.collection_name,
                },
            )

        except Exception as e:
            return SubsystemStatus(
                name="Index",
                level=StatusLevel.FAIL,
                message=f"Error reading state: {e}",
                details={"error": str(e)},
            )

    def collect_health(self) -> SubsystemStatus:
        """Collect overall health status using doctor checks.

        Returns:
            SubsystemStatus summarizing doctor check results.
        """
        try:
            from ..doctor.manager import DoctorManager
            from ..doctor.types import DoctorOptions

            options = DoctorOptions(
                project_path=self.project_path,
                collection_name=self.collection_name,
            )
            doctor = DoctorManager(options)
            result = doctor.run_quick()

            if result.failures > 0:
                level = StatusLevel.FAIL
            elif result.warnings > 0:
                level = StatusLevel.WARN
            else:
                level = StatusLevel.OK

            total = result.passed + result.warnings + result.failures + result.skipped
            return SubsystemStatus(
                name="Health",
                level=level,
                message=f"{result.passed}/{total} checks passed",
                details={
                    "passed": result.passed,
                    "warnings": result.warnings,
                    "failures": result.failures,
                    "skipped": result.skipped,
                },
            )

        except Exception as e:
            return SubsystemStatus(
                name="Health",
                level=StatusLevel.UNKNOWN,
                message=f"Check failed: {e}",
                details={"error": str(e)},
            )

    def collect_all(self) -> SystemStatus:
        """Collect status from all subsystems.

        Returns:
            SystemStatus with all subsystem statuses.
        """
        return SystemStatus(
            qdrant=self.collect_qdrant(),
            service=self.collect_service(),
            hooks=self.collect_hooks(),
            index=self.collect_index(),
            health=self.collect_health(),
        )


def format_status_text(
    status: SystemStatus,
    use_color: bool = True,
    verbose: bool = False,
) -> str:
    """Format SystemStatus as human-readable text.

    Args:
        status: SystemStatus to format.
        use_color: Whether to use ANSI colors.
        verbose: Whether to include details.

    Returns:
        Formatted status string.
    """
    # Color codes
    green = "\033[92m" if use_color else ""
    yellow = "\033[93m" if use_color else ""
    red = "\033[91m" if use_color else ""
    dim = "\033[2m" if use_color else ""
    bold = "\033[1m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    # Symbols
    symbols = {
        StatusLevel.OK: f"{green}[OK]{reset}" if use_color else "[OK]",
        StatusLevel.WARN: f"{yellow}[WARN]{reset}" if use_color else "[WARN]",
        StatusLevel.FAIL: f"{red}[FAIL]{reset}" if use_color else "[FAIL]",
        StatusLevel.UNKNOWN: f"{dim}[--]{reset}" if use_color else "[--]",
    }

    lines = [f"{bold}Claude Indexer Status{reset}", "=" * 21, ""]

    # Format each subsystem
    for name in ["qdrant", "service", "hooks", "index", "health"]:
        subsystem = getattr(status, name)
        if subsystem is None:
            continue

        symbol = symbols.get(subsystem.level, symbols[StatusLevel.UNKNOWN])
        label = f"{subsystem.name}:".ljust(12)
        lines.append(f"{label} {symbol} {subsystem.message}")

        # Add details in verbose mode
        if verbose and subsystem.details:
            for key, value in subsystem.details.items():
                if key != "error":  # Skip error in summary
                    lines.append(f"{dim}             {key}: {value}{reset}")

    # Overall summary
    lines.append("")
    overall_symbol = symbols.get(status.overall_level, symbols[StatusLevel.UNKNOWN])
    lines.append(f"Overall:     {overall_symbol}")

    return "\n".join(lines)
