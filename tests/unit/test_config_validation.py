"""Unit tests for configuration validation."""

import json
from pathlib import Path

import pytest

from claude_indexer.config.validation import (
    ConfigError,
    ConfigValidator,
    ValidationResult,
    validate_config_dict,
    validate_config_file,
)


class TestConfigError:
    """Tests for ConfigError class."""

    def test_basic_error(self):
        """Test basic error creation."""
        error = ConfigError(
            path="api.openai.api_key",
            message="API key is required",
        )
        assert error.path == "api.openai.api_key"
        assert error.message == "API key is required"
        assert error.suggestion is None
        assert error.severity == "error"

    def test_error_with_suggestion(self):
        """Test error with suggestion."""
        error = ConfigError(
            path="embedding.provider",
            message="Invalid provider",
            suggestion="Use 'openai' or 'voyage'",
        )
        assert error.suggestion == "Use 'openai' or 'voyage'"

    def test_error_string_representation(self):
        """Test error string representation."""
        error = ConfigError(
            path="watcher.debounce_seconds",
            message="Value too small",
            suggestion="Use a value >= 0.1",
        )
        str_repr = str(error)
        assert "watcher.debounce_seconds" in str_repr
        assert "Value too small" in str_repr
        assert "Use a value >= 0.1" in str_repr

    def test_error_to_dict(self):
        """Test error to_dict method."""
        error = ConfigError(
            path="api.qdrant.url",
            message="Invalid URL",
            suggestion="Use http:// or https://",
            severity="error",
        )
        d = error.to_dict()
        assert d["path"] == "api.qdrant.url"
        assert d["message"] == "Invalid URL"
        assert d["suggestion"] == "Use http:// or https://"
        assert d["severity"] == "error"


