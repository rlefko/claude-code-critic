"""Configuration validation with clear, actionable error messages.

This module provides validation utilities for configuration files,
including JSON Schema validation and semantic validation with
user-friendly error messages and suggestions.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..indexer_logging import get_logger

logger = get_logger()

# Try to import jsonschema, but make it optional
try:
    from jsonschema import Draft7Validator, ValidationError

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    Draft7Validator = None  # type: ignore
    ValidationError = Exception  # type: ignore


@dataclass
class ConfigError:
    """A configuration validation error with helpful context."""

    path: str
    message: str
    suggestion: Optional[str] = None
    severity: str = "error"

    def __str__(self) -> str:
        result = f"  [{self.path}] {self.message}"
        if self.suggestion:
            result += f"\n    Suggestion: {self.suggestion}"
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "path": self.path,
            "message": self.message,
            "suggestion": self.suggestion,
            "severity": self.severity,
        }


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    valid: bool
    errors: list[ConfigError] = field(default_factory=list)
    warnings: list[ConfigError] = field(default_factory=list)
    info: list[ConfigError] = field(default_factory=list)

    def __str__(self) -> str:
        if self.valid and not self.warnings:
            return "Configuration is valid."

        lines = []
        if self.errors:
            lines.append(f"\nErrors ({len(self.errors)}):")
            lines.extend(str(e) for e in self.errors)
        if self.warnings:
            lines.append(f"\nWarnings ({len(self.warnings)}):")
            lines.extend(str(w) for w in self.warnings)
        if self.info:
            lines.append(f"\nInfo ({len(self.info)}):")
            lines.extend(str(i) for i in self.info)
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "valid": self.valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "info": [i.to_dict() for i in self.info],
        }


class ConfigValidator:
    """Validates configuration against JSON Schema with helpful error messages."""

    # User-friendly suggestions for common validation errors
    ERROR_SUGGESTIONS: dict[str, str] = {
        "minItems": "Add at least one item to this array",
        "maxItems": "Remove some items from this array",
        "minimum": "Use a larger value",
        "maximum": "Use a smaller value",
        "minLength": "The string is too short",
        "maxLength": "The string is too long",
        "pattern": "Check the format requirements for this field",
        "enum": "Use one of the allowed values",
        "type": "Check the expected data type",
        "required": "This field is required",
        "additionalProperties": "Remove unknown properties or check spelling",
        "format": "Check the format (e.g., URI, date)",
    }

    # Known valid config sections for semantic validation
    VALID_SECTIONS = {
        "version",
        "project",
        "api",
        "embedding",
        "indexing",
        "watcher",
        "performance",
        "hooks",
        "guard",
        "logging",
        "$schema",
    }

    def __init__(self, schema_path: Optional[Path] = None):
        """Initialize the validator.

        Args:
            schema_path: Path to JSON Schema file. If not provided, uses embedded schema.
        """
        self.schema_path = schema_path or (
            Path(__file__).parent.parent.parent / "schemas" / "unified-config.schema.json"
        )
        self._schema: Optional[dict] = None
        self._validator: Optional[Any] = None

    @property
    def schema(self) -> dict:
        """Load schema lazily."""
        if self._schema is None:
            if self.schema_path.exists():
                try:
                    with open(self.schema_path) as f:
                        self._schema = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load schema: {e}")
                    self._schema = self._get_minimal_schema()
            else:
                self._schema = self._get_minimal_schema()
        return self._schema

    @property
    def validator(self) -> Any:
        """Get or create JSON Schema validator."""
        if self._validator is None and JSONSCHEMA_AVAILABLE:
            self._validator = Draft7Validator(self.schema)
        return self._validator

    def validate(self, config: dict) -> ValidationResult:
        """Validate configuration and return detailed results.

        Args:
            config: Configuration dictionary to validate.

        Returns:
            ValidationResult with errors, warnings, and info.
        """
        errors: list[ConfigError] = []
        warnings: list[ConfigError] = []
        info: list[ConfigError] = []

        # Schema validation (if jsonschema is available)
        if JSONSCHEMA_AVAILABLE and self.validator:
            for error in self.validator.iter_errors(config):
                config_error = self._convert_schema_error(error)
                if self._is_critical_error(error):
                    errors.append(config_error)
                else:
                    warnings.append(config_error)

        # Semantic validation (always performed)
        semantic_issues = self._semantic_validation(config)
        for severity, issue in semantic_issues:
            if severity == "error":
                errors.append(issue)
            elif severity == "warning":
                warnings.append(issue)
            else:
                info.append(issue)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
        )

    def _convert_schema_error(self, error: Any) -> ConfigError:
        """Convert jsonschema error to user-friendly ConfigError."""
        path = ".".join(str(p) for p in error.path) or "root"

        # Get base message
        message = error.message

        # Add suggestion based on validator type
        validator = error.validator
        suggestion = self.ERROR_SUGGESTIONS.get(validator)

        # Customize message for common cases
        if validator == "enum":
            allowed = error.validator_value
            suggestion = f"Allowed values: {', '.join(repr(v) for v in allowed)}"
        elif validator == "type":
            expected = error.validator_value
            actual = type(error.instance).__name__
            message = f"Expected {expected}, got {actual}"
        elif validator == "required":
            missing = list(error.validator_value - set(error.instance.keys()))
            message = f"Missing required field(s): {', '.join(missing)}"
            suggestion = "Add the missing fields to your configuration"
        elif validator == "minimum":
            message = f"Value {error.instance} is below minimum {error.validator_value}"
        elif validator == "maximum":
            message = f"Value {error.instance} is above maximum {error.validator_value}"

        return ConfigError(path=path, message=message, suggestion=suggestion)

    def _is_critical_error(self, error: Any) -> bool:
        """Determine if a validation error is critical vs warning."""
        critical_validators = {"required", "type", "enum", "const"}
        return error.validator in critical_validators

    def _semantic_validation(self, config: dict) -> list[tuple[str, ConfigError]]:
        """Perform semantic validation beyond JSON Schema.

        Args:
            config: Configuration dictionary.

        Returns:
            List of (severity, ConfigError) tuples.
        """
        issues: list[tuple[str, ConfigError]] = []

        # Check for unknown top-level keys
        for key in config.keys():
            if key not in self.VALID_SECTIONS:
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path=key,
                            message=f"Unknown configuration section: '{key}'",
                            suggestion=f"Valid sections: {', '.join(sorted(self.VALID_SECTIONS))}",
                        ),
                    )
                )

        # Check API key presence based on provider
        issues.extend(self._validate_api_keys(config))

        # Check file patterns
        issues.extend(self._validate_file_patterns(config))

        # Check version
        issues.extend(self._validate_version(config))

        # Check project configuration
        issues.extend(self._validate_project(config))

        return issues

    def _validate_api_keys(self, config: dict) -> list[tuple[str, ConfigError]]:
        """Validate API key configuration."""
        issues: list[tuple[str, ConfigError]] = []

        api = config.get("api", {})
        embedding = config.get("embedding", {})
        provider = embedding.get("provider", "voyage")

        if provider == "openai":
            openai_key = api.get("openai", {}).get("api_key", "")
            if not openai_key:
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path="api.openai.api_key",
                            message="OpenAI API key not configured but 'openai' provider selected",
                            suggestion="Set OPENAI_API_KEY environment variable or add to config",
                        ),
                    )
                )
        elif provider == "voyage":
            voyage_key = api.get("voyage", {}).get("api_key", "")
            if not voyage_key:
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path="api.voyage.api_key",
                            message="Voyage API key not configured but 'voyage' provider selected",
                            suggestion="Set VOYAGE_API_KEY environment variable or add to config",
                        ),
                    )
                )

        # Check Qdrant URL
        qdrant_url = api.get("qdrant", {}).get("url", "")
        if qdrant_url and not (
            qdrant_url.startswith("http://") or qdrant_url.startswith("https://")
        ):
            issues.append(
                (
                    "error",
                    ConfigError(
                        path="api.qdrant.url",
                        message=f"Invalid Qdrant URL: '{qdrant_url}'",
                        suggestion="URL should start with http:// or https://",
                    ),
                )
            )

        return issues

    def _validate_file_patterns(self, config: dict) -> list[tuple[str, ConfigError]]:
        """Validate file pattern configuration."""
        issues: list[tuple[str, ConfigError]] = []

        indexing = config.get("indexing", {})
        patterns = indexing.get("file_patterns", indexing.get("filePatterns", {}))
        include = patterns.get("include", [])
        exclude = patterns.get("exclude", [])

        # Warn if no include patterns
        if not include:
            issues.append(
                (
                    "info",
                    ConfigError(
                        path="indexing.file_patterns.include",
                        message="No include patterns specified - defaults will be used",
                        suggestion="Add patterns like ['*.py', '*.js'] to customize indexing",
                    ),
                )
            )

        # Warn about potentially dangerous patterns
        dangerous_patterns = [".env", "*.env", ".env*", "**/secrets/*", "**/credentials/*"]
        for pattern in include:
            if pattern in dangerous_patterns or any(
                d in pattern for d in [".env", "secret", "credential", "password"]
            ):
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path="indexing.file_patterns.include",
                            message=f"Potentially sensitive pattern included: '{pattern}'",
                            suggestion="Consider moving to exclude patterns to prevent indexing secrets",
                        ),
                    )
                )

        # Check for conflicting patterns
        for inc in include:
            for exc in exclude:
                if inc == exc:
                    issues.append(
                        (
                            "warning",
                            ConfigError(
                                path="indexing.file_patterns",
                                message=f"Pattern '{inc}' appears in both include and exclude",
                                suggestion="Exclude takes precedence, but this may cause confusion",
                            ),
                        )
                    )
                    break

        return issues

    def _validate_version(self, config: dict) -> list[tuple[str, ConfigError]]:
        """Validate configuration version."""
        issues: list[tuple[str, ConfigError]] = []

        version = config.get("version")
        if version is None:
            issues.append(
                (
                    "info",
                    ConfigError(
                        path="version",
                        message="No version specified - assuming v3.0",
                        suggestion="Add 'version': '3.0' for clarity",
                    ),
                )
            )
        elif version not in ("3.0", "2.6"):
            issues.append(
                (
                    "warning",
                    ConfigError(
                        path="version",
                        message=f"Unknown config version: '{version}'",
                        suggestion="Use '3.0' for the latest format",
                    ),
                )
            )

        return issues

    def _validate_project(self, config: dict) -> list[tuple[str, ConfigError]]:
        """Validate project configuration."""
        issues: list[tuple[str, ConfigError]] = []

        project = config.get("project")
        if project is None:
            issues.append(
                (
                    "info",
                    ConfigError(
                        path="project",
                        message="No project configuration - defaults will be used",
                        suggestion="Add project.name and project.collection for better organization",
                    ),
                )
            )
        elif isinstance(project, dict):
            if not project.get("name"):
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path="project.name",
                            message="Project name not specified",
                            suggestion="Add a project name for better identification",
                        ),
                    )
                )
            if not project.get("collection"):
                issues.append(
                    (
                        "warning",
                        ConfigError(
                            path="project.collection",
                            message="Collection name not specified",
                            suggestion="Add a collection name to organize your index",
                        ),
                    )
                )

        return issues

    def _get_minimal_schema(self) -> dict:
        """Return minimal embedded schema for when schema file is not found."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "version": {"type": "string"},
                "project": {"type": "object"},
                "api": {"type": "object"},
                "embedding": {"type": "object"},
                "indexing": {"type": "object"},
                "watcher": {"type": "object"},
                "performance": {"type": "object"},
                "hooks": {"type": "object"},
                "guard": {"type": "object"},
                "logging": {"type": "object"},
            },
        }


