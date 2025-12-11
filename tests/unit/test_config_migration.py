"""Unit tests for configuration migration."""

import json
from pathlib import Path

import pytest

from claude_indexer.config.migration import (
    ConfigMigration,
    MigrationAnalysis,
    MigrationResult,
    analyze_migration,
    perform_migration,
)


class TestMigrationAnalysis:
    """Tests for MigrationAnalysis class."""

    def test_analysis_defaults(self):
        """Test MigrationAnalysis default values."""
        analysis = MigrationAnalysis()
        assert analysis.project_path == ""
        assert analysis.existing_configs == []
        assert analysis.migration_needed is False
        assert analysis.actions == []
        assert analysis.warnings == []

    def test_analysis_to_dict(self):
        """Test MigrationAnalysis to_dict method."""
        analysis = MigrationAnalysis()
        analysis.project_path = "/test/path"
        analysis.migration_needed = True
        analysis.actions = ["Action 1"]

        d = analysis.to_dict()

        assert d["project_path"] == "/test/path"
        assert d["migration_needed"] is True
        assert d["actions"] == ["Action 1"]


class TestMigrationResult:
    """Tests for MigrationResult class."""

    def test_successful_result(self):
        """Test successful migration result."""
        result = MigrationResult(
            success=True,
            message="Migration completed",
            changes=["Created config"],
            backup_path="/backup",
        )
        assert result.success is True
        assert result.message == "Migration completed"
        assert len(result.changes) == 1
        assert result.backup_path == "/backup"

    def test_failed_result(self):
        """Test failed migration result."""
        result = MigrationResult(
            success=False,
            message="Migration failed: permission denied",
        )
        assert result.success is False
        assert "failed" in result.message.lower()

    def test_result_to_dict(self):
        """Test MigrationResult to_dict method."""
        result = MigrationResult(
            success=True,
            message="Done",
            changes=["Change 1"],
            backup_path="/backup/path",
            validation_result="Valid",
            sources_used=["source1", "source2"],
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["message"] == "Done"
        assert d["changes"] == ["Change 1"]
        assert d["backup_path"] == "/backup/path"
        assert d["validation_result"] == "Valid"
        assert d["sources_used"] == ["source1", "source2"]


class TestConfigMigrationAnalyze:
    """Tests for ConfigMigration.analyze method."""

    def test_analyze_empty_project(self, tmp_path):
        """Test analysis of project with no config."""
        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        assert str(tmp_path) in analysis.project_path
        assert analysis.migration_needed is False
        # Only project-specific configs trigger migration, global config is preserved
        project_configs = [
            c for c in analysis.existing_configs
            if c["type"] != "global_config"
        ]
        assert len(project_configs) == 0

    def test_analyze_with_settings_txt(self, tmp_path):
        """Test analysis detects settings.txt."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        assert analysis.migration_needed is True
        assert any(c["type"] == "legacy_settings_txt" for c in analysis.existing_configs)
        assert any("settings.txt" in a for a in analysis.actions)

    def test_analyze_with_v26_config(self, tmp_path):
        """Test analysis detects v2.6 config."""
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.6",
            "project": {"name": "test", "collection": "test"},
        }))

        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        assert analysis.migration_needed is True
        assert any(c["version"] == "2.6" for c in analysis.existing_configs)
        assert any("v2.6 to v3.0" in a for a in analysis.actions)

    def test_analyze_with_v30_config(self, tmp_path):
        """Test analysis detects existing v3.0 config."""
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({
            "version": "3.0",
            "project": {"name": "test", "collection": "test"},
        }))

        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        # Should note existing config
        assert any(c["type"] == "unified_config" for c in analysis.existing_configs)
        assert any("already exists" in w.lower() for w in analysis.warnings)

    def test_analyze_with_invalid_json(self, tmp_path):
        """Test analysis handles invalid JSON in config."""
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text("{invalid json}")

        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        assert any("Invalid JSON" in w for w in analysis.warnings)


class TestConfigMigrationMigrate:
    """Tests for ConfigMigration.migrate method."""

    def test_migrate_no_migration_needed(self, tmp_path):
        """Test migration when no migration is needed."""
        migration = ConfigMigration(tmp_path)
        result = migration.migrate()

        assert result.success is True
        assert "no migration needed" in result.message.lower()

    def test_migrate_dry_run(self, tmp_path):
        """Test migration dry run."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(dry_run=True)

        assert result.success is True
        assert "dry run" in result.message.lower()
        assert all(c.startswith("Would:") for c in result.changes)
        # No actual files should be created
        assert not (tmp_path / ".claude" / "settings.json").exists()

    def test_migrate_from_settings_txt(self, tmp_path):
        """Test migration from settings.txt."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("""
openai_api_key=sk-test123
voyage_api_key=va-test456
qdrant_url=https://test.qdrant.com
debounce_seconds=3.0
""")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate()

        assert result.success is True
        assert (tmp_path / ".claude" / "settings.json").exists()

        # Verify content
        with open(tmp_path / ".claude" / "settings.json") as f:
            config = json.load(f)
        assert config["version"] == "3.0"

    def test_migrate_creates_backup(self, tmp_path):
        """Test that migration creates backup."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(backup=True)

        assert result.success is True
        assert result.backup_path is not None
        assert Path(result.backup_path).exists()

    def test_migrate_no_backup(self, tmp_path):
        """Test migration without backup."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(backup=False)

        assert result.success is True
        assert result.backup_path is None

    def test_migrate_existing_config_no_force(self, tmp_path):
        """Test migration fails if config exists without force."""
        # Create existing v3.0 config
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({"version": "3.0"}))

        # Also create something to migrate
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(force=False)

        assert result.success is False
        assert "--force" in result.message

    def test_migrate_existing_config_with_force(self, tmp_path):
        """Test migration overwrites config with force."""
        # Create existing v3.0 config
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        config_file = config_dir / "settings.json"
        config_file.write_text(json.dumps({"version": "3.0"}))

        # Also create something to migrate
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-new-key")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(force=True)

        assert result.success is True

    def test_migrate_updates_gitignore(self, tmp_path):
        """Test migration updates .gitignore."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        result = migration.migrate()

        assert result.success is True
        gitignore_file = tmp_path / ".claude" / ".gitignore"
        assert gitignore_file.exists()
        assert "settings.local.json" in gitignore_file.read_text()


class TestConfigMigrationBackup:
    """Tests for backup and restore functionality."""

    def test_list_backups_empty(self, tmp_path):
        """Test listing backups when none exist."""
        migration = ConfigMigration(tmp_path)
        backups = migration.list_backups()
        assert backups == []

    def test_list_backups_after_migration(self, tmp_path):
        """Test listing backups after migration."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        migration.migrate(backup=True)

        backups = migration.list_backups()
        assert len(backups) >= 1
        assert "timestamp" in backups[0]
        assert "path" in backups[0]

    def test_restore_backup_nonexistent(self, tmp_path):
        """Test restore when no backups exist."""
        migration = ConfigMigration(tmp_path)
        result = migration.restore_backup()

        assert result.success is False
        assert "no backup" in result.message.lower()

    def test_restore_backup_most_recent(self, tmp_path):
        """Test restore from most recent backup."""
        # Create original settings
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-original")

        migration = ConfigMigration(tmp_path)
        migration.migrate(backup=True)

        # Modify the settings file
        settings_file.write_text("openai_api_key=sk-modified")

        # Restore from backup
        result = migration.restore_backup()

        assert result.success is True
        assert "sk-original" in settings_file.read_text()

    def test_restore_specific_backup(self, tmp_path):
        """Test restore from specific backup by timestamp."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        migration.migrate(backup=True)

        backups = migration.list_backups()
        timestamp = backups[0]["timestamp"]

        result = migration.restore_backup(backup_timestamp=timestamp)

        assert result.success is True
        assert timestamp in result.message

    def test_restore_nonexistent_timestamp(self, tmp_path):
        """Test restore with nonexistent timestamp."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        migration = ConfigMigration(tmp_path)
        migration.migrate(backup=True)

        result = migration.restore_backup(backup_timestamp="99991231_235959")

        assert result.success is False
        assert "not found" in result.message


class TestAnalyzeMigrationFunction:
    """Tests for analyze_migration convenience function."""

    def test_analyze_migration(self, tmp_path):
        """Test analyze_migration function."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        result = analyze_migration(str(tmp_path))

        assert isinstance(result, dict)
        assert result["migration_needed"] is True
        assert "actions" in result


class TestPerformMigrationFunction:
    """Tests for perform_migration convenience function."""

    def test_perform_migration(self, tmp_path):
        """Test perform_migration function."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        result = perform_migration(str(tmp_path))

        assert isinstance(result, dict)
        assert result["success"] is True

    def test_perform_migration_dry_run(self, tmp_path):
        """Test perform_migration with dry_run."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        result = perform_migration(str(tmp_path), dry_run=True)

        assert result["success"] is True
        assert "dry run" in result["message"].lower()

    def test_perform_migration_no_backup(self, tmp_path):
        """Test perform_migration without backup."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        result = perform_migration(str(tmp_path), no_backup=True)

        assert result["success"] is True
        assert result["backup_path"] is None


class TestMigrationEdgeCases:
    """Tests for migration edge cases."""

    def test_migrate_with_both_legacy_locations(self, tmp_path):
        """Test migration when both settings.txt and .claude-indexer exist."""
        # Create settings.txt
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-from-txt")

        # Create .claude-indexer/config.json
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({
            "version": "2.6",
            "project": {"name": "from-json", "collection": "test"},
        }))

        migration = ConfigMigration(tmp_path)
        analysis = migration.analyze()

        # Should detect both
        assert analysis.migration_needed is True
        config_types = [c["type"] for c in analysis.existing_configs]
        assert "legacy_settings_txt" in config_types
        assert "project_config" in config_types

    def test_migrate_preserves_existing_gitignore(self, tmp_path):
        """Test migration preserves existing .gitignore content."""
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        # Create .claude with existing .gitignore
        config_dir = tmp_path / ".claude"
        config_dir.mkdir()
        gitignore = config_dir / ".gitignore"
        gitignore.write_text("existing-ignore.txt\n")

        migration = ConfigMigration(tmp_path)
        migration.migrate()

        gitignore_content = gitignore.read_text()
        assert "existing-ignore.txt" in gitignore_content
        assert "settings.local.json" in gitignore_content

    def test_backup_multiple_files(self, tmp_path):
        """Test backup includes all relevant files."""
        # Create settings.txt
        settings_file = tmp_path / "settings.txt"
        settings_file.write_text("openai_api_key=sk-test")

        # Create .claude-indexer
        config_dir = tmp_path / ".claude-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"version": "2.6"}))

        migration = ConfigMigration(tmp_path)
        result = migration.migrate(backup=True)

        backup_path = Path(result.backup_path)
        # Both files should be backed up
        assert (backup_path / "settings.txt").exists()
        assert (backup_path / ".claude-indexer").exists()
