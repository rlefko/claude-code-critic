"""Tests for doctor types."""

from pathlib import Path

import pytest

from claude_indexer.doctor.types import (
    CheckCategory,
    CheckResult,
    CheckStatus,
    DoctorOptions,
    DoctorResult,
)


class TestCheckStatus:
    """Tests for CheckStatus enum."""

    def test_status_values(self):
        """Test that all status values are defined."""
        assert CheckStatus.PASS.value == "pass"
        assert CheckStatus.WARN.value == "warn"
        assert CheckStatus.FAIL.value == "fail"
        assert CheckStatus.SKIP.value == "skip"

    def test_all_statuses_exist(self):
        """Test that we have exactly 4 statuses."""
        assert len(CheckStatus) == 4


class TestCheckCategory:
    """Tests for CheckCategory enum."""

    def test_category_values(self):
        """Test that all category values are defined."""
        assert CheckCategory.PYTHON.value == "Python Environment"
        assert CheckCategory.SERVICES.value == "External Services"
        assert CheckCategory.API_KEYS.value == "API Keys"
        assert CheckCategory.PROJECT.value == "Project Status"

    def test_all_categories_exist(self):
        """Test that we have exactly 4 categories."""
        assert len(CheckCategory) == 4


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_basic_creation(self):
        """Test creating a basic check result."""
        result = CheckResult(
            name="test_check",
            category=CheckCategory.PYTHON,
            status=CheckStatus.PASS,
            message="Test passed",
        )
        assert result.name == "test_check"
        assert result.category == CheckCategory.PYTHON
        assert result.status == CheckStatus.PASS
        assert result.message == "Test passed"
        assert result.suggestion is None
        assert result.details is None

    def test_creation_with_all_fields(self):
        """Test creating a check result with all fields."""
        result = CheckResult(
            name="test_check",
            category=CheckCategory.SERVICES,
            status=CheckStatus.FAIL,
            message="Connection failed",
            suggestion="Check your connection",
            details={"error": "timeout"},
        )
        assert result.suggestion == "Check your connection"
        assert result.details == {"error": "timeout"}


class TestDoctorOptions:
    """Tests for DoctorOptions dataclass."""

    def test_default_options(self):
        """Test default option values."""
        options = DoctorOptions()
        assert options.project_path is None
        assert options.collection_name is None
        assert options.verbose is False
        assert options.json_output is False

    def test_custom_options(self):
        """Test custom option values."""
        options = DoctorOptions(
            project_path=Path("/test"),
            collection_name="test-collection",
            verbose=True,
            json_output=True,
        )
        assert options.project_path == Path("/test")
        assert options.collection_name == "test-collection"
        assert options.verbose is True
        assert options.json_output is True


class TestDoctorResult:
    """Tests for DoctorResult dataclass."""

    def test_empty_result(self):
        """Test empty result properties."""
        result = DoctorResult()
        assert result.passed == 0
        assert result.warnings == 0
        assert result.failures == 0
        assert result.skipped == 0
        assert result.success is True  # No failures = success
        assert result.checks == []

    def test_passed_count(self):
        """Test passed count calculation."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.PASS, "ok"))
        result.add_check(CheckResult("b", CheckCategory.PYTHON, CheckStatus.PASS, "ok"))
        result.add_check(CheckResult("c", CheckCategory.PYTHON, CheckStatus.WARN, "warn"))
        assert result.passed == 2

    def test_warnings_count(self):
        """Test warnings count calculation."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.WARN, "w1"))
        result.add_check(CheckResult("b", CheckCategory.PYTHON, CheckStatus.WARN, "w2"))
        result.add_check(CheckResult("c", CheckCategory.PYTHON, CheckStatus.PASS, "ok"))
        assert result.warnings == 2

    def test_failures_count(self):
        """Test failures count calculation."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.FAIL, "f1"))
        result.add_check(CheckResult("b", CheckCategory.PYTHON, CheckStatus.PASS, "ok"))
        assert result.failures == 1

    def test_skipped_count(self):
        """Test skipped count calculation."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.SKIP, "s1"))
        result.add_check(CheckResult("b", CheckCategory.PYTHON, CheckStatus.SKIP, "s2"))
        assert result.skipped == 2

    def test_success_with_failures(self):
        """Test success is False when there are failures."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.FAIL, "f1"))
        assert result.success is False

    def test_success_with_only_warnings(self):
        """Test success is True when there are only warnings."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.WARN, "w1"))
        assert result.success is True

    def test_add_check(self):
        """Test adding checks."""
        result = DoctorResult()
        check = CheckResult("a", CheckCategory.PYTHON, CheckStatus.PASS, "ok")
        result.add_check(check)
        assert len(result.checks) == 1
        assert result.checks[0] == check

    def test_to_dict(self):
        """Test JSON serialization."""
        result = DoctorResult()
        result.add_check(
            CheckResult(
                name="test",
                category=CheckCategory.PYTHON,
                status=CheckStatus.PASS,
                message="ok",
                suggestion="hint",
                details={"key": "value"},
            )
        )

        data = result.to_dict()
        assert "checks" in data
        assert "summary" in data
        assert len(data["checks"]) == 1
        assert data["checks"][0]["name"] == "test"
        assert data["checks"][0]["category"] == "Python Environment"
        assert data["checks"][0]["status"] == "pass"
        assert data["summary"]["passed"] == 1
        assert data["summary"]["success"] is True

    def test_mixed_results(self):
        """Test with mixed results."""
        result = DoctorResult()
        result.add_check(CheckResult("a", CheckCategory.PYTHON, CheckStatus.PASS, "ok"))
        result.add_check(CheckResult("b", CheckCategory.SERVICES, CheckStatus.WARN, "warn"))
        result.add_check(CheckResult("c", CheckCategory.API_KEYS, CheckStatus.FAIL, "fail"))
        result.add_check(CheckResult("d", CheckCategory.PROJECT, CheckStatus.SKIP, "skip"))

        assert result.passed == 1
        assert result.warnings == 1
        assert result.failures == 1
        assert result.skipped == 1
        assert result.success is False
