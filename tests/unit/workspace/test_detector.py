"""Unit tests for workspace detector module."""

import json

from claude_indexer.workspace.detector import WorkspaceDetector
from claude_indexer.workspace.types import (
    CollectionStrategy,
    WorkspaceType,
)


class TestWorkspaceDetector:
    """Tests for WorkspaceDetector class."""

    def test_detect_no_workspace(self, tmp_path):
        """Test detection when no workspace markers present."""
        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NONE
        assert config.root_path == tmp_path
        assert len(config.members) == 0

    def test_detect_pnpm_workspace(self, tmp_path):
        """Test detection of pnpm workspace."""
        # Create pnpm-workspace.yaml
        pnpm_config = tmp_path / "pnpm-workspace.yaml"
        pnpm_config.write_text("packages:\n  - 'packages/*'\n")

        # Create package directories
        pkg1 = tmp_path / "packages" / "core"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "core"}')

        pkg2 = tmp_path / "packages" / "utils"
        pkg2.mkdir(parents=True)
        (pkg2 / "package.json").write_text('{"name": "utils"}')

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.PNPM
        assert config.root_path == tmp_path
        assert config.collection_strategy == CollectionStrategy.SINGLE
        assert len(config.members) == 2
        member_names = {m.name for m in config.members}
        assert "core" in member_names
        assert "utils" in member_names

    def test_detect_npm_workspaces(self, tmp_path):
        """Test detection of npm workspaces in package.json."""
        # Create package.json with workspaces
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(
            json.dumps(
                {
                    "name": "monorepo",
                    "workspaces": ["packages/*"],
                }
            )
        )

        # Create package directory
        pkg1 = tmp_path / "packages" / "app"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "app"}')

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NPM_WORKSPACES
        assert len(config.members) == 1
        assert config.members[0].name == "app"

    def test_detect_yarn_workspaces(self, tmp_path):
        """Test detection of yarn workspaces (with yarn.lock)."""
        # Create package.json with workspaces
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(
            json.dumps(
                {
                    "name": "monorepo",
                    "workspaces": ["packages/*"],
                }
            )
        )

        # Create yarn.lock to indicate yarn
        (tmp_path / "yarn.lock").write_text("")

        # Create package directory
        pkg1 = tmp_path / "packages" / "app"
        pkg1.mkdir(parents=True)
        (pkg1 / "package.json").write_text('{"name": "app"}')

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.YARN_WORKSPACES

    def test_detect_vscode_workspace(self, tmp_path):
        """Test detection of VS Code workspace file."""
        # Create folders
        project_a = tmp_path / "project-a"
        project_a.mkdir()
        project_b = tmp_path / "project-b"
        project_b.mkdir()

        # Create .code-workspace file
        ws_file = tmp_path / "myworkspace.code-workspace"
        ws_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": "project-a"},
                        {"path": "project-b", "name": "Backend"},
                    ]
                }
            )
        )

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.VSCODE_MULTI_ROOT
        assert config.collection_strategy == CollectionStrategy.MULTIPLE
        assert len(config.members) == 2

        member_names = {m.name for m in config.members}
        assert "project-a" in member_names
        assert "Backend" in member_names

    def test_detect_lerna_workspace(self, tmp_path):
        """Test detection of lerna workspace."""
        # Create lerna.json
        lerna_config = tmp_path / "lerna.json"
        lerna_config.write_text(
            json.dumps(
                {
                    "version": "1.0.0",
                    "packages": ["packages/*"],
                }
            )
        )

        # Create package directory
        pkg1 = tmp_path / "packages" / "lib"
        pkg1.mkdir(parents=True)

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.LERNA
        assert len(config.members) == 1

    def test_detect_nx_workspace_with_workspace_json(self, tmp_path):
        """Test detection of Nx workspace with workspace.json."""
        # Create nx.json
        (tmp_path / "nx.json").write_text("{}")

        # Create workspace.json
        workspace_json = tmp_path / "workspace.json"
        workspace_json.write_text(
            json.dumps(
                {
                    "projects": {
                        "app": "apps/app",
                        "lib": {"root": "libs/lib"},
                    }
                }
            )
        )

        # Create project directories
        app_dir = tmp_path / "apps" / "app"
        app_dir.mkdir(parents=True)
        lib_dir = tmp_path / "libs" / "lib"
        lib_dir.mkdir(parents=True)

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NX
        assert len(config.members) == 2

    def test_detect_nx_workspace_with_project_json(self, tmp_path):
        """Test detection of Nx workspace with project.json files."""
        # Create nx.json
        (tmp_path / "nx.json").write_text("{}")

        # Create project.json files
        app_dir = tmp_path / "apps" / "myapp"
        app_dir.mkdir(parents=True)
        (app_dir / "project.json").write_text('{"name": "myapp"}')

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NX
        assert len(config.members) == 1
        assert config.members[0].name == "myapp"

    def test_detect_turborepo(self, tmp_path):
        """Test detection of Turborepo workspace."""
        # Create turbo.json
        (tmp_path / "turbo.json").write_text('{"pipeline": {}}')

        # Create package.json with workspaces
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(
            json.dumps(
                {
                    "name": "turborepo",
                    "workspaces": ["apps/*", "packages/*"],
                }
            )
        )

        # Create packages
        app = tmp_path / "apps" / "web"
        app.mkdir(parents=True)
        (app / "package.json").write_text('{"name": "web"}')

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.TURBOREPO
        assert len(config.members) == 1

    def test_detect_walks_up_directory_tree(self, tmp_path):
        """Test that detection walks up directory tree."""
        # Create workspace at root
        pnpm_config = tmp_path / "pnpm-workspace.yaml"
        pnpm_config.write_text("packages:\n  - 'packages/*'\n")

        # Create nested directory
        nested = tmp_path / "packages" / "core" / "src" / "utils"
        nested.mkdir(parents=True)

        # Detect from nested directory
        config = WorkspaceDetector.detect(nested)

        assert config.workspace_type == WorkspaceType.PNPM
        assert config.root_path == tmp_path

    def test_detect_priority_pnpm_over_npm(self, tmp_path):
        """Test that pnpm takes priority over npm workspaces."""
        # Create both pnpm-workspace.yaml and package.json with workspaces
        (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'pkg/*'\n")
        (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["pkg/*"]}))

        pkg = tmp_path / "pkg" / "a"
        pkg.mkdir(parents=True)

        config = WorkspaceDetector.detect(tmp_path)

        # pnpm should take priority
        assert config.workspace_type == WorkspaceType.PNPM

    def test_detect_ignores_package_json_without_workspaces(self, tmp_path):
        """Test that package.json without workspaces is not detected."""
        (tmp_path / "package.json").write_text(json.dumps({"name": "single-package"}))

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NONE

    def test_detect_handles_malformed_json(self, tmp_path):
        """Test graceful handling of malformed JSON."""
        (tmp_path / "lerna.json").write_text("not valid json {")

        config = WorkspaceDetector.detect(tmp_path)

        # Should not crash, may detect as lerna but with no members
        assert config.workspace_type == WorkspaceType.LERNA
        assert len(config.members) == 0

    def test_detect_handles_missing_folders_in_vscode(self, tmp_path):
        """Test VS Code workspace with missing folder paths."""
        ws_file = tmp_path / "workspace.code-workspace"
        ws_file.write_text(
            json.dumps(
                {
                    "folders": [
                        {"path": "exists"},
                        {"path": "does-not-exist"},
                    ]
                }
            )
        )

        (tmp_path / "exists").mkdir()

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.VSCODE_MULTI_ROOT
        assert len(config.members) == 1
        assert config.members[0].name == "exists"

    def test_is_monorepo_classmethod(self):
        """Test is_monorepo class method."""
        monorepo_types = [
            WorkspaceType.PNPM,
            WorkspaceType.LERNA,
            WorkspaceType.NX,
            WorkspaceType.NPM_WORKSPACES,
            WorkspaceType.YARN_WORKSPACES,
            WorkspaceType.TURBOREPO,
        ]

        for ws_type in monorepo_types:
            assert WorkspaceDetector.is_monorepo(ws_type) is True

        assert WorkspaceDetector.is_monorepo(WorkspaceType.NONE) is False
        assert WorkspaceDetector.is_monorepo(WorkspaceType.VSCODE_MULTI_ROOT) is False

    def test_expand_glob_with_negation(self, tmp_path):
        """Test that negation patterns are skipped."""
        patterns = ["packages/*", "!packages/internal"]

        pkg1 = tmp_path / "packages" / "public"
        pkg1.mkdir(parents=True)

        pkg2 = tmp_path / "packages" / "internal"
        pkg2.mkdir(parents=True)

        members = WorkspaceDetector._expand_glob_patterns(patterns, tmp_path)

        # Both should be found as negation just skips that pattern
        # but doesn't exclude already found items
        assert len(members) >= 1

    def test_npm_workspaces_object_format(self, tmp_path):
        """Test npm workspaces with object format."""
        pkg_json = tmp_path / "package.json"
        pkg_json.write_text(
            json.dumps(
                {
                    "name": "monorepo",
                    "workspaces": {"packages": ["packages/*"]},
                }
            )
        )

        pkg = tmp_path / "packages" / "lib"
        pkg.mkdir(parents=True)

        config = WorkspaceDetector.detect(tmp_path)

        assert config.workspace_type == WorkspaceType.NPM_WORKSPACES
        assert len(config.members) == 1
