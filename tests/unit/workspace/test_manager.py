"""Unit tests for workspace manager module."""

import json
import time

import pytest

from claude_indexer.workspace.manager import (
    WorkspaceManager,
    detect_workspace,
    get_workspace_context,
)
from claude_indexer.workspace.types import (
    WorkspaceType,
)


class TestWorkspaceManager:
    """Tests for WorkspaceManager class."""

    @pytest.fixture
    def pnpm_workspace(self, tmp_path):
        """Create a pnpm workspace for testing."""
        # Create pnpm-workspace.yaml
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")

        # Create packages
        pkg1 = tmp_path / "packages" / "core"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "core"}')

        pkg2 = tmp_path / "packages" / "utils"
        pkg2.mkdir(parents=True)
        (pkg2 / "package.json").write_text('{"name": "utils"}')

        return tmp_path

    @pytest.fixture
    def vscode_workspace(self, tmp_path):
        """Create a VS Code workspace for testing."""
        # Create folders
        project_a = tmp_path / "project-a"
        project_a.mkdir()
        project_b = tmp_path / "project-b"
        project_b.mkdir()

        # Create .code-workspace file
        ws_file = tmp_path / "test.code-workspace"
        ws_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": "project-a"},
                        {"path": "project-b"},
                    ]
                }
            )
        )

        return tmp_path

    def test_detect_pnpm(self, pnpm_workspace):
        """Test detecting pnpm workspace."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        config = manager.detect()

        assert config.workspace_type == WorkspaceType.PNPM
        assert config.root_path == pnpm_workspace
        assert len(config.members) == 2

    def test_detect_vscode(self, vscode_workspace):
        """Test detecting VS Code workspace."""
        manager = WorkspaceManager(workspace_path=vscode_workspace)
        config = manager.detect()

        assert config.workspace_type == WorkspaceType.VSCODE_MULTI_ROOT
        assert len(config.members) == 2

    def test_is_workspace_true(self, pnpm_workspace):
        """Test is_workspace returns True for workspace."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        assert manager.is_workspace() is True

    def test_is_workspace_false(self, tmp_path):
        """Test is_workspace returns False for non-workspace."""
        manager = WorkspaceManager(workspace_path=tmp_path)
        assert manager.is_workspace() is False

    def test_initialize_creates_context(self, pnpm_workspace):
        """Test initialize creates workspace context."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        context = manager.initialize()

        assert context is not None
        assert context.workspace_id.startswith("ws_")
        assert context.workspace_config.workspace_type == WorkspaceType.PNPM
        assert len(context.members) == 2

    def test_initialize_raises_for_non_workspace(self, tmp_path):
        """Test initialize raises ValueError for non-workspace."""
        manager = WorkspaceManager(workspace_path=tmp_path)

        with pytest.raises(ValueError, match="Not in a workspace"):
            manager.initialize()

    def test_initialize_saves_state(self, pnpm_workspace):
        """Test initialize saves state file."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        context = manager.initialize()

        state_file = pnpm_workspace / ".claude-indexer" / "workspace.json"
        assert state_file.exists()

        with open(state_file) as f:
            data = json.load(f)

        assert data["workspace_id"] == context.workspace_id
        assert data["workspace_type"] == "pnpm"

    def test_initialize_resumes_existing(self, pnpm_workspace):
        """Test initialize resumes existing valid session."""
        manager1 = WorkspaceManager(workspace_path=pnpm_workspace)
        context1 = manager1.initialize()
        manager1.cleanup()

        manager2 = WorkspaceManager(workspace_path=pnpm_workspace)
        context2 = manager2.initialize()

        assert context2.workspace_id == context1.workspace_id

    def test_initialize_creates_new_if_expired(self, pnpm_workspace):
        """Test initialize creates new session if expired."""
        manager1 = WorkspaceManager(workspace_path=pnpm_workspace)
        context1 = manager1.initialize()

        # Manually expire the session
        state_file = pnpm_workspace / ".claude-indexer" / "workspace.json"
        with open(state_file) as f:
            data = json.load(f)
        data["last_activity"] = time.time() - (25 * 3600)  # 25 hours ago
        with open(state_file, "w") as f:
            json.dump(data, f)

        manager2 = WorkspaceManager(workspace_path=pnpm_workspace)
        context2 = manager2.initialize()

        assert context2.workspace_id != context1.workspace_id

    def test_get_config_loader(self, pnpm_workspace):
        """Test get_config_loader returns config loader."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        loader = manager.get_config_loader()

        assert loader is not None
        assert loader.workspace_config.workspace_type == WorkspaceType.PNPM

    def test_get_indexing_paths_monorepo(self, pnpm_workspace):
        """Test get_indexing_paths for monorepo returns root."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        manager.initialize()
        paths = manager.get_indexing_paths()

        assert len(paths) == 1
        assert paths[0] == pnpm_workspace

    def test_get_indexing_paths_multi_root(self, vscode_workspace):
        """Test get_indexing_paths for multi-root returns members."""
        manager = WorkspaceManager(workspace_path=vscode_workspace)
        manager.initialize()
        paths = manager.get_indexing_paths()

        assert len(paths) == 2

    def test_get_member_by_name_found(self, pnpm_workspace):
        """Test get_member_by_name when member exists."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        member = manager.get_member_by_name("core")

        assert member is not None
        assert member.name == "core"

    def test_get_member_by_name_not_found(self, pnpm_workspace):
        """Test get_member_by_name when member doesn't exist."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        member = manager.get_member_by_name("nonexistent")

        assert member is None

    def test_get_member_by_path(self, pnpm_workspace):
        """Test get_member_by_path."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        file_path = pnpm_workspace / "packages" / "core" / "src" / "index.ts"
        member = manager.get_member_by_path(file_path)

        assert member is not None
        assert member.name == "core"

    def test_get_collection_for_member(self, pnpm_workspace):
        """Test get_collection_for_member."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        collection = manager.get_collection_for_member("core")

        assert collection is not None
        # For monorepo, all members use same collection
        assert collection == manager.detect().collection_name

    def test_get_all_collections_monorepo(self, pnpm_workspace):
        """Test get_all_collections for monorepo."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        collections = manager.get_all_collections()

        assert len(collections) == 1

    def test_get_all_collections_multi_root(self, vscode_workspace):
        """Test get_all_collections for multi-root."""
        manager = WorkspaceManager(workspace_path=vscode_workspace)
        collections = manager.get_all_collections()

        assert len(collections) == 2

    def test_create_workspace_config(self, pnpm_workspace):
        """Test create_workspace_config creates config file."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        manager.initialize()
        config_path = manager.create_workspace_config()

        assert config_path.exists()
        assert config_path.name == "workspace.config.json"

        with open(config_path) as f:
            data = json.load(f)

        assert data["workspace_type"] == "pnpm"
        assert len(data["members"]) == 2

    def test_clear_session(self, pnpm_workspace):
        """Test clear_session removes state."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        manager.initialize()

        state_file = pnpm_workspace / ".claude-indexer" / "workspace.json"
        assert state_file.exists()

        result = manager.clear_session()

        assert result is True
        assert not state_file.exists()

    def test_clear_session_no_session(self, pnpm_workspace):
        """Test clear_session when no session exists."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        result = manager.clear_session()

        assert result is False

    def test_context_manager(self, pnpm_workspace):
        """Test context manager usage."""
        with WorkspaceManager(workspace_path=pnpm_workspace) as manager:
            context = manager.initialize()
            assert context is not None

        # State should be saved after exit
        state_file = pnpm_workspace / ".claude-indexer" / "workspace.json"
        assert state_file.exists()

    def test_cleanup_saves_state(self, pnpm_workspace):
        """Test cleanup saves state."""
        manager = WorkspaceManager(workspace_path=pnpm_workspace)
        context = manager.initialize()
        old_activity = context.last_activity

        time.sleep(0.01)
        manager.cleanup()

        state_file = pnpm_workspace / ".claude-indexer" / "workspace.json"
        with open(state_file) as f:
            data = json.load(f)

        assert data["last_activity"] > old_activity


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.fixture
    def pnpm_workspace(self, tmp_path):
        """Create a pnpm workspace for testing."""
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n")

        pkg1 = tmp_path / "packages" / "core"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "core"}')

        return tmp_path

    def test_get_workspace_context_in_workspace(self, pnpm_workspace):
        """Test get_workspace_context in workspace."""
        context = get_workspace_context(str(pnpm_workspace))

        assert context is not None
        assert context.workspace_config.workspace_type == WorkspaceType.PNPM

    def test_get_workspace_context_not_in_workspace(self, tmp_path):
        """Test get_workspace_context not in workspace."""
        context = get_workspace_context(str(tmp_path))

        assert context is None

    def test_detect_workspace_pnpm(self, pnpm_workspace):
        """Test detect_workspace for pnpm."""
        config = detect_workspace(str(pnpm_workspace))

        assert config.workspace_type == WorkspaceType.PNPM

    def test_detect_workspace_none(self, tmp_path):
        """Test detect_workspace for non-workspace."""
        config = detect_workspace(str(tmp_path))

        assert config.workspace_type == WorkspaceType.NONE
