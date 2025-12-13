"""Unit tests for workspace context module."""

import time

import pytest

from claude_indexer.workspace.context import WorkspaceContext
from claude_indexer.workspace.types import (
    CollectionStrategy,
    WorkspaceConfig,
    WorkspaceMember,
    WorkspaceType,
)


class TestWorkspaceContext:
    """Tests for WorkspaceContext dataclass."""

    @pytest.fixture
    def sample_members(self, tmp_path):
        """Create sample workspace members."""
        pkg1 = tmp_path / "packages" / "core"
        pkg1.mkdir(parents=True)
        pkg2 = tmp_path / "packages" / "utils"
        pkg2.mkdir(parents=True)

        return [
            WorkspaceMember(
                name="core",
                path=pkg1,
                relative_path="packages/core",
            ),
            WorkspaceMember(
                name="utils",
                path=pkg2,
                relative_path="packages/utils",
            ),
        ]

    @pytest.fixture
    def monorepo_config(self, tmp_path, sample_members):
        """Create a monorepo workspace config."""
        return WorkspaceConfig(
            workspace_type=WorkspaceType.PNPM,
            root_path=tmp_path,
            members=sample_members,
            collection_strategy=CollectionStrategy.SINGLE,
        )

    @pytest.fixture
    def multi_root_config(self, tmp_path, sample_members):
        """Create a multi-root workspace config."""
        return WorkspaceConfig(
            workspace_type=WorkspaceType.VSCODE_MULTI_ROOT,
            root_path=tmp_path,
            members=sample_members,
            collection_strategy=CollectionStrategy.MULTIPLE,
        )

    def test_basic_context_creation(self, monorepo_config):
        """Test creating a basic workspace context."""
        context = WorkspaceContext(
            workspace_id="ws_test_123_abc",
            workspace_config=monorepo_config,
        )

        assert context.workspace_id == "ws_test_123_abc"
        assert context.workspace_config == monorepo_config
        assert context.active_member is None
        assert context.created_at > 0
        assert context.last_activity > 0

    def test_member_collections_auto_populated(self, multi_root_config):
        """Test that member_collections is auto-populated."""
        context = WorkspaceContext(
            workspace_id="ws_test_123_abc",
            workspace_config=multi_root_config,
        )

        assert len(context.member_collections) == 2
        assert "core" in context.member_collections
        assert "utils" in context.member_collections

    def test_is_monorepo_true(self, monorepo_config):
        """Test is_monorepo property for monorepo."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        assert context.is_monorepo is True

    def test_is_monorepo_false(self, multi_root_config):
        """Test is_monorepo property for multi-root."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=multi_root_config,
        )

        assert context.is_monorepo is False

    def test_is_multi_root_true(self, multi_root_config):
        """Test is_multi_root property for multi-root."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=multi_root_config,
        )

        assert context.is_multi_root is True

    def test_is_multi_root_false(self, monorepo_config):
        """Test is_multi_root property for monorepo."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        assert context.is_multi_root is False

    def test_root_path(self, monorepo_config, tmp_path):
        """Test root_path property."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        assert context.root_path == tmp_path

    def test_state_dir(self, monorepo_config, tmp_path):
        """Test state_dir property."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        assert context.state_dir == tmp_path / ".claude-indexer"

    def test_members_property(self, monorepo_config, sample_members):
        """Test members property."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        assert len(context.members) == 2

    def test_collection_names_single_strategy(self, monorepo_config):
        """Test collection_names for single strategy."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        names = context.collection_names
        assert len(names) == 1
        assert names[0] == monorepo_config.collection_name

    def test_collection_names_multiple_strategy(self, multi_root_config):
        """Test collection_names for multiple strategy."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=multi_root_config,
        )

        names = context.collection_names
        assert len(names) == 2

    def test_get_collection_for_path_monorepo(self, monorepo_config, tmp_path):
        """Test get_collection_for_path for monorepo."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        file_path = tmp_path / "packages" / "core" / "index.ts"
        collection = context.get_collection_for_path(file_path)

        # Monorepo always returns single collection
        assert collection == monorepo_config.collection_name

    def test_get_collection_for_path_multi_root(self, multi_root_config, tmp_path):
        """Test get_collection_for_path for multi-root."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=multi_root_config,
        )

        file_path = tmp_path / "packages" / "core" / "index.ts"
        collection = context.get_collection_for_path(file_path)

        assert collection == context.member_collections["core"]

    def test_get_member_for_path_found(self, monorepo_config, tmp_path):
        """Test get_member_for_path when member is found."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        file_path = tmp_path / "packages" / "core" / "src" / "index.ts"
        member = context.get_member_for_path(file_path)

        assert member is not None
        assert member.name == "core"

    def test_get_member_for_path_not_found(self, monorepo_config, tmp_path):
        """Test get_member_for_path when no member matches."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        file_path = tmp_path / "other" / "file.ts"
        member = context.get_member_for_path(file_path)

        assert member is None

    def test_set_active_member_success(self, monorepo_config):
        """Test setting active member by name."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        result = context.set_active_member("core")

        assert result is True
        assert context.active_member is not None
        assert context.active_member.name == "core"

    def test_set_active_member_not_found(self, monorepo_config):
        """Test setting active member that doesn't exist."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        result = context.set_active_member("nonexistent")

        assert result is False
        assert context.active_member is None

    def test_touch_updates_last_activity(self, monorepo_config):
        """Test that touch updates last_activity."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        old_activity = context.last_activity
        time.sleep(0.01)
        context.touch()

        assert context.last_activity > old_activity

    def test_age_seconds(self, monorepo_config):
        """Test age_seconds calculation."""
        context = WorkspaceContext(
            workspace_id="ws_test",
            workspace_config=monorepo_config,
        )

        time.sleep(0.01)
        age = context.age_seconds()

        assert age >= 0.01

    def test_to_dict(self, monorepo_config, tmp_path):
        """Test serialization to dictionary."""
        context = WorkspaceContext(
            workspace_id="ws_test_123",
            workspace_config=monorepo_config,
        )

        data = context.to_dict()

        assert data["workspace_id"] == "ws_test_123"
        assert data["workspace_type"] == "pnpm"
        assert data["root_path"] == str(tmp_path)
        assert data["collection_strategy"] == "single"
        assert len(data["members"]) == 2
        assert "member_collections" in data
        assert "created_at" in data
        assert "last_activity" in data

    def test_from_dict(self, monorepo_config, tmp_path):
        """Test deserialization from dictionary."""
        original = WorkspaceContext(
            workspace_id="ws_test_123",
            workspace_config=monorepo_config,
        )
        original.set_active_member("core")

        data = original.to_dict()
        restored = WorkspaceContext.from_dict(data, monorepo_config)

        assert restored.workspace_id == original.workspace_id
        assert restored.member_collections == original.member_collections
        assert restored.active_member is not None
        assert restored.active_member.name == "core"

    def test_from_dict_without_active_member(self, monorepo_config):
        """Test deserialization without active member."""
        data = {
            "workspace_id": "ws_test",
            "member_collections": {},
            "created_at": time.time(),
            "last_activity": time.time(),
        }

        context = WorkspaceContext.from_dict(data, monorepo_config)

        assert context.active_member is None
