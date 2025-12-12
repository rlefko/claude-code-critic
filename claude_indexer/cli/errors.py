"""Structured error types for CLI with recovery suggestions.

This module provides a consistent error handling framework for the CLI,
with categorized error types and actionable recovery suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(Enum):
    """Categories of CLI errors for organization and handling."""

    CONNECTION = "connection"  # Qdrant, network issues
    CONFIGURATION = "configuration"  # Missing keys, invalid config
    FILE_SYSTEM = "file_system"  # Path issues, permissions
    VALIDATION = "validation"  # Invalid arguments
    INDEXING = "indexing"  # Indexing failures
    RUNTIME = "runtime"  # Unexpected errors


@dataclass
class CLIError(Exception):
    """Base class for structured CLI errors with recovery suggestions.

    Attributes:
        category: Error category for grouping.
        message: Human-readable error message.
        suggestion: Optional actionable recovery suggestion.
        details: Optional additional details dict.
        exit_code: Exit code to use when this error causes termination.
    """

    category: ErrorCategory
    message: str
    suggestion: str | None = None
    details: dict[str, Any] | None = field(default_factory=dict)
    exit_code: int = 1

    def __post_init__(self) -> None:
        """Initialize the exception with the message."""
        super().__init__(self.message)

    def format(self, use_color: bool = True) -> str:
        """Format the error for display.

        Args:
            use_color: Whether to include ANSI color codes.

        Returns:
            Formatted error string with suggestion if available.
        """
        # Color codes
        red = "\033[91m" if use_color else ""
        cyan = "\033[96m" if use_color else ""
        dim = "\033[2m" if use_color else ""
        reset = "\033[0m" if use_color else ""

        lines = [f"{red}Error:{reset} {self.message}"]

        if self.suggestion:
            lines.append(f"{cyan}Suggestion:{reset} {self.suggestion}")

        if self.details:
            for key, value in self.details.items():
                lines.append(f"{dim}  {key}: {value}{reset}")

        return "\n".join(lines)

    def __str__(self) -> str:
        """Return the formatted error message."""
        return self.format(use_color=False)


# Pre-defined error types for common scenarios


class QdrantConnectionError(CLIError):
    """Error connecting to Qdrant vector database."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        original_error: str | None = None,
    ):
        message = f"Cannot connect to Qdrant at {url}"
        if original_error:
            message = f"{message}: {original_error}"

        super().__init__(
            category=ErrorCategory.CONNECTION,
            message=message,
            suggestion=(
                "Ensure Qdrant is running. Start with: "
                "docker run -p 6333:6333 qdrant/qdrant"
            ),
            details={"url": url} if original_error else None,
            exit_code=1,
        )


class MissingAPIKeyError(CLIError):
    """Error when a required API key is missing."""

    def __init__(self, key_name: str, env_var: str):
        super().__init__(
            category=ErrorCategory.CONFIGURATION,
            message=f"Missing required API key: {key_name}",
            suggestion=f"Set the {env_var} environment variable or add to settings.txt",
            details={"key_name": key_name, "env_var": env_var},
            exit_code=1,
        )


class ProjectNotFoundError(CLIError):
    """Error when the specified project directory doesn't exist."""

    def __init__(self, path: str):
        super().__init__(
            category=ErrorCategory.FILE_SYSTEM,
            message=f"Project directory not found: {path}",
            suggestion="Verify the path exists and you have read permissions",
            details={"path": path},
            exit_code=1,
        )


class ConfigurationError(CLIError):
    """Error in configuration file or settings."""

    def __init__(
        self,
        message: str,
        config_file: str | None = None,
        suggestion: str | None = None,
    ):
        default_suggestion = (
            "Check your configuration file syntax and required fields"
        )
        super().__init__(
            category=ErrorCategory.CONFIGURATION,
            message=message,
            suggestion=suggestion or default_suggestion,
            details={"config_file": config_file} if config_file else None,
            exit_code=1,
        )


class IndexingError(CLIError):
    """Error during indexing operation."""

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        suggestion: str | None = None,
    ):
        default_suggestion = "Check the file exists and is a supported file type"
        super().__init__(
            category=ErrorCategory.INDEXING,
            message=message,
            suggestion=suggestion or default_suggestion,
            details={"file": file_path} if file_path else None,
            exit_code=1,
        )


class CollectionNotFoundError(CLIError):
    """Error when the specified collection doesn't exist."""

    def __init__(self, collection_name: str):
        super().__init__(
            category=ErrorCategory.VALIDATION,
            message=f"Collection not found: {collection_name}",
            suggestion=(
                "Run 'claude-indexer collections list' to see available collections, "
                "or 'claude-indexer init' to create one"
            ),
            details={"collection": collection_name},
            exit_code=1,
        )


class ValidationError(CLIError):
    """Error for invalid CLI arguments or input."""

    def __init__(self, message: str, suggestion: str | None = None):
        super().__init__(
            category=ErrorCategory.VALIDATION,
            message=message,
            suggestion=suggestion or "Check the command syntax with --help",
            exit_code=2,
        )


class ServiceError(CLIError):
    """Error with the background indexing service."""

    def __init__(self, message: str, suggestion: str | None = None):
        default_suggestion = (
            "Try 'claude-indexer service status' to check service health"
        )
        super().__init__(
            category=ErrorCategory.RUNTIME,
            message=message,
            suggestion=suggestion or default_suggestion,
            exit_code=1,
        )


def handle_exception(
    error: Exception,
    use_color: bool = True,
    verbose: bool = False,
) -> tuple[str, int]:
    """Convert any exception to formatted output and exit code.

    Args:
        error: The exception to handle.
        use_color: Whether to use color in output.
        verbose: Whether to include full traceback.

    Returns:
        Tuple of (formatted_message, exit_code).
    """
    import traceback

    if isinstance(error, CLIError):
        message = error.format(use_color=use_color)
        exit_code = error.exit_code
    else:
        # Generic exception handling
        red = "\033[91m" if use_color else ""
        reset = "\033[0m" if use_color else ""
        message = f"{red}Error:{reset} {str(error)}"
        exit_code = 1

    if verbose:
        message += "\n\nTraceback:\n" + traceback.format_exc()

    return message, exit_code
