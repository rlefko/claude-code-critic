"""Type definitions for the doctor module."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CheckStatus(Enum):
    """Status of a health check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckCategory(Enum):
    """Category of health checks for grouping in output."""

    PYTHON = "Python Environment"
    SERVICES = "External Services"
    API_KEYS = "API Keys"
    PROJECT = "Project Status"


@dataclass
class CheckResult:
    """Result of a single health check."""

    name: str
    category: CheckCategory
    status: CheckStatus
    message: str
    suggestion: str | None = None
    details: dict[str, Any] | None = None


@dataclass
class DoctorOptions:
    """Configuration options for the doctor command."""

    project_path: Path | None = None
    collection_name: str | None = None
    verbose: bool = False
    json_output: bool = False


@dataclass
class DoctorResult:
    """Complete result of all health checks."""

    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        """Count of passed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)

    @property
    def warnings(self) -> int:
        """Count of warning checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)

    @property
    def failures(self) -> int:
        """Count of failed checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)

    @property
    def skipped(self) -> int:
        """Count of skipped checks."""
        return sum(1 for c in self.checks if c.status == CheckStatus.SKIP)

    @property
    def success(self) -> bool:
        """Overall success (no failures)."""
        return self.failures == 0

    def add_check(self, check: CheckResult) -> None:
        """Add a check result."""
        self.checks.append(check)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "checks": [
                {
                    "name": c.name,
                    "category": c.category.value,
                    "status": c.status.value,
                    "message": c.message,
                    "suggestion": c.suggestion,
                    "details": c.details,
                }
                for c in self.checks
            ],
            "summary": {
                "passed": self.passed,
                "warnings": self.warnings,
                "failures": self.failures,
                "skipped": self.skipped,
                "success": self.success,
            },
        }
