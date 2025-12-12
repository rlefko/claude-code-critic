"""Tests for CLI error handling module."""

from __future__ import annotations

import pytest

from claude_indexer.cli.errors import (
    CLIError,
    CollectionNotFoundError,
    ConfigurationError,
    ErrorCategory,
    IndexingError,
    MissingAPIKeyError,
    ProjectNotFoundError,
    QdrantConnectionError,
    ServiceError,
    ValidationError,
    handle_exception,
)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""

    def test_categories_exist(self):
        """Test that all expected categories exist."""
        assert ErrorCategory.CONNECTION.value == "connection"
        assert ErrorCategory.CONFIGURATION.value == "configuration"
        assert ErrorCategory.FILE_SYSTEM.value == "file_system"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.INDEXING.value == "indexing"
        assert ErrorCategory.RUNTIME.value == "runtime"


class TestCLIError:
    """Tests for base CLIError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
        )
        assert error.category == ErrorCategory.RUNTIME
        assert error.message == "Something went wrong"
        assert error.exit_code == 1
        assert error.suggestion is None

    def test_error_with_suggestion(self):
        """Test error with suggestion."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            suggestion="Try again",
        )
        assert error.suggestion == "Try again"

    def test_error_with_details(self):
        """Test error with details."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            details={"key": "value"},
        )
        assert error.details["key"] == "value"

    def test_custom_exit_code(self):
        """Test custom exit code."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            exit_code=42,
        )
        assert error.exit_code == 42

    def test_format_with_color(self):
        """Test formatted output with colors."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            suggestion="Try again",
        )
        formatted = error.format(use_color=True)
        assert "Something went wrong" in formatted
        assert "Try again" in formatted
        assert "\033[91m" in formatted  # Red color code

    def test_format_without_color(self):
        """Test formatted output without colors."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            suggestion="Try again",
        )
        formatted = error.format(use_color=False)
        assert "Something went wrong" in formatted
        assert "Try again" in formatted
        assert "\033[" not in formatted  # No ANSI codes

    def test_format_with_details(self):
        """Test formatted output includes details."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
            details={"file": "/path/to/file"},
        )
        formatted = error.format(use_color=False)
        assert "file: /path/to/file" in formatted

    def test_str_method(self):
        """Test __str__ returns formatted error."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Something went wrong",
        )
        assert "Something went wrong" in str(error)

    def test_exception_inheritance(self):
        """Test that CLIError is an Exception."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Test error",
        )
        assert isinstance(error, Exception)


class TestQdrantConnectionError:
    """Tests for QdrantConnectionError."""

    def test_default_url(self):
        """Test error with default URL."""
        error = QdrantConnectionError()
        assert "localhost:6333" in error.message
        assert "docker run" in error.suggestion

    def test_custom_url(self):
        """Test error with custom URL."""
        error = QdrantConnectionError(url="http://custom:6334")
        assert "custom:6334" in error.message

    def test_with_original_error(self):
        """Test error with original exception."""
        error = QdrantConnectionError(
            url="http://localhost:6333",
            original_error="Connection refused",
        )
        assert "Connection refused" in error.message

    def test_category(self):
        """Test error category."""
        error = QdrantConnectionError()
        assert error.category == ErrorCategory.CONNECTION


class TestMissingAPIKeyError:
    """Tests for MissingAPIKeyError."""

    def test_basic_error(self):
        """Test basic API key error."""
        error = MissingAPIKeyError(
            key_name="OpenAI API Key",
            env_var="OPENAI_API_KEY",
        )
        assert "OpenAI API Key" in error.message
        assert "OPENAI_API_KEY" in error.suggestion

    def test_category(self):
        """Test error category."""
        error = MissingAPIKeyError(
            key_name="Test",
            env_var="TEST_KEY",
        )
        assert error.category == ErrorCategory.CONFIGURATION

    def test_details(self):
        """Test error details."""
        error = MissingAPIKeyError(
            key_name="OpenAI",
            env_var="OPENAI_API_KEY",
        )
        assert error.details["key_name"] == "OpenAI"
        assert error.details["env_var"] == "OPENAI_API_KEY"


class TestProjectNotFoundError:
    """Tests for ProjectNotFoundError."""

    def test_basic_error(self):
        """Test basic project not found error."""
        error = ProjectNotFoundError(path="/path/to/project")
        assert "/path/to/project" in error.message
        assert "verify" in error.suggestion.lower()

    def test_category(self):
        """Test error category."""
        error = ProjectNotFoundError(path="/test")
        assert error.category == ErrorCategory.FILE_SYSTEM


class TestConfigurationError:
    """Tests for ConfigurationError."""

    def test_basic_error(self):
        """Test basic configuration error."""
        error = ConfigurationError(message="Invalid config format")
        assert "Invalid config format" in error.message

    def test_with_config_file(self):
        """Test error with config file."""
        error = ConfigurationError(
            message="Invalid JSON",
            config_file="/path/to/config.json",
        )
        assert error.details["config_file"] == "/path/to/config.json"

    def test_custom_suggestion(self):
        """Test error with custom suggestion."""
        error = ConfigurationError(
            message="Invalid format",
            suggestion="Use YAML instead",
        )
        assert error.suggestion == "Use YAML instead"


class TestIndexingError:
    """Tests for IndexingError."""

    def test_basic_error(self):
        """Test basic indexing error."""
        error = IndexingError(message="Failed to parse file")
        assert "Failed to parse file" in error.message

    def test_with_file_path(self):
        """Test error with file path."""
        error = IndexingError(
            message="Parse error",
            file_path="/path/to/file.py",
        )
        assert error.details["file"] == "/path/to/file.py"


class TestCollectionNotFoundError:
    """Tests for CollectionNotFoundError."""

    def test_basic_error(self):
        """Test basic collection not found error."""
        error = CollectionNotFoundError(collection_name="my-collection")
        assert "my-collection" in error.message
        assert "collections list" in error.suggestion

    def test_category(self):
        """Test error category."""
        error = CollectionNotFoundError(collection_name="test")
        assert error.category == ErrorCategory.VALIDATION


class TestValidationError:
    """Tests for ValidationError."""

    def test_basic_error(self):
        """Test basic validation error."""
        error = ValidationError(message="Invalid argument")
        assert "Invalid argument" in error.message
        assert "--help" in error.suggestion

    def test_exit_code(self):
        """Test validation error exit code."""
        error = ValidationError(message="Test")
        assert error.exit_code == 2


class TestServiceError:
    """Tests for ServiceError."""

    def test_basic_error(self):
        """Test basic service error."""
        error = ServiceError(message="Service not running")
        assert "Service not running" in error.message
        assert "service status" in error.suggestion

    def test_category(self):
        """Test error category."""
        error = ServiceError(message="Test")
        assert error.category == ErrorCategory.RUNTIME


class TestHandleException:
    """Tests for handle_exception function."""

    def test_cli_error(self):
        """Test handling CLIError."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Test error",
            exit_code=5,
        )
        message, exit_code = handle_exception(error, use_color=False)
        assert "Test error" in message
        assert exit_code == 5

    def test_generic_exception(self):
        """Test handling generic exception."""
        error = ValueError("Invalid value")
        message, exit_code = handle_exception(error, use_color=False)
        assert "Invalid value" in message
        assert exit_code == 1

    def test_verbose_traceback(self):
        """Test verbose mode includes traceback."""
        error = ValueError("Test")
        message, _ = handle_exception(error, verbose=True)
        assert "Traceback" in message

    def test_color_in_output(self):
        """Test color codes in output."""
        error = CLIError(
            category=ErrorCategory.RUNTIME,
            message="Test",
        )
        message, _ = handle_exception(error, use_color=True)
        assert "\033[91m" in message  # Red color
