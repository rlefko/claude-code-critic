"""Tests for CLI status module."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.cli.status import (
    StatusCollector,
    StatusLevel,
    SubsystemStatus,
    SystemStatus,
    format_status_text,
)


class TestStatusLevel:
    """Tests for StatusLevel enum."""

    def test_levels_exist(self):
        """Test that all expected levels exist."""
        assert StatusLevel.OK.value == "ok"
        assert StatusLevel.WARN.value == "warn"
        assert StatusLevel.FAIL.value == "fail"
        assert StatusLevel.UNKNOWN.value == "unknown"


class TestSubsystemStatus:
    """Tests for SubsystemStatus dataclass."""

    def test_basic_creation(self):
        """Test basic status creation."""
        status = SubsystemStatus(
            name="Qdrant",
            level=StatusLevel.OK,
            message="Connected",
        )
        assert status.name == "Qdrant"
        assert status.level == StatusLevel.OK
        assert status.message == "Connected"
        assert status.details == {}

    def test_with_details(self):
        """Test status with details."""
        status = SubsystemStatus(
            name="Qdrant",
            level=StatusLevel.OK,
            message="Connected",
            details={"url": "localhost:6333"},
        )
        assert status.details["url"] == "localhost:6333"

    def test_to_dict(self):
        """Test conversion to dictionary."""
        status = SubsystemStatus(
            name="Qdrant",
            level=StatusLevel.OK,
            message="Connected",
            details={"collections": 5},
        )
        result = status.to_dict()
        assert result["name"] == "Qdrant"
        assert result["level"] == "ok"
        assert result["message"] == "Connected"
        assert result["details"]["collections"] == 5


class TestSystemStatus:
    """Tests for SystemStatus dataclass."""

    def test_empty_status(self):
        """Test empty system status."""
        status = SystemStatus()
        assert status.qdrant is None
        assert status.service is None
        assert status.hooks is None
        assert status.index is None
        assert status.health is None
        assert status.timestamp is not None

    def test_with_subsystems(self):
        """Test status with subsystems."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
            service=SubsystemStatus("Service", StatusLevel.WARN, "Not running"),
        )
        assert status.qdrant.level == StatusLevel.OK
        assert status.service.level == StatusLevel.WARN

    def test_overall_level_ok(self):
        """Test overall level is OK when all subsystems are OK."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
            health=SubsystemStatus("Health", StatusLevel.OK, "All good"),
        )
        assert status.overall_level == StatusLevel.OK

    def test_overall_level_warn(self):
        """Test overall level is WARN when any subsystem warns."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
            service=SubsystemStatus("Service", StatusLevel.WARN, "Not running"),
        )
        assert status.overall_level == StatusLevel.WARN

    def test_overall_level_fail(self):
        """Test overall level is FAIL when any subsystem fails."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.FAIL, "Disconnected"),
            service=SubsystemStatus("Service", StatusLevel.OK, "Running"),
        )
        assert status.overall_level == StatusLevel.FAIL

    def test_overall_level_unknown_empty(self):
        """Test overall level is UNKNOWN when no subsystems."""
        status = SystemStatus()
        assert status.overall_level == StatusLevel.UNKNOWN

    def test_to_dict(self):
        """Test conversion to dictionary."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
        )
        result = status.to_dict()
        assert "timestamp" in result
        assert "overall" in result
        assert "subsystems" in result
        assert "qdrant" in result["subsystems"]

    def test_to_json(self):
        """Test conversion to JSON."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
        )
        json_str = status.to_json()
        parsed = json.loads(json_str)
        assert parsed["overall"] == "ok"


class TestStatusCollector:
    """Tests for StatusCollector class."""

    def test_init_no_args(self):
        """Test initialization without arguments."""
        collector = StatusCollector()
        assert collector.project_path is None
        assert collector.collection_name is None

    def test_init_with_project(self):
        """Test initialization with project path."""
        collector = StatusCollector(project_path="/path/to/project")
        assert collector.project_path == Path("/path/to/project")

    def test_init_with_collection(self):
        """Test initialization with collection name."""
        collector = StatusCollector(collection_name="my-collection")
        assert collector.collection_name == "my-collection"

    @patch("qdrant_client.QdrantClient")
    def test_collect_qdrant_success(self, mock_client_class):
        """Test collecting Qdrant status when connected."""
        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = [MagicMock(), MagicMock()]
        mock_client.get_collections.return_value = mock_collections
        mock_client_class.return_value = mock_client

        collector = StatusCollector()
        collector._config = MagicMock(qdrant_url="http://localhost:6333", qdrant_api_key=None)
        status = collector.collect_qdrant()

        assert status.level == StatusLevel.OK
        assert "Connected" in status.message
        assert status.details["collections"] == 2

    @patch("qdrant_client.QdrantClient")
    def test_collect_qdrant_failure(self, mock_client_class):
        """Test collecting Qdrant status when disconnected."""
        mock_client_class.side_effect = Exception("Connection refused")

        collector = StatusCollector()
        status = collector.collect_qdrant()

        assert status.level == StatusLevel.FAIL
        assert "failed" in status.message.lower()

    def test_collect_hooks_no_project(self):
        """Test collecting hooks status without project."""
        collector = StatusCollector()
        status = collector.collect_hooks()

        assert status.level == StatusLevel.UNKNOWN
        assert "No project" in status.message

    def test_collect_hooks_with_project(self, tmp_path):
        """Test collecting hooks status with project."""
        # Create a project with hooks
        claude_hooks = tmp_path / ".claude" / "hooks"
        claude_hooks.mkdir(parents=True)
        (claude_hooks / "after-write.sh").touch()

        collector = StatusCollector(project_path=tmp_path)
        status = collector.collect_hooks()

        assert status.level == StatusLevel.OK
        assert "Installed" in status.message

    def test_collect_hooks_no_hooks(self, tmp_path):
        """Test collecting hooks status when none installed."""
        collector = StatusCollector(project_path=tmp_path)
        status = collector.collect_hooks()

        assert status.level == StatusLevel.WARN
        assert "No hooks" in status.message

    def test_collect_index_no_project(self):
        """Test collecting index status without project."""
        collector = StatusCollector()
        status = collector.collect_index()

        assert status.level == StatusLevel.UNKNOWN

    def test_collect_index_not_indexed(self, tmp_path):
        """Test collecting index status when not indexed."""
        collector = StatusCollector(
            project_path=tmp_path,
            collection_name="test-collection",
        )
        status = collector.collect_index()

        assert status.level == StatusLevel.WARN
        assert "Not indexed" in status.message

    def test_collect_index_with_state(self, tmp_path):
        """Test collecting index status with state file."""
        # Create state file
        cache_dir = tmp_path / ".index_cache"
        cache_dir.mkdir()
        state_file = cache_dir / "state.json"
        state_file.write_text(json.dumps({
            "_file_count": 100,
            "_last_indexed_time": datetime.now().isoformat(),
        }))

        collector = StatusCollector(
            project_path=tmp_path,
            collection_name="test-collection",
        )
        status = collector.collect_index()

        assert status.level == StatusLevel.OK
        assert "100 files" in status.message

    @patch("claude_indexer.doctor.manager.DoctorManager")
    def test_collect_health_success(self, mock_manager_class):
        """Test collecting health status."""
        mock_manager = MagicMock()
        mock_result = MagicMock()
        mock_result.passed = 5
        mock_result.warnings = 0
        mock_result.failures = 0
        mock_result.skipped = 0
        mock_manager.run_quick.return_value = mock_result
        mock_manager_class.return_value = mock_manager

        collector = StatusCollector()
        status = collector.collect_health()

        assert status.level == StatusLevel.OK
        assert "5/5" in status.message

    @patch("claude_indexer.doctor.manager.DoctorManager")
    def test_collect_health_with_warnings(self, mock_manager_class):
        """Test collecting health status with warnings."""
        mock_manager = MagicMock()
        mock_result = MagicMock()
        mock_result.passed = 4
        mock_result.warnings = 1
        mock_result.failures = 0
        mock_result.skipped = 0
        mock_manager.run_quick.return_value = mock_result
        mock_manager_class.return_value = mock_manager

        collector = StatusCollector()
        status = collector.collect_health()

        assert status.level == StatusLevel.WARN

    def test_collect_all(self):
        """Test collecting all statuses."""
        collector = StatusCollector()

        # Mock all collect methods
        with patch.object(collector, "collect_qdrant") as mock_qdrant, \
             patch.object(collector, "collect_service") as mock_service, \
             patch.object(collector, "collect_hooks") as mock_hooks, \
             patch.object(collector, "collect_index") as mock_index, \
             patch.object(collector, "collect_health") as mock_health:

            mock_qdrant.return_value = SubsystemStatus("Qdrant", StatusLevel.OK, "OK")
            mock_service.return_value = SubsystemStatus("Service", StatusLevel.WARN, "Warn")
            mock_hooks.return_value = SubsystemStatus("Hooks", StatusLevel.OK, "OK")
            mock_index.return_value = SubsystemStatus("Index", StatusLevel.UNKNOWN, "Unknown")
            mock_health.return_value = SubsystemStatus("Health", StatusLevel.OK, "OK")

            status = collector.collect_all()

            assert status.qdrant is not None
            assert status.service is not None
            assert status.hooks is not None
            assert status.index is not None
            assert status.health is not None


class TestFormatStatusText:
    """Tests for format_status_text function."""

    def test_basic_format(self):
        """Test basic text formatting."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
        )
        result = format_status_text(status, use_color=False)

        assert "Claude Indexer Status" in result
        assert "Qdrant" in result
        assert "[OK]" in result
        assert "Connected" in result

    def test_format_with_color(self):
        """Test formatting with colors."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
        )
        result = format_status_text(status, use_color=True)

        assert "\033[92m" in result  # Green for OK

    def test_format_all_levels(self):
        """Test formatting all status levels."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "OK"),
            service=SubsystemStatus("Service", StatusLevel.WARN, "Warning"),
            hooks=SubsystemStatus("Hooks", StatusLevel.FAIL, "Failed"),
            index=SubsystemStatus("Index", StatusLevel.UNKNOWN, "Unknown"),
        )
        result = format_status_text(status, use_color=False)

        assert "[OK]" in result
        assert "[WARN]" in result
        assert "[FAIL]" in result
        assert "[--]" in result

    def test_verbose_includes_details(self):
        """Test verbose mode includes details."""
        status = SystemStatus(
            qdrant=SubsystemStatus(
                "Qdrant",
                StatusLevel.OK,
                "Connected",
                details={"collections": 5},
            ),
        )
        result = format_status_text(status, use_color=False, verbose=True)

        assert "collections: 5" in result

    def test_overall_status(self):
        """Test overall status in output."""
        status = SystemStatus(
            qdrant=SubsystemStatus("Qdrant", StatusLevel.OK, "Connected"),
        )
        result = format_status_text(status, use_color=False)

        assert "Overall:" in result