class TestValidationResult:
    """Tests for ValidationResult class."""

    def test_valid_result(self):
        """Test valid result creation."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_invalid_result_with_errors(self):
        """Test invalid result with errors."""
        errors = [
            ConfigError(path="root", message="Error 1"),
            ConfigError(path="root", message="Error 2"),
        ]
        result = ValidationResult(valid=False, errors=errors)
        assert result.valid is False
        assert len(result.errors) == 2

    def test_valid_result_with_warnings(self):
        """Test valid result with warnings."""
        warnings = [ConfigError(path="warn", message="Warning 1", severity="warning")]
        result = ValidationResult(valid=True, warnings=warnings)
        assert result.valid is True
        assert len(result.warnings) == 1

    def test_string_representation_valid(self):
        """Test string representation of valid result."""
        result = ValidationResult(valid=True)
        assert "valid" in str(result).lower()

    def test_string_representation_with_errors(self):
        """Test string representation with errors."""
        result = ValidationResult(
            valid=False,
            errors=[ConfigError(path="test", message="Test error")],
        )
        str_repr = str(result)
        assert "Error" in str_repr
        assert "test" in str_repr

    def test_to_dict(self):
        """Test to_dict method."""
        result = ValidationResult(
            valid=False,
            errors=[ConfigError(path="e", message="error")],
            warnings=[ConfigError(path="w", message="warning")],
        )
        d = result.to_dict()
        assert d["valid"] is False
        assert len(d["errors"]) == 1
        assert len(d["warnings"]) == 1


class TestConfigValidator:
    """Tests for ConfigValidator class."""

    def test_validator_creation(self):
        """Test validator creation."""
        validator = ConfigValidator()
        assert validator is not None

    def test_validate_empty_config(self):
        """Test validation of empty config."""
        validator = ConfigValidator()
        result = validator.validate({})

        # Empty config should be valid (uses defaults)
        assert result.valid is True

    def test_validate_valid_config(self):
        """Test validation of valid config."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "project": {"name": "test", "collection": "test-collection"},
            "embedding": {"provider": "voyage"},
        }
        result = validator.validate(config)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_validate_unknown_section(self):
        """Test validation warns about unknown sections."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "unknown_section": {"foo": "bar"},
        }
        result = validator.validate(config)

        # Should warn about unknown section
        assert any("unknown_section" in w.path for w in result.warnings)

    def test_validate_missing_api_key_for_voyage(self):
        """Test validation warns about missing Voyage API key."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "embedding": {"provider": "voyage"},
            "api": {"voyage": {"api_key": ""}},
        }
        result = validator.validate(config)

        # Should warn about missing API key
        api_key_warnings = [
            w for w in result.warnings if "voyage" in w.path.lower() and "api_key" in w.path
        ]
        assert len(api_key_warnings) > 0

    def test_validate_missing_api_key_for_openai(self):
        """Test validation warns about missing OpenAI API key."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "embedding": {"provider": "openai"},
            "api": {"openai": {"api_key": ""}},
        }
        result = validator.validate(config)

        # Should warn about missing API key
        api_key_warnings = [
            w for w in result.warnings if "openai" in w.path.lower() and "api_key" in w.path
        ]
        assert len(api_key_warnings) > 0

    def test_validate_invalid_qdrant_url(self):
        """Test validation errors on invalid Qdrant URL."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "api": {"qdrant": {"url": "invalid-url-no-protocol"}},
        }
        result = validator.validate(config)

        # Should error on invalid URL
        url_errors = [e for e in result.errors if "qdrant" in e.path.lower()]
        assert len(url_errors) > 0

    def test_validate_valid_qdrant_url_http(self):
        """Test validation accepts http:// Qdrant URL."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "api": {"qdrant": {"url": "http://localhost:6333"}},
        }
        result = validator.validate(config)

        # Should not have URL errors
        url_errors = [e for e in result.errors if "qdrant" in e.path.lower()]
        assert len(url_errors) == 0

    def test_validate_valid_qdrant_url_https(self):
        """Test validation accepts https:// Qdrant URL."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "api": {"qdrant": {"url": "https://cloud.qdrant.io"}},
        }
        result = validator.validate(config)

        # Should not have URL errors
        url_errors = [e for e in result.errors if "qdrant" in e.path.lower()]
        assert len(url_errors) == 0

    def test_validate_dangerous_patterns_env(self):
        """Test validation warns about dangerous include patterns."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "indexing": {
                "filePatterns": {"include": ["*.py", ".env"]},
            },
        }
        result = validator.validate(config)

        # Should warn about .env
        env_warnings = [
            w for w in result.warnings if ".env" in w.message or "sensitive" in w.message.lower()
        ]
        assert len(env_warnings) > 0

    def test_validate_conflicting_patterns(self):
        """Test validation warns about conflicting include/exclude patterns."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "indexing": {
                "filePatterns": {
                    "include": ["*.py", "*.js"],
                    "exclude": ["*.py"],
                },
            },
        }
        result = validator.validate(config)

        # Should warn about conflicting pattern
        conflict_warnings = [
            w for w in result.warnings if "*.py" in w.message and "both" in w.message.lower()
        ]
        assert len(conflict_warnings) > 0

    def test_validate_unknown_version(self):
        """Test validation warns about unknown version."""
        validator = ConfigValidator()
        config = {"version": "99.0"}
        result = validator.validate(config)

        # Should warn about unknown version
        version_warnings = [w for w in result.warnings if "version" in w.path.lower()]
        assert len(version_warnings) > 0

    def test_validate_missing_version(self):
        """Test validation notes missing version."""
        validator = ConfigValidator()
        config = {"project": {"name": "test", "collection": "test"}}
        result = validator.validate(config)

        # Should have info about missing version
        version_info = [i for i in result.info if "version" in i.path.lower()]
        assert len(version_info) > 0

    def test_validate_missing_project(self):
        """Test validation notes missing project config."""
        validator = ConfigValidator()
        config = {"version": "3.0"}
        result = validator.validate(config)

        # Should have info about missing project
        project_info = [i for i in result.info if "project" in i.path.lower()]
        assert len(project_info) > 0

    def test_validate_missing_project_name(self):
        """Test validation warns about missing project name."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "project": {"collection": "test-collection"},
        }
        result = validator.validate(config)

        # Should warn about missing name
        name_warnings = [w for w in result.warnings if "name" in w.path.lower()]
        assert len(name_warnings) > 0

    def test_validate_missing_project_collection(self):
        """Test validation warns about missing project collection."""
        validator = ConfigValidator()
        config = {
            "version": "3.0",
            "project": {"name": "test"},
        }
        result = validator.validate(config)

        # Should warn about missing collection
        coll_warnings = [w for w in result.warnings if "collection" in w.path.lower()]
        assert len(coll_warnings) > 0


class TestValidateConfigFile:
    """Tests for validate_config_file function."""

    def test_validate_valid_file(self, tmp_path):
        """Test validation of valid config file."""
        config_file = tmp_path / "settings.json"
        config_file.write_text(json.dumps({
            "version": "3.0",
            "project": {"name": "test", "collection": "test"},
        }))

        result = validate_config_file(config_file)
        assert result.valid is True

    def test_validate_invalid_json(self, tmp_path):
        """Test validation of file with invalid JSON."""
        config_file = tmp_path / "settings.json"
        config_file.write_text("{invalid json}")

        result = validate_config_file(config_file)
        assert result.valid is False
        assert any("JSON" in e.message for e in result.errors)

    def test_validate_nonexistent_file(self, tmp_path):
        """Test validation of nonexistent file."""
        config_file = tmp_path / "nonexistent.json"

        result = validate_config_file(config_file)
        assert result.valid is False
        assert any("not found" in e.message for e in result.errors)

    def test_validate_file_with_syntax_error(self, tmp_path):
        """Test validation of file with JSON syntax error."""
        config_file = tmp_path / "settings.json"
        config_file.write_text('{"version": "3.0",}')  # Trailing comma

        result = validate_config_file(config_file)
        assert result.valid is False


class TestValidateConfigDict:
    """Tests for validate_config_dict function."""

    def test_validate_empty_dict(self):
        """Test validation of empty dictionary."""
        result = validate_config_dict({})
        assert result.valid is True

    def test_validate_valid_dict(self):
        """Test validation of valid dictionary."""
        config = {
            "version": "3.0",
            "project": {"name": "test", "collection": "test"},
            "api": {
                "qdrant": {"url": "http://localhost:6333"},
            },
        }
        result = validate_config_dict(config)
        assert result.valid is True

    def test_validate_dict_with_errors(self):
        """Test validation of dictionary with errors."""
        config = {
            "version": "3.0",
            "api": {
                "qdrant": {"url": "not-a-url"},
            },
        }
        result = validate_config_dict(config)
        assert result.valid is False


class TestValidSections:
    """Tests for valid section detection."""

    def test_valid_sections_list(self):
        """Test that all valid sections are recognized."""
        validator = ConfigValidator()
        valid_sections = validator.VALID_SECTIONS

        assert "version" in valid_sections
        assert "project" in valid_sections
        assert "api" in valid_sections
        assert "embedding" in valid_sections
        assert "indexing" in valid_sections
        assert "watcher" in valid_sections
        assert "performance" in valid_sections
        assert "hooks" in valid_sections
        assert "guard" in valid_sections
        assert "logging" in valid_sections
        assert "$schema" in valid_sections

    def test_schema_reference_is_valid(self):
        """Test that $schema is accepted as valid."""
        validator = ConfigValidator()
        config = {
            "$schema": "https://example.com/schema.json",
            "version": "3.0",
        }
        result = validator.validate(config)

        # Should not warn about $schema
        schema_warnings = [w for w in result.warnings if "$schema" in w.path]
        assert len(schema_warnings) == 0
