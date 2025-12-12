"""Tests for init manager functionality."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from claude_indexer.init.manager import InitManager
from claude_indexer.init.types import InitOptions, InitResult, ProjectType


class TestInitManager:
    """Tests for InitManager class."""

    @pytest.fixture
    def init_options(self, tmp_path: Path) -> InitOptions:
        """Create default init options."""
        return InitOptions(
            project_path=tmp_path,
            collection_name="test-collection",
            no_index=True,  # Skip indexing in tests
            no_hooks=True,  # Skip hooks in tests
        )

    def test_init_creates_basic_files(self, tmp_path: Path, init_options: InitOptions):
        """Test that init creates basic configuration files."""
        manager = InitManager(init_options)
        result = manager.run()

        assert result.success
        assert (tmp_path / ".claudeignore").exists()
        assert (tmp_path / ".claude" / "settings.local.json").exists()
        assert (tmp_path / ".claude" / "guard.config.json").exists()
        assert (tmp_path / ".claude-indexer" / "config.json").exists()

    def test_init_result_has_correct_metadata(self, tmp_path: Path, init_options: InitOptions):
        """Test that init result contains correct metadata."""
        manager = InitManager(init_options)
        result = manager.run()

        assert result.project_path == tmp_path
        assert result.collection_name == "test-collection"
        assert isinstance(result.project_type, ProjectType)

    def test_init_auto_detects_collection_name(self, tmp_path: Path):
        """Test auto-detection of collection name."""
        options = InitOptions(
            project_path=tmp_path,
            collection_name=None,  # Should auto-derive
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        # Collection name should be derived from project path
        # Note: underscores are replaced with hyphens during sanitization
        assert result.collection_name
        expected = tmp_path.name.lower().replace("_", "-")
        assert result.collection_name == expected

    def test_init_auto_detects_project_type(self, tmp_path: Path):
        """Test auto-detection of project type."""
        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[build-system]")

        options = InitOptions(
            project_path=tmp_path,
            project_type=None,  # Should auto-detect
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        assert result.project_type == ProjectType.PYTHON

    def test_init_uses_provided_project_type(self, tmp_path: Path):
        """Test that provided project type is used."""
        options = InitOptions(
            project_path=tmp_path,
            project_type=ProjectType.TYPESCRIPT,
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        assert result.project_type == ProjectType.TYPESCRIPT

    def test_init_skips_existing_without_force(self, tmp_path: Path, init_options: InitOptions):
        """Test that init skips existing files without force."""
        # Pre-create files
        (tmp_path / ".claudeignore").write_text("# Custom")

        manager = InitManager(init_options)
        result = manager.run()

        # Should have skipped .claudeignore
        claudeignore_step = next(s for s in result.steps if s.step_name == "claudeignore")
        assert claudeignore_step.skipped

        # Content should be unchanged
        assert (tmp_path / ".claudeignore").read_text() == "# Custom"

    def test_init_overwrites_with_force(self, tmp_path: Path):
        """Test that init overwrites files with force flag."""
        # Pre-create file
        (tmp_path / ".claudeignore").write_text("# Custom")

        options = InitOptions(
            project_path=tmp_path,
            force=True,
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        # Should not have skipped .claudeignore
        claudeignore_step = next(s for s in result.steps if s.step_name == "claudeignore")
        assert not claudeignore_step.skipped

        # Content should be changed
        assert (tmp_path / ".claudeignore").read_text() != "# Custom"

    def test_init_respects_no_hooks_flag(self, tmp_path: Path):
        """Test that --no-hooks skips hook installation."""
        options = InitOptions(
            project_path=tmp_path,
            no_hooks=True,
            no_index=True,
        )

        manager = InitManager(options)
        result = manager.run()

        # Should have a skipped hooks step
        hooks_step = next(
            (s for s in result.steps if s.step_name == "hooks"),
            None
        )
        if hooks_step:
            assert hooks_step.skipped

    def test_init_respects_no_index_flag(self, tmp_path: Path):
        """Test that --no-index skips indexing."""
        options = InitOptions(
            project_path=tmp_path,
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        # Should have a skipped indexing step
        index_step = next(s for s in result.steps if s.step_name == "indexing")
        assert index_step.skipped

    def test_get_status(self, tmp_path: Path, init_options: InitOptions):
        """Test get_status method."""
        manager = InitManager(init_options)

        # Before init
        status_before = manager.get_status()
        assert status_before["files"][".claudeignore"] is False

        # After init
        manager.run()
        status_after = manager.get_status()
        assert status_after["files"][".claudeignore"] is True

    @patch("claude_indexer.init.collection_manager.CollectionManager._get_store")
    def test_init_graceful_qdrant_failure(self, mock_store, tmp_path: Path):
        """Test that init continues if Qdrant is unavailable."""
        mock_store.return_value = None  # Simulate Qdrant unavailable

        options = InitOptions(
            project_path=tmp_path,
            no_index=True,
            no_hooks=True,
        )

        manager = InitManager(options)
        result = manager.run()

        # Should still succeed overall
        assert result.success

        # Should have warning about Qdrant
        qdrant_step = next(s for s in result.steps if s.step_name == "qdrant_collection")
        assert qdrant_step.skipped
        assert qdrant_step.warning

    def test_init_result_tracks_warnings(self, tmp_path: Path, init_options: InitOptions):
        """Test that warnings are properly tracked."""
        manager = InitManager(init_options)
        result = manager.run()

        # Warnings list should exist
        assert isinstance(result.warnings, list)

    def test_init_result_tracks_errors(self, tmp_path: Path, init_options: InitOptions):
        """Test that errors are properly tracked."""
        manager = InitManager(init_options)
        result = manager.run()

        # Errors list should exist
        assert isinstance(result.errors, list)


class TestInitOptions:
    """Tests for InitOptions dataclass."""

    def test_default_values(self, tmp_path: Path):
        """Test default option values."""
        options = InitOptions(project_path=tmp_path)

        assert options.collection_name is None
        assert options.project_type is None
        assert options.no_index is False
        assert options.no_hooks is False
        assert options.force is False
        assert options.verbose is False
        assert options.quiet is False

    def test_custom_values(self, tmp_path: Path):
        """Test custom option values."""
        options = InitOptions(
            project_path=tmp_path,
            collection_name="custom",
            project_type=ProjectType.PYTHON,
            no_index=True,
            force=True,
        )

        assert options.collection_name == "custom"
        assert options.project_type == ProjectType.PYTHON
        assert options.no_index is True
        assert options.force is True


class TestInitResult:
    """Tests for InitResult dataclass."""

    def test_add_step(self, tmp_path: Path):
        """Test adding steps to result."""
        from claude_indexer.init.types import InitStepResult

        result = InitResult(
            success=True,
            project_path=tmp_path,
            collection_name="test",
            project_type=ProjectType.GENERIC,
        )

        step = InitStepResult(
            step_name="test_step",
            success=True,
            message="Test completed",
        )

        result.add_step(step)

        assert len(result.steps) == 1
        assert result.steps[0].step_name == "test_step"

    def test_add_step_tracks_warnings(self, tmp_path: Path):
        """Test that warnings are tracked when adding steps."""
        from claude_indexer.init.types import InitStepResult

        result = InitResult(
            success=True,
            project_path=tmp_path,
            collection_name="test",
            project_type=ProjectType.GENERIC,
        )

        step = InitStepResult(
            step_name="test_step",
            success=True,
            message="Test completed",
            warning="Something to note",
        )

        result.add_step(step)

        assert "Something to note" in result.warnings

    def test_update_success(self, tmp_path: Path):
        """Test update_success method."""
        from claude_indexer.init.types import InitStepResult

        result = InitResult(
            success=True,
            project_path=tmp_path,
            collection_name="test",
            project_type=ProjectType.GENERIC,
        )

        # Add failing step
        result.add_step(InitStepResult(
            step_name="failing",
            success=False,
            message="Failed",
        ))

        result.update_success()
        assert result.success is False