def validate_config_file(path: Path) -> ValidationResult:
    """Validate a configuration file.

    Args:
        path: Path to the configuration file.

    Returns:
        ValidationResult with validation details.
    """
    validator = ConfigValidator()

    try:
        with open(path) as f:
            config = json.load(f)
        return validator.validate(config)
    except json.JSONDecodeError as e:
        return ValidationResult(
            valid=False,
            errors=[
                ConfigError(
                    path="",
                    message=f"Invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}",
                    suggestion="Check JSON syntax (missing commas, quotes, brackets)",
                )
            ],
        )
    except FileNotFoundError:
        return ValidationResult(
            valid=False,
            errors=[
                ConfigError(
                    path="",
                    message=f"Configuration file not found: {path}",
                    suggestion="Create the file or check the path",
                )
            ],
        )
    except PermissionError:
        return ValidationResult(
            valid=False,
            errors=[
                ConfigError(
                    path="",
                    message=f"Permission denied reading: {path}",
                    suggestion="Check file permissions",
                )
            ],
        )


def validate_config_dict(config: dict) -> ValidationResult:
    """Validate a configuration dictionary.

    Args:
        config: Configuration dictionary.

    Returns:
        ValidationResult with validation details.
    """
    validator = ConfigValidator()
    return validator.validate(config)
