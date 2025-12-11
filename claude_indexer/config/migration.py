"""Configuration migration tool for existing setups.

This module provides tools to migrate existing configuration files
to the new unified format, with backup and rollback capabilities.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..indexer_logging import get_logger
from .hierarchical_loader import ConfigPaths, HierarchicalConfigLoader
from .validation import validate_config_file

logger = get_logger()


class MigrationAnalysis:
    """Analysis of existing configuration for migration."""

    def __init__(self) -> None:
        self.project_path: str = ""
        self.existing_configs: list[dict[str, Any]] = []
        self.migration_needed: bool = False
        self.actions: list[str] = []
        self.warnings: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "project_path": self.project_path,
            "existing_configs": self.existing_configs,
            "migration_needed": self.migration_needed,
            "actions": self.actions,
            "warnings": self.warnings,
        }


class MigrationResult:
    """Result of a migration operation."""

    def __init__(
        self,
        success: bool,
        message: str,
        changes: Optional[list[str]] = None,
        backup_path: Optional[str] = None,
        validation_result: Optional[str] = None,
        sources_used: Optional[list[str]] = None,
    ) -> None:
        self.success = success
        self.message = message
        self.changes = changes or []
        self.backup_path = backup_path
        self.validation_result = validation_result
        self.sources_used = sources_used or []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "success": self.success,
            "message": self.message,
            "changes": self.changes,
            "backup_path": self.backup_path,
            "validation_result": self.validation_result,
            "sources_used": self.sources_used,
        }


class ConfigMigration:
    """Migrates existing configuration to new unified format."""

    def __init__(self, project_path: Path):
        """Initialize migration for a project.

        Args:
            project_path: Path to the project root.
        """
        self.project_path = Path(project_path).resolve()
        self.backup_dir = self.project_path / ".claude-indexer-backup"

    def analyze(self) -> MigrationAnalysis:
        """Analyze existing configuration without making changes.

        Returns:
            MigrationAnalysis with details of what would be migrated.
        """
        analysis = MigrationAnalysis()
        analysis.project_path = str(self.project_path)

        # Check for legacy settings.txt
        settings_txt = self.project_path / "settings.txt"
        if settings_txt.exists():
            analysis.existing_configs.append(
                {
                    "file": str(settings_txt),
                    "type": "legacy_settings_txt",
                    "status": "will_be_imported",
                }
            )
            analysis.migration_needed = True
            analysis.actions.append(f"Import settings from {settings_txt}")

        # Check for .claude-indexer/config.json (legacy location)
        legacy_config = (
            self.project_path
            / ConfigPaths.LEGACY_PROJECT_DIR
            / ConfigPaths.LEGACY_PROJECT_CONFIG
        )
        if legacy_config.exists():
            try:
                with open(legacy_config) as f:
                    data = json.load(f)
                version = data.get("version", "unknown")
                status = "will_be_migrated" if version < "3.0" else "already_current"
                analysis.existing_configs.append(
                    {
                        "file": str(legacy_config),
                        "type": "project_config",
                        "version": version,
                        "status": status,
                    }
                )
                if version < "3.0":
                    analysis.migration_needed = True
                    analysis.actions.append(
                        f"Migrate {legacy_config} from v{version} to v3.0"
                    )
            except json.JSONDecodeError as e:
                analysis.warnings.append(f"Invalid JSON in {legacy_config}: {e}")
            except Exception as e:
                analysis.warnings.append(f"Could not read {legacy_config}: {e}")

        # Check for global config
        if ConfigPaths.GLOBAL_CONFIG.exists():
            analysis.existing_configs.append(
                {
                    "file": str(ConfigPaths.GLOBAL_CONFIG),
                    "type": "global_config",
                    "status": "will_be_preserved",
                }
            )

        # Check if new .claude directory already exists
        new_dir = self.project_path / ConfigPaths.PROJECT_DIR
        new_config = new_dir / ConfigPaths.PROJECT_SETTINGS
        if new_config.exists():
            try:
                with open(new_config) as f:
                    data = json.load(f)
                version = data.get("version", "unknown")
                analysis.existing_configs.append(
                    {
                        "file": str(new_config),
                        "type": "unified_config",
                        "version": version,
                        "status": "exists",
                    }
                )
                if version >= "3.0":
                    analysis.warnings.append(
                        "New format config already exists - migration may overwrite"
                    )
            except Exception:
                pass
        else:
            analysis.actions.append(f"Create new config directory: {new_dir}")

        return analysis

    def migrate(
        self, dry_run: bool = False, backup: bool = True, force: bool = False
    ) -> MigrationResult:
        """Perform migration to new configuration format.

        Args:
            dry_run: If True, only report what would be done.
            backup: If True, backup existing configs before migration.
            force: If True, overwrite existing new format config.

        Returns:
            MigrationResult with details of what was done.
        """
        analysis = self.analyze()

        if not analysis.migration_needed and not force:
            return MigrationResult(
                success=True,
                message="No migration needed - configuration is already current",
            )

        # Check for existing new config
        new_dir = self.project_path / ConfigPaths.PROJECT_DIR
        new_config_path = new_dir / ConfigPaths.PROJECT_SETTINGS
        if new_config_path.exists() and not force and not dry_run:
            return MigrationResult(
                success=False,
                message=f"Config already exists at {new_config_path}. Use --force to overwrite.",
            )

        if dry_run:
            return MigrationResult(
                success=True,
                message="Dry run - no changes made",
                changes=[f"Would: {action}" for action in analysis.actions],
            )

        changes: list[str] = []
        backup_path: Optional[str] = None

        # Create backup
        if backup:
            try:
                backup_path = str(self._create_backup())
                changes.append(f"Created backup at {backup_path}")
            except Exception as e:
                return MigrationResult(
                    success=False,
                    message=f"Failed to create backup: {e}",
                )

        # Load existing configuration using hierarchical loader
        try:
            loader = HierarchicalConfigLoader(self.project_path)
            unified_config = loader.load()
        except Exception as e:
            return MigrationResult(
                success=False,
                message=f"Failed to load configuration: {e}",
                backup_path=backup_path,
            )

        # Create new directory structure
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            changes.append(f"Created directory: {new_dir}")
        except Exception as e:
            return MigrationResult(
                success=False,
                message=f"Failed to create directory {new_dir}: {e}",
                backup_path=backup_path,
            )

        # Write new settings.json
        try:
            config_dict = unified_config.to_dict(exclude_defaults=False)
            config_dict["version"] = "3.0"
            config_dict["$schema"] = (
                "https://claude-code-memory.dev/schemas/unified-config.schema.json"
            )

            with open(new_config_path, "w") as f:
                json.dump(config_dict, f, indent=2, default=str)
            changes.append(f"Created: {new_config_path}")
        except Exception as e:
            return MigrationResult(
                success=False,
                message=f"Failed to write config: {e}",
                backup_path=backup_path,
                changes=changes,
            )

        # Update .gitignore
        try:
            self._update_gitignore(new_dir)
            changes.append("Updated .gitignore for local config")
        except Exception as e:
            changes.append(f"Warning: Could not update .gitignore: {e}")

        # Validate new config
        validation = validate_config_file(new_config_path)
        if not validation.valid:
            logger.warning(f"Migration completed but validation found issues:\n{validation}")

        return MigrationResult(
            success=True,
            message="Migration completed successfully",
            changes=changes,
            backup_path=backup_path,
            validation_result=str(validation),
            sources_used=loader.get_loaded_sources(),
        )

    def _create_backup(self) -> Path:
        """Create backup of existing configuration files.

        Returns:
            Path to the backup directory.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        files_to_backup = [
            self.project_path / "settings.txt",
            self.project_path
            / ConfigPaths.LEGACY_PROJECT_DIR
            / ConfigPaths.LEGACY_PROJECT_CONFIG,
            self.project_path / ConfigPaths.PROJECT_DIR / ConfigPaths.PROJECT_SETTINGS,
        ]

        for file_path in files_to_backup:
            if file_path.exists():
                dest = backup_path / file_path.name
                shutil.copy2(file_path, dest)
                logger.info(f"Backed up {file_path} to {dest}")

        # Also backup entire .claude-indexer directory if it exists
        legacy_dir = self.project_path / ConfigPaths.LEGACY_PROJECT_DIR
        if legacy_dir.exists():
            dest_dir = backup_path / ConfigPaths.LEGACY_PROJECT_DIR
            shutil.copytree(legacy_dir, dest_dir, dirs_exist_ok=True)
            logger.info(f"Backed up {legacy_dir} to {dest_dir}")

        return backup_path

    def _update_gitignore(self, config_dir: Path) -> None:
        """Ensure local config is gitignored.

        Args:
            config_dir: Path to the .claude config directory.
        """
        gitignore_entries = [
            "# Local configuration (git-ignored)",
            "settings.local.json",
            "",
        ]

        gitignore_path = config_dir / ".gitignore"

        existing_content = ""
        if gitignore_path.exists():
            existing_content = gitignore_path.read_text()

        # Only add if not already present
        if "settings.local.json" not in existing_content:
            with open(gitignore_path, "a") as f:
                if existing_content and not existing_content.endswith("\n"):
                    f.write("\n")
                f.write("\n".join(gitignore_entries))

    def restore_backup(self, backup_timestamp: Optional[str] = None) -> MigrationResult:
        """Restore configuration from backup.

        Args:
            backup_timestamp: Specific backup to restore (format: YYYYMMDD_HHMMSS).
                            If None, uses the most recent backup.

        Returns:
            MigrationResult with details of the restore operation.
        """
        if not self.backup_dir.exists():
            return MigrationResult(
                success=False,
                message="No backups found",
            )

        # Find backup to restore
        backups = sorted(self.backup_dir.iterdir(), reverse=True)
        if not backups:
            return MigrationResult(
                success=False,
                message="No backups found",
            )

        backup_path: Optional[Path] = None
        if backup_timestamp:
            for b in backups:
                if b.name == backup_timestamp:
                    backup_path = b
                    break
            if not backup_path:
                return MigrationResult(
                    success=False,
                    message=f"Backup {backup_timestamp} not found",
                )
        else:
            backup_path = backups[0]

        changes: list[str] = []

        # Restore files from backup
        try:
            for item in backup_path.iterdir():
                if item.is_file():
                    dest = self.project_path / item.name
                    shutil.copy2(item, dest)
                    changes.append(f"Restored {item.name} to {dest}")
                elif item.is_dir() and item.name == ConfigPaths.LEGACY_PROJECT_DIR:
                    dest = self.project_path / ConfigPaths.LEGACY_PROJECT_DIR
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                    changes.append(f"Restored {item.name}/ directory")
        except Exception as e:
            return MigrationResult(
                success=False,
                message=f"Failed to restore from backup: {e}",
                changes=changes,
            )

        return MigrationResult(
            success=True,
            message=f"Restored from backup {backup_path.name}",
            changes=changes,
            backup_path=str(backup_path),
        )

    def list_backups(self) -> list[dict[str, Any]]:
        """List available backups.

        Returns:
            List of backup information dictionaries.
        """
        if not self.backup_dir.exists():
            return []

        backups = []
        for backup in sorted(self.backup_dir.iterdir(), reverse=True):
            if backup.is_dir():
                files = [f.name for f in backup.iterdir()]
                try:
                    # Parse timestamp
                    dt = datetime.strptime(backup.name, "%Y%m%d_%H%M%S")
                    formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted = backup.name

                backups.append(
                    {
                        "timestamp": backup.name,
                        "formatted": formatted,
                        "path": str(backup),
                        "files": files,
                    }
                )

        return backups


def analyze_migration(project_path: str) -> dict[str, Any]:
    """Analyze a project for migration needs.

    Args:
        project_path: Path to the project.

    Returns:
        Analysis results dictionary.
    """
    migration = ConfigMigration(Path(project_path))
    analysis = migration.analyze()
    return analysis.to_dict()


def perform_migration(
    project_path: str, dry_run: bool = False, no_backup: bool = False, force: bool = False
) -> dict[str, Any]:
    """Perform configuration migration.

    Args:
        project_path: Path to the project.
        dry_run: If True, only report what would be done.
        no_backup: If True, skip backup creation.
        force: If True, overwrite existing config.

    Returns:
        Migration results dictionary.
    """
    migration = ConfigMigration(Path(project_path))
    result = migration.migrate(dry_run=dry_run, backup=not no_backup, force=force)
    return result.to_dict()
