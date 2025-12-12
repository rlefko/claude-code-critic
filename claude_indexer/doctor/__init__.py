"""Doctor module for system health checks.

Provides the `claude-indexer doctor` command functionality for checking
system dependencies and configuration.
"""

from .checkers import (
    check_claude_cli,
    check_collection_exists,
    check_openai_key,
    check_package_installed,
    check_project_initialized,
    check_python_version,
    check_qdrant_connection,
    check_voyage_key,
)
from .manager import DoctorManager
from .types import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorOptions,
    DoctorResult,
)

__all__ = [
    # Types
    "CheckStatus",
    "CheckCategory",
    "CheckResult",
    "DoctorOptions",
    "DoctorResult",
    # Manager
    "DoctorManager",
    # Checkers
    "check_python_version",
    "check_package_installed",
    "check_qdrant_connection",
    "check_claude_cli",
    "check_openai_key",
    "check_voyage_key",
    "check_project_initialized",
    "check_collection_exists",
]
