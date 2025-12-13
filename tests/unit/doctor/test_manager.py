"""Tests for DoctorManager."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_indexer.doctor.manager import DoctorManager
from claude_indexer.doctor.types import (
    DoctorOptions,
)


class TestDoctorManager:
    """Tests for DoctorManager class."""

    @pytest.fixture
    def default_options(self) -> DoctorOptions:
        """Create default options."""
        return DoctorOptions()

    @pytest.fixture
    def project_options(self, tmp_path: Path) -> DoctorOptions:
        """Create options with project path."""
        return DoctorOptions(
            project_path=tmp_path,
            collection_name="test-collection",
        )

    def test_runs_all_basic_checks(self, default_options: DoctorOptions):
        """Test that manager runs all basic checks without project path."""
        manager = DoctorManager(default_options)
        result = manager.run()

        # Should run basic checks (Python, services, API keys)
        # Without project path, should NOT run project checks
        check_names = [c.name for c in result.checks]

        assert "python_version" in check_names
        assert "package_installed" in check_names
        assert "qdrant_connection" in check_names
        assert "claude_cli" in check_names
        assert "openai_api_key" in check_names
        assert "voyage_api_key" in check_names

        # Should NOT include project checks
        assert "project_initialized" not in check_names
        assert "collection_exists" not in check_names

    def test_runs_project_checks_with_path(self, project_options: DoctorOptions):
        """Test that manager runs project checks when path is provided."""
        manager = DoctorManager(project_options)
        result = manager.run()

        check_names = [c.name for c in result.checks]

        # Should include project checks
        assert "project_initialized" in check_names
        assert "collection_exists" in check_names

    def test_skips_collection_check_without_name(self, tmp_path: Path):
        """Test that collection check is skipped when no collection name."""
        options = DoctorOptions(project_path=tmp_path, collection_name=None)
        manager = DoctorManager(options)
        result = manager.run()

        check_names = [c.name for c in result.checks]
        assert "project_initialized" in check_names
        assert "collection_exists" not in check_names

    def test_handles_config_loading_failure(self, default_options: DoctorOptions):
        """Test graceful handling of config loading failure."""
        mock_loader = MagicMock()
        mock_loader.load.side_effect = Exception("Config error")

        manager = DoctorManager(default_options, config_loader=mock_loader)

        # Should not raise, should still run checks
        result = manager.run()
        assert len(result.checks) > 0

    def test_run_quick_checks(self, default_options: DoctorOptions):
        """Test quick check mode runs only essential checks."""
        manager = DoctorManager(default_options)
        result = manager.run_quick()

        check_names = [c.name for c in result.checks]

        # Quick checks only include Python and Qdrant
        assert "python_version" in check_names
        assert "qdrant_connection" in check_names

        # Should NOT include other checks
        assert "package_installed" not in check_names
        assert "claude_cli" not in check_names
        assert "openai_api_key" not in check_names

    def test_result_aggregation(self, default_options: DoctorOptions):
        """Test that results are properly aggregated."""
        manager = DoctorManager(default_options)
        result = manager.run()

        # Verify that results are aggregated correctly
        total = result.passed + result.warnings + result.failures + result.skipped
        assert total == len(result.checks)

    def test_uses_custom_config_loader(self, default_options: DoctorOptions):
        """Test that custom config loader is used."""
        mock_loader = MagicMock()
        mock_config = MagicMock()
        mock_loader.load.return_value = mock_config

        manager = DoctorManager(default_options, config_loader=mock_loader)
        manager._load_config()

        mock_loader.load.assert_called_once()


class TestDoctorManagerIntegration:
    """Integration tests for DoctorManager."""

    def test_full_run_no_exceptions(self):
        """Test that a full run completes without exceptions."""
        options = DoctorOptions()
        manager = DoctorManager(options)

        # Should complete without raising
        result = manager.run()

        # Should have results
        assert len(result.checks) >= 6  # At least 6 basic checks
        assert (
            result.passed + result.warnings + result.failures + result.skipped
            == len(result.checks)
        )

    def test_full_run_with_project_path(self, tmp_path: Path):
        """Test full run with project path."""
        options = DoctorOptions(
            project_path=tmp_path,
            collection_name="test-collection",
        )
        manager = DoctorManager(options)

        result = manager.run()

        # Should have project checks
        check_names = [c.name for c in result.checks]
        assert "project_initialized" in check_names

    def test_json_output_structure(self):
        """Test that to_dict produces valid structure."""
        options = DoctorOptions()
        manager = DoctorManager(options)
        result = manager.run()

        data = result.to_dict()

        assert "checks" in data
        assert "summary" in data
        assert isinstance(data["checks"], list)
        assert isinstance(data["summary"], dict)

        for check in data["checks"]:
            assert "name" in check
            assert "category" in check
            assert "status" in check
            assert "message" in check
