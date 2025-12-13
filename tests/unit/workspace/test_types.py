"""Unit tests for workspace types module."""

from pathlib import Path

from claude_indexer.workspace.types import (
    CollectionStrategy,
    WorkspaceConfig,
    WorkspaceMember,
    WorkspaceType,
)


class TestWorkspaceType:
    """Tests for WorkspaceType enum."""

    def test_none_value(self):
        """Test NONE workspace type."""
        assert WorkspaceType.NONE.value == "none"

    def test_vscode_value(self):
        """Test VSCODE_MULTI_ROOT workspace type."""
        assert WorkspaceType.VSCODE_MULTI_ROOT.value == "vscode"

    def test_pnpm_value(self):
        """Test PNPM workspace type."""
        assert WorkspaceType.PNPM.value == "pnpm"

    def test_all_types_have_values(self):
        """Test all workspace types have string values."""
        for ws_type in WorkspaceType:
            assert isinstance(ws_type.value, str)
            assert len(ws_type.value) > 0


class TestCollectionStrategy:
    """Tests for CollectionStrategy enum."""

    def test_single_value(self):
        """Test SINGLE strategy."""
        assert CollectionStrategy.SINGLE.value == "single"

    def test_multiple_value(self):
        """Test MULTIPLE strategy."""
        assert CollectionStrategy.MULTIPLE.value == "multiple"


class TestWorkspaceMember:
    """Tests for WorkspaceMember dataclass."""

    def test_basic_member(self, tmp_path):
        """Test creating a basic workspace member."""
        member = WorkspaceMember(
            name="core",
            path=tmp_path / "packages" / "core",
            relative_path="packages/core",
        )
        assert member.name == "core"
        assert member.relative_path == "packages/core"
        assert member.is_root is False
        assert member.collection_override is None
        assert member.exclude_from_workspace is False

    def test_member_with_override(self, tmp_path):
        """Test creating a member with collection override."""
        member = WorkspaceMember(
            name="special",
            path=tmp_path / "special",
            relative_path="special",
            collection_override="custom_collection",
        )
        assert member.collection_override == "custom_collection"

    def test_member_as_root(self, tmp_path):
        """Test creating a root member."""
        member = WorkspaceMember(
            name="root",
            path=tmp_path,
            relative_path=".",
            is_root=True,
        )
        assert member.is_root is True

    def test_path_string_conversion(self, tmp_path):
        """Test that string paths are converted to Path."""
        path_str = str(tmp_path / "test")
        member = WorkspaceMember(
            name="test",
            path=path_str,  # type: ignore
            relative_path="test",
        )
        assert isinstance(member.path, Path)


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig dataclass."""

    def test_basic_config(self, tmp_path):
        """Test creating a basic workspace config."""
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.PNPM,
            root_path=tmp_path,
        )
        assert config.workspace_type == WorkspaceType.PNPM
        assert config.root_path == tmp_path
        assert config.members == []
        assert config.collection_strategy == CollectionStrategy.SINGLE

    def test_config_with_members(self, tmp_path):
        """Test creating config with members."""
        members = [
            WorkspaceMember(
                name="pkg1",
                path=tmp_path / "pkg1",
                relative_path="pkg1",
            ),
            WorkspaceMember(
                name="pkg2",
                path=tmp_path / "pkg2",
                relative_path="pkg2",
            ),
        ]
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.NPM_WORKSPACES,
            root_path=tmp_path,
            members=members,
        )
        assert len(config.members) == 2

    def test_config_derives_collection_name(self, tmp_path):
        """Test that collection name is derived automatically."""
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.LERNA,
            root_path=tmp_path,
        )
        assert config.collection_name is not None
        assert config.collection_name.startswith("claude_")

    def test_config_none_type_no_collection(self, tmp_path):
        """Test NONE type doesn't derive collection name."""
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.NONE,
            root_path=tmp_path,
        )
        assert config.collection_name is None

    def test_is_monorepo_true(self, tmp_path):
        """Test is_monorepo returns True for monorepo types."""
        for ws_type in [
            WorkspaceType.PNPM,
            WorkspaceType.LERNA,
            WorkspaceType.NX,
            WorkspaceType.NPM_WORKSPACES,
            WorkspaceType.YARN_WORKSPACES,
            WorkspaceType.TURBOREPO,
        ]:
            config = WorkspaceConfig(
                workspace_type=ws_type,
                root_path=tmp_path,
            )
            assert config.is_monorepo() is True, f"Failed for {ws_type}"

    def test_is_monorepo_false(self, tmp_path):
        """Test is_monorepo returns False for non-monorepo types."""
        for ws_type in [WorkspaceType.NONE, WorkspaceType.VSCODE_MULTI_ROOT]:
            config = WorkspaceConfig(
                workspace_type=ws_type,
                root_path=tmp_path,
            )
            assert config.is_monorepo() is False, f"Failed for {ws_type}"

    def test_get_effective_collection_single_strategy(self, tmp_path):
        """Test get_effective_collection with SINGLE strategy."""
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.PNPM,
            root_path=tmp_path,
            collection_strategy=CollectionStrategy.SINGLE,
        )
        collection = config.get_effective_collection()
        assert collection == config.collection_name

    def test_get_effective_collection_multiple_strategy(self, tmp_path):
        """Test get_effective_collection with MULTIPLE strategy."""
        member = WorkspaceMember(
            name="pkg1",
            path=tmp_path / "pkg1",
            relative_path="pkg1",
        )
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.VSCODE_MULTI_ROOT,
            root_path=tmp_path,
            collection_strategy=CollectionStrategy.MULTIPLE,
            members=[member],
        )
        collection = config.get_effective_collection(member)
        assert collection.startswith("claude_pkg1_")

    def test_get_effective_collection_with_override(self, tmp_path):
        """Test get_effective_collection respects member override."""
        member = WorkspaceMember(
            name="pkg1",
            path=tmp_path / "pkg1",
            relative_path="pkg1",
            collection_override="my_custom_collection",
        )
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.VSCODE_MULTI_ROOT,
            root_path=tmp_path,
            collection_strategy=CollectionStrategy.MULTIPLE,
            members=[member],
        )
        collection = config.get_effective_collection(member)
        assert collection == "my_custom_collection"

    def test_to_dict(self, tmp_path):
        """Test serialization to dictionary."""
        member = WorkspaceMember(
            name="pkg1",
            path=tmp_path / "pkg1",
            relative_path="pkg1",
        )
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.PNPM,
            root_path=tmp_path,
            members=[member],
        )
        data = config.to_dict()

        assert data["workspace_type"] == "pnpm"
        assert data["root_path"] == str(tmp_path)
        assert len(data["members"]) == 1
        assert data["members"][0]["name"] == "pkg1"
        assert data["collection_strategy"] == "single"

    def test_path_string_conversion(self, tmp_path):
        """Test that string root_path is converted to Path."""
        config = WorkspaceConfig(
            workspace_type=WorkspaceType.PNPM,
            root_path=str(tmp_path),  # type: ignore
        )
        assert isinstance(config.root_path, Path)
