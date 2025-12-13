"""Centralized logging configuration for the indexer.

Enhanced for Milestone 0.3 with:
- Structured JSON logging support
- Configurable 3-file rotation (default)
- Performance timing integration
- Multi-component category loggers
- Debug context manager
"""

import json
import logging
import logging.handlers
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path


class LogCategory(Enum):
    """Log categories for multi-component debugging."""

    INDEXER = "indexer"
    GUARD = "guard"
    MCP = "mcp"
    PERFORMANCE = "performance"
    WATCHER = "watcher"
    STORAGE = "storage"


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    Produces structured JSON log entries with consistent fields
    and support for extra context like performance timing.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            JSON string representation of the log entry.
        """
        log_entry: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        extra_fields = ["duration_ms", "operation", "file_path", "entity_count"]
        for field in extra_fields:
            if hasattr(record, field):
                log_entry[field] = getattr(record, field)

        # Include exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def get_global_log_dir() -> Path:
    """Get the global log directory.

    Returns:
        Path to the global log directory (~/.claude-indexer/logs/).
    """
    log_dir = Path.home() / ".claude-indexer" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_default_log_file(
    collection_name: str | None = None, project_path: Path | None = None
) -> Path:
    """Get the default log file path, optionally per collection and project."""
    if project_path:
        # Use project directory for logs
        log_dir = project_path / "logs"
    else:
        # Fallback to home directory
        log_dir = Path.home() / ".claude-indexer" / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)

    if collection_name:
        return log_dir / f"{collection_name}.log"
    else:
        return log_dir / "claude-indexer.log"


def clear_log_file(
    collection_name: str | None = None, project_path: Path | None = None
) -> bool:
    """Clear the log file for a collection."""
    try:
        log_file = get_default_log_file(collection_name, project_path)
        if log_file.exists():
            log_file.unlink()
            return True
        return True  # File doesn't exist, consider it cleared
    except Exception:
        return False


def setup_logging(
    level: str = "INFO",
    quiet: bool = False,
    verbose: bool = False,
    log_file: Path | None = None,
    enable_file_logging: bool = True,
    collection_name: str | None = None,
    project_path: Path | None = None,
    # New parameters for Milestone 0.3
    log_format: str = "text",
    rotation_count: int = 3,
    max_bytes: int = 10485760,
    **kwargs,
) -> "logging.Logger":
    """Setup global logging configuration.

    Args:
        level: Base log level (DEBUG, INFO, WARNING, ERROR).
        quiet: Suppress console output (only ERROR level).
        verbose: Enable debug-level output.
        log_file: Explicit log file path.
        enable_file_logging: Enable file-based logging.
        collection_name: Collection-specific log file naming.
        project_path: Project root for log file location.
        log_format: Output format ("text" or "json").
        rotation_count: Number of backup files (default 3).
        max_bytes: Max file size before rotation (default 10MB).
        **kwargs: Additional parameters for forward compatibility.

    Returns:
        Configured logger instance.
    """
    import logging.config

    # Use collection-specific log file if none specified and file logging is enabled
    if log_file is None and enable_file_logging:
        log_file = get_default_log_file(collection_name, project_path)

    # Determine effective level
    if quiet:
        effective_level = "ERROR"
    elif verbose:
        effective_level = "DEBUG"
    else:
        effective_level = level

    # Build dictConfig
    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "simple": {"format": "%(levelname)s | %(message)s"},
            "json": {
                "()": JSONFormatter,
            },
        },
        "handlers": {},
        "loggers": {
            "claude_indexer": {"handlers": [], "level": "DEBUG", "propagate": False}
        },
    }

    # Select formatter based on format option
    file_formatter = "json" if log_format == "json" else "detailed"

    # Console handler
    if not quiet:
        config["handlers"]["console"] = {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "level": effective_level,
            "stream": "ext://sys.stderr",
        }
        config["loggers"]["claude_indexer"]["handlers"].append("console")

    # File handler with rotation (changed from 7 to 3 backups by default)
    if log_file:
        config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": file_formatter,
            "level": "DEBUG",
            "filename": str(log_file),
            "maxBytes": max_bytes,
            "backupCount": rotation_count,
        }
        config["loggers"]["claude_indexer"]["handlers"].append("file")

    logging.config.dictConfig(config)
    return logging.getLogger("claude_indexer")


def get_logger() -> "logging.Logger":
    """Get the global logger instance."""
    return logging.getLogger("claude_indexer")


def get_category_logger(category: LogCategory) -> "logging.Logger":
    """Get a logger for a specific category.

    Args:
        category: The log category (INDEXER, GUARD, MCP, etc.).

    Returns:
        Logger instance for the category.

    Example:
        >>> from claude_indexer.indexer_logging import get_category_logger, LogCategory
        >>> logger = get_category_logger(LogCategory.GUARD)
        >>> logger.info("Guard check completed")
    """
    return logging.getLogger(f"claude_indexer.{category.value}")


@contextmanager
def debug_context(
    logger: "logging.Logger | None" = None,
) -> Generator["logging.Logger", None, None]:
    """Temporarily enable debug-level logging.

    Context manager that sets the logger to DEBUG level for the duration
    of the context, then restores the original level.

    Args:
        logger: Optional logger to modify. Defaults to the global logger.

    Yields:
        The logger instance with DEBUG level enabled.

    Example:
        >>> with debug_context():
        ...     # Debug logs will appear
        ...     process_complex_operation()
    """
    target_logger = logger or get_logger()
    original_level = target_logger.level
    try:
        target_logger.setLevel(logging.DEBUG)
        # Also set handlers to DEBUG temporarily
        original_handler_levels = []
        for handler in target_logger.handlers:
            original_handler_levels.append(handler.level)
            handler.setLevel(logging.DEBUG)
        yield target_logger
    finally:
        target_logger.setLevel(original_level)
        # Restore handler levels
        for handler, level in zip(
            target_logger.handlers, original_handler_levels, strict=False
        ):
            handler.setLevel(level)


def setup_multi_component_logging(
    project_path: Path | None = None,
    collection_name: str | None = None,
    log_format: str = "text",
    enable_performance: bool = False,
    rotation_count: int = 3,
    max_bytes: int = 10485760,
) -> None:
    """Setup logging for all components with category-specific files.

    Creates separate log files for each component category in the global
    log directory (~/.claude-indexer/logs/).

    Args:
        project_path: Project root for project-specific logs.
        collection_name: Collection name for log file naming.
        log_format: "text" or "json".
        enable_performance: Enable separate performance log.
        rotation_count: Number of backup files (default 3).
        max_bytes: Max file size before rotation (default 10MB).
    """
    global_log_dir = get_global_log_dir()

    # Setup category-specific handlers
    categories: list[tuple[LogCategory, Path]] = [
        (LogCategory.INDEXER, global_log_dir / "indexer.log"),
        (LogCategory.GUARD, global_log_dir / "guard.log"),
        (LogCategory.MCP, global_log_dir / "mcp.log"),
        (LogCategory.WATCHER, global_log_dir / "watcher.log"),
        (LogCategory.STORAGE, global_log_dir / "storage.log"),
    ]

    if enable_performance:
        categories.append((LogCategory.PERFORMANCE, global_log_dir / "performance.log"))

    # Select formatter
    if log_format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    for category, log_file in categories:
        logger = logging.getLogger(f"claude_indexer.{category.value}")

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # File handler with rotation
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=rotation_count,
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
