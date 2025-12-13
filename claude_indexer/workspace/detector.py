"""
Workspace detection from directory structure.

This module provides detection of various workspace types by scanning
for marker files and parsing their contents to identify workspace members.
"""

import json
from pathlib import Path
from typing import ClassVar

from ..indexer_logging import get_logger
from .types import CollectionStrategy, WorkspaceConfig, WorkspaceMember, WorkspaceType

logger = get_logger()


class WorkspaceDetector:
    """Detects workspace type and structure from filesystem.

    Scans for workspace markers in priority order and parses their
    contents to identify workspace members and configuration.

    Detection priority (highest to lowest):
    1. .code-workspace file (VS Code multi-root)
    2. pnpm-workspace.yaml (pnpm monorepo)
    3. nx.json (Nx monorepo)
    4. lerna.json (Lerna monorepo)
    5. turbo.json (Turborepo)
    6. package.json with workspaces (npm/yarn workspaces)
    7. No workspace (single project)

    Example:
        detector = WorkspaceDetector()
        config = detector.detect(Path("/path/to/workspace"))
        if config.workspace_type != WorkspaceType.NONE:
            print(f"Found {config.workspace_type.value} workspace")
            for member in config.members:
                print(f"  - {member.name}: {member.path}")
    """

    # Markers in detection priority order
    # Format: (pattern, WorkspaceType)
    WORKSPACE_MARKERS: ClassVar[list[tuple[str, WorkspaceType]]] = [
        ("*.code-workspace", WorkspaceType.VSCODE_MULTI_ROOT),
        ("pnpm-workspace.yaml", WorkspaceType.PNPM),
        ("nx.json", WorkspaceType.NX),
        ("lerna.json", WorkspaceType.LERNA),
        ("turbo.json", WorkspaceType.TURBOREPO),
        ("package.json", WorkspaceType.NPM_WORKSPACES),  # Checked for workspaces field
    ]

    @classmethod
    def detect(cls, start_path: Path | None = None) -> WorkspaceConfig:
        """Detect workspace from path.

        Walks up the directory tree from start_path looking for
        workspace markers, then parses the workspace configuration.

        Args:
            start_path: Starting directory (defaults to CWD)

        Returns:
            WorkspaceConfig with detected type and members
        """
        path = (start_path or Path.cwd()).resolve()

        # Walk up to find workspace root
        workspace_type, workspace_file = cls._find_workspace_marker(path)

        if workspace_type == WorkspaceType.NONE:
            return WorkspaceConfig(
                workspace_type=WorkspaceType.NONE,
                root_path=path,
            )

        workspace_root = workspace_file.parent if workspace_file else path

        # Parse workspace configuration
        members = cls._parse_workspace_members(
            workspace_type, workspace_file, workspace_root
        )

        # Determine collection strategy
        strategy = cls._determine_collection_strategy(workspace_type)

        return WorkspaceConfig(
            workspace_type=workspace_type,
            root_path=workspace_root,
            members=members,
            collection_strategy=strategy,
            workspace_file=workspace_file,
        )

    @classmethod
    def _find_workspace_marker(
        cls, start_path: Path
    ) -> tuple[WorkspaceType, Path | None]:
        """Walk up directory tree to find workspace marker.

        Searches for workspace markers starting from start_path and
        walking up until a marker is found or filesystem root is reached.

        Args:
            start_path: Starting directory

        Returns:
            Tuple of (WorkspaceType, path to marker file or None)
        """
        current = start_path

        while current != current.parent:
            for pattern, ws_type in cls.WORKSPACE_MARKERS:
                if pattern.startswith("*"):
                    # Glob pattern (e.g., *.code-workspace)
                    matches = list(current.glob(pattern))
                    if matches:
                        return ws_type, matches[0]
                else:
                    marker_path = current / pattern
                    if marker_path.exists():
                        # Special case: package.json needs workspaces field
                        if ws_type == WorkspaceType.NPM_WORKSPACES:
                            if cls._has_workspaces_field(marker_path):
                                # Check for yarn.lock to distinguish yarn vs npm
                                if (current / "yarn.lock").exists():
                                    return WorkspaceType.YARN_WORKSPACES, marker_path
                                return ws_type, marker_path
                        else:
                            return ws_type, marker_path
            current = current.parent

        # Check root directory as well
        for pattern, ws_type in cls.WORKSPACE_MARKERS:
            if pattern.startswith("*"):
                matches = list(current.glob(pattern))
                if matches:
                    return ws_type, matches[0]
            else:
                marker_path = current / pattern
                if marker_path.exists():
                    if ws_type == WorkspaceType.NPM_WORKSPACES:
                        if cls._has_workspaces_field(marker_path):
                            if (current / "yarn.lock").exists():
                                return WorkspaceType.YARN_WORKSPACES, marker_path
                            return ws_type, marker_path
                    else:
                        return ws_type, marker_path

        return WorkspaceType.NONE, None

    @classmethod
    def _has_workspaces_field(cls, package_json_path: Path) -> bool:
        """Check if package.json has workspaces field.

        Args:
            package_json_path: Path to package.json

        Returns:
            True if workspaces field exists
        """
        try:
            with open(package_json_path) as f:
                data = json.load(f)
            return "workspaces" in data
        except (json.JSONDecodeError, OSError):
            return False

    @classmethod
    def _parse_workspace_members(
        cls,
        ws_type: WorkspaceType,
        ws_file: Path | None,
        root_path: Path,
    ) -> list[WorkspaceMember]:
        """Parse workspace members based on workspace type.

        Delegates to type-specific parsing methods.

        Args:
            ws_type: Detected workspace type
            ws_file: Path to workspace config file
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        if ws_file is None:
            return []

        if ws_type == WorkspaceType.VSCODE_MULTI_ROOT:
            return cls._parse_vscode_workspace(ws_file)
        elif ws_type == WorkspaceType.PNPM:
            return cls._parse_pnpm_workspace(ws_file, root_path)
        elif ws_type == WorkspaceType.NX:
            return cls._parse_nx_workspace(ws_file, root_path)
        elif ws_type == WorkspaceType.LERNA:
            return cls._parse_lerna_workspace(ws_file, root_path)
        elif ws_type == WorkspaceType.TURBOREPO:
            return cls._parse_turbo_workspace(ws_file, root_path)
        elif ws_type in (WorkspaceType.NPM_WORKSPACES, WorkspaceType.YARN_WORKSPACES):
            return cls._parse_npm_workspaces(ws_file, root_path)

        return []

    @classmethod
    def _parse_vscode_workspace(cls, ws_file: Path) -> list[WorkspaceMember]:
        """Parse VS Code .code-workspace file.

        Args:
            ws_file: Path to .code-workspace file

        Returns:
            List of WorkspaceMember objects
        """
        try:
            with open(ws_file) as f:
                data = json.load(f)

            members = []
            for folder in data.get("folders", []):
                folder_path = folder.get("path", "")
                name = folder.get("name") or Path(folder_path).name

                # Resolve path relative to workspace file
                if folder_path.startswith("/"):
                    resolved_path = Path(folder_path)
                else:
                    resolved_path = (ws_file.parent / folder_path).resolve()

                if resolved_path.exists() and resolved_path.is_dir():
                    members.append(
                        WorkspaceMember(
                            name=name,
                            path=resolved_path,
                            relative_path=folder_path,
                        )
                    )

            return members
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.debug(f"Error parsing VS Code workspace: {e}")
            return []

    @classmethod
    def _parse_pnpm_workspace(
        cls, ws_file: Path, root_path: Path
    ) -> list[WorkspaceMember]:
        """Parse pnpm-workspace.yaml.

        Args:
            ws_file: Path to pnpm-workspace.yaml
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        try:
            # Try to import yaml, fall back to basic parsing if not available
            try:
                import yaml

                with open(ws_file) as f:
                    data = yaml.safe_load(f)
                packages = data.get("packages", []) if data else []
            except ImportError:
                # Basic YAML parsing for simple pnpm-workspace.yaml
                packages = cls._parse_simple_yaml_list(ws_file, "packages")

            return cls._expand_glob_patterns(packages, root_path)
        except OSError as e:
            logger.debug(f"Error parsing pnpm workspace: {e}")
            return []

    @classmethod
    def _parse_simple_yaml_list(cls, file_path: Path, key: str) -> list[str]:
        """Basic YAML list parsing for simple cases.

        Handles basic pnpm-workspace.yaml format:
        packages:
          - 'packages/*'
          - 'apps/*'

        Args:
            file_path: Path to YAML file
            key: Key to look for

        Returns:
            List of string values
        """
        try:
            with open(file_path) as f:
                lines = f.readlines()

            result = []
            in_key = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(f"{key}:"):
                    in_key = True
                    continue
                if in_key:
                    if stripped.startswith("-"):
                        # Extract value, removing quotes
                        value = stripped[1:].strip().strip("'\"")
                        if value:
                            result.append(value)
                    elif stripped and not stripped.startswith("#"):
                        # New key started, stop parsing
                        break

            return result
        except OSError:
            return []

    @classmethod
    def _parse_npm_workspaces(
        cls, package_json: Path, root_path: Path
    ) -> list[WorkspaceMember]:
        """Parse package.json workspaces field.

        Handles both array format and object format with packages key.

        Args:
            package_json: Path to package.json
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        try:
            with open(package_json) as f:
                data = json.load(f)

            workspaces = data.get("workspaces", [])
            # Handle both array and object format
            if isinstance(workspaces, dict):
                workspaces = workspaces.get("packages", [])

            return cls._expand_glob_patterns(workspaces, root_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Error parsing npm workspaces: {e}")
            return []

    @classmethod
    def _expand_glob_patterns(
        cls, patterns: list[str], root_path: Path
    ) -> list[WorkspaceMember]:
        """Expand glob patterns to actual directories.

        Handles patterns like 'packages/*', 'apps/**', etc.

        Args:
            patterns: List of glob patterns
            root_path: Root directory for pattern matching

        Returns:
            List of WorkspaceMember objects
        """
        members = []
        seen_paths = set()

        for pattern in patterns:
            # Handle negation patterns (skip excluded)
            if pattern.startswith("!"):
                continue

            # Strip quotes if present
            pattern = pattern.strip("'\"")

            # Determine the glob pattern to use
            # patterns like 'packages/*' should match packages/core, packages/utils
            # patterns like 'packages' should match the packages directory itself
            if "*" in pattern:
                # Pattern has wildcards - use it directly
                glob_pattern = pattern
            else:
                # No wildcards - just a directory path
                glob_pattern = pattern

            # Expand glob
            for path in root_path.glob(glob_pattern):
                if path.is_dir() and path not in seen_paths:
                    # Check if it's a valid package (has package.json or is just a dir)
                    seen_paths.add(path)
                    try:
                        rel_path = str(path.relative_to(root_path))
                    except ValueError:
                        rel_path = str(path)

                    # Get member name from package.json if available, else use dir name
                    member_name = cls._get_package_name(path) or path.name

                    members.append(
                        WorkspaceMember(
                            name=member_name,
                            path=path,
                            relative_path=rel_path,
                        )
                    )

        return members

    @classmethod
    def _get_package_name(cls, path: Path) -> str | None:
        """Get package name from package.json if it exists.

        Args:
            path: Path to package directory

        Returns:
            Package name from package.json or None
        """
        package_json = path / "package.json"
        if package_json.exists():
            try:
                with open(package_json) as f:
                    data = json.load(f)
                return data.get("name")
            except (json.JSONDecodeError, OSError):
                pass
        return None

    @classmethod
    def _parse_nx_workspace(
        cls, ws_file: Path, root_path: Path
    ) -> list[WorkspaceMember]:
        """Parse nx.json and scan for projects.

        Nx projects can be defined in workspace.json or detected via project.json files.

        Args:
            ws_file: Path to nx.json
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        members = []

        # Check for workspace.json (older Nx format)
        workspace_json = root_path / "workspace.json"
        if workspace_json.exists():
            try:
                with open(workspace_json) as f:
                    data = json.load(f)
                projects = data.get("projects", {})
                for name, project_info in projects.items():
                    if isinstance(project_info, str):
                        resolved = root_path / project_info
                    else:
                        resolved = root_path / project_info.get("root", name)
                    if resolved.exists() and resolved.is_dir():
                        try:
                            rel_path = str(resolved.relative_to(root_path))
                        except ValueError:
                            rel_path = str(resolved)
                        members.append(
                            WorkspaceMember(
                                name=name,
                                path=resolved,
                                relative_path=rel_path,
                            )
                        )
            except (json.JSONDecodeError, OSError):
                pass

        # Fallback: scan for project.json files (modern Nx format)
        if not members:
            for project_json in root_path.rglob("project.json"):
                # Skip node_modules
                if "node_modules" in str(project_json):
                    continue
                project_dir = project_json.parent
                try:
                    rel_path = str(project_dir.relative_to(root_path))
                except ValueError:
                    rel_path = str(project_dir)
                members.append(
                    WorkspaceMember(
                        name=project_dir.name,
                        path=project_dir,
                        relative_path=rel_path,
                    )
                )

        return members

    @classmethod
    def _parse_lerna_workspace(
        cls, ws_file: Path, root_path: Path
    ) -> list[WorkspaceMember]:
        """Parse lerna.json.

        Args:
            ws_file: Path to lerna.json
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        try:
            with open(ws_file) as f:
                data = json.load(f)

            packages = data.get("packages", ["packages/*"])
            return cls._expand_glob_patterns(packages, root_path)
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Error parsing Lerna workspace: {e}")
            return []

    @classmethod
    def _parse_turbo_workspace(
        cls, ws_file: Path, root_path: Path
    ) -> list[WorkspaceMember]:
        """Parse turbo.json (uses package.json workspaces).

        Turborepo relies on package.json workspaces for package discovery.

        Args:
            ws_file: Path to turbo.json
            root_path: Workspace root directory

        Returns:
            List of WorkspaceMember objects
        """
        # Turborepo uses package.json workspaces
        package_json = root_path / "package.json"
        if package_json.exists():
            return cls._parse_npm_workspaces(package_json, root_path)
        return []

    @classmethod
    def _determine_collection_strategy(
        cls, ws_type: WorkspaceType
    ) -> CollectionStrategy:
        """Determine collection strategy based on workspace type.

        VS Code multi-root gets MULTIPLE (isolated collections).
        Monorepos get SINGLE (unified collection).

        Args:
            ws_type: Detected workspace type

        Returns:
            CollectionStrategy enum value
        """
        if ws_type == WorkspaceType.VSCODE_MULTI_ROOT:
            return CollectionStrategy.MULTIPLE
        elif ws_type != WorkspaceType.NONE:
            return CollectionStrategy.SINGLE
        return CollectionStrategy.SINGLE

    @classmethod
    def is_monorepo(cls, ws_type: WorkspaceType) -> bool:
        """Check if workspace type is a monorepo.

        Args:
            ws_type: Workspace type to check

        Returns:
            True if workspace type is a monorepo variant
        """
        return ws_type in (
            WorkspaceType.PNPM,
            WorkspaceType.LERNA,
            WorkspaceType.NX,
            WorkspaceType.NPM_WORKSPACES,
            WorkspaceType.YARN_WORKSPACES,
            WorkspaceType.TURBOREPO,
        )
