"""CLI utilities package for Claude Code Memory Indexer.

This package provides centralized output management, error handling,
and status reporting for the CLI interface.

Modules:
    output: OutputManager for consistent CLI output with color/quiet support
    errors: Structured error types with recovery suggestions
    status: Unified status command aggregating all subsystem statuses
"""

from .errors import (
    CLIError,
    ConfigurationError,
    ErrorCategory,
    IndexingError,
    MissingAPIKeyError,
    ProjectNotFoundError,
    QdrantConnectionError,
)
from .output import OutputConfig, OutputManager, should_use_color
from .status import StatusCollector, SubsystemStatus, SystemStatus

__all__ = [
    # Output
    "OutputConfig",
    "OutputManager",
    "should_use_color",
    # Errors
    "CLIError",
    "ErrorCategory",
    "QdrantConnectionError",
    "MissingAPIKeyError",
    "ProjectNotFoundError",
    "ConfigurationError",
    "IndexingError",
    # Status
    "StatusCollector",
    "SystemStatus",
    "SubsystemStatus",
]
