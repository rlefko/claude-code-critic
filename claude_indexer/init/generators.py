"""File generators for project initialization."""

import json
from pathlib import Path

from ..config.project_config import ProjectConfigManager
from ..indexer_logging import get_logger
from .templates import TemplateManager
from .types import InitStepResult, ProjectType

logger = get_logger()


class FileGenerator:
    """Generates configuration files for project initialization."""

    # Claude-specific entries to add to .gitignore
    GITIGNORE_ENTRIES = [
        "",
        "# Claude Code Memory",
        ".claude/hooks/",
        ".claude/settings.local.json",
        ".claude/utils/",
        ".mcp.json",
        ".ui-quality/",
        ".claude-indexer/",
    ]

    def __init__(
        self,
        project_path: Path,
        template_manager: TemplateManager,
        project_type: ProjectType,
    ):
        self.project_path = Path(project_path).resolve()
        self.template_manager = template_manager
        self.project_type = project_type

    def generate_claudeignore(self, force: bool = False) -> InitStepResult:
        """Generate .claudeignore from project-type template.

        Resolution order:
        1. Try project-type-specific template (e.g., templates/python/.claudeignore.template)
        2. Try root template (templates/.claudeignore.template)
        3. Fall back to minimal programmatic generation
        """
        target_path = self.project_path / ".claudeignore"

        if target_path.exists() and not force:
            return InitStepResult(
                step_name="claudeignore",
                success=True,
                skipped=True,
                message=".claudeignore already exists",
            )

        # Copy from template (uses project-type resolution)
        success = self.template_manager.copy_template(
            ".claudeignore.template",
            target_path,
            process_variables=True,  # Process variables like {{PROJECT_NAME}}
        )

        if success:
            return InitStepResult(
                step_name="claudeignore",
                success=True,
                message=f"Created {target_path} ({self.project_type.value} template)",
            )
        else:
            # Fallback: create minimal claudeignore
            try:
                minimal_content = self._get_minimal_claudeignore()
                with open(target_path, "w") as f:
                    f.write(minimal_content)
                return InitStepResult(
                    step_name="claudeignore",
                    success=True,
                    message=f"Created {target_path} (minimal template)",
                    warning="Template not found, used minimal defaults",
                )
            except OSError as e:
                return InitStepResult(
                    step_name="claudeignore",
                    success=False,
                    message=f"Failed to create .claudeignore: {e}",
                )

    def _get_minimal_claudeignore(self) -> str:
        """Get minimal claudeignore content as fallback."""
        return """# .claudeignore - Custom Exclusions for Code Indexing

# Secrets and credentials
.env
.env.*
*.pem
*.key
**/credentials.json
**/secrets.json

# Large files
*.h5
*.pkl
*.bin
*.model

# Test artifacts
.coverage
htmlcov/
coverage/
test-results/

# Debug files
debug/
*.dump
*.prof
"""

    def generate_claude_settings(self, force: bool = False) -> InitStepResult:
        """Generate .claude/settings.local.json with hooks configuration."""
        target_dir = self.project_path / ".claude"
        target_path = target_dir / "settings.local.json"

        if target_path.exists() and not force:
            return InitStepResult(
                step_name="claude_settings",
                success=True,
                skipped=True,
                message=".claude/settings.local.json already exists",
            )

        # Try to copy from template
        success = self.template_manager.copy_template(
            "settings.local.json.template",
            target_path,
            process_variables=True,
        )

        if success:
            return InitStepResult(
                step_name="claude_settings",
                success=True,
                message=f"Created {target_path}",
            )
        else:
            # Fallback: create settings directly
            try:
                settings = self._generate_default_settings()
                target_dir.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w") as f:
                    json.dump(settings, f, indent=2)
                return InitStepResult(
                    step_name="claude_settings",
                    success=True,
                    message=f"Created {target_path}",
                    warning="Template not found, used defaults",
                )
            except OSError as e:
                return InitStepResult(
                    step_name="claude_settings",
                    success=False,
                    message=f"Failed to create settings: {e}",
                )

    def _generate_default_settings(self) -> dict:
        """Generate default Claude Code settings."""
        hooks_path = str(self.project_path / ".claude" / "hooks")
        collection = self.template_manager.collection_name

        return {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "Write|Edit",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{hooks_path}/after-write.sh",
                            }
                        ],
                    }
                ],
                "Stop": [
                    {
                        "matcher": ".*",
                        "hooks": [
                            {
                                "type": "command",
                                "command": f"{hooks_path}/end-of-turn-check.sh",
                            }
                        ],
                    }
                ],
            },
            "env": {"CLAUDE_MEMORY_COLLECTION": collection},
        }

    def generate_guard_config(self, force: bool = False) -> InitStepResult:
        """Generate .claude/guard.config.json from project-type template.

        Resolution order:
        1. Try project-type-specific template (e.g., templates/python/guard.config.json.template)
        2. Try root template (templates/guard.config.json.template)
        3. Fall back to programmatic generation
        """
        target_dir = self.project_path / ".claude"
        target_path = target_dir / "guard.config.json"

        if target_path.exists() and not force:
            return InitStepResult(
                step_name="guard_config",
                success=True,
                skipped=True,
                message=".claude/guard.config.json already exists",
            )

        # Try to load from template first (uses project-type resolution)
        content = self.template_manager.load_and_process("guard.config.json.template")

        if content:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                with open(target_path, "w") as f:
                    f.write(content)
                return InitStepResult(
                    step_name="guard_config",
                    success=True,
                    message=f"Created {target_path} ({self.project_type.value} template)",
                )
            except OSError as e:
                logger.warning(
                    f"Failed to write template: {e}, falling back to default"
                )

        # Fallback: generate programmatically
        try:
            config = self._generate_default_guard_config()
            target_dir.mkdir(parents=True, exist_ok=True)
            with open(target_path, "w") as f:
                json.dump(config, f, indent=2)
            return InitStepResult(
                step_name="guard_config",
                success=True,
                message=f"Created {target_path}",
                warning="No template found, used default configuration",
            )
        except OSError as e:
            return InitStepResult(
                step_name="guard_config",
                success=False,
                message=f"Failed to create guard config: {e}",
            )

    def _generate_default_guard_config(self) -> dict:
        """Generate default guard configuration."""
        return {
            "enabled": True,
            "failOnSeverity": "HIGH",
            "continueOnError": True,
            "performance": {
                "fastRuleTimeoutMs": 50.0,
                "totalTimeoutMs": 5000.0,
            },
            "categories": {
                "security": {"enabled": True, "defaultSeverity": "HIGH"},
                "tech_debt": {"enabled": True, "defaultSeverity": "MEDIUM"},
                "resilience": {"enabled": True, "defaultSeverity": "MEDIUM"},
                "documentation": {"enabled": True, "defaultSeverity": "LOW"},
                "git": {"enabled": True, "defaultSeverity": "CRITICAL"},
            },
            "rules": {
                # Disable overly noisy rules by default
                "TECH_DEBT.MAGIC_NUMBERS": {"enabled": False},
                "DOCUMENTATION.MISSING_DOCSTRING": {
                    "enabled": True,
                    "parameters": {"minComplexity": 5},
                },
            },
        }

    def generate_project_config(
        self, collection_name: str, force: bool = False
    ) -> InitStepResult:
        """Generate .claude-indexer/config.json."""
        manager = ProjectConfigManager(self.project_path)

        if manager.exists and not force:
            return InitStepResult(
                step_name="project_config",
                success=True,
                skipped=True,
                message=".claude-indexer/config.json already exists",
            )

        try:
            project_name = self.project_path.name
            config = manager.create_default(project_name, collection_name)
            manager.save(config)
            return InitStepResult(
                step_name="project_config",
                success=True,
                message=f"Created {manager.config_path}",
                details={
                    "include_patterns": config.indexing.file_patterns.include,
                    "exclude_patterns": config.indexing.file_patterns.exclude[:5],
                },
            )
        except Exception as e:
            return InitStepResult(
                step_name="project_config",
                success=False,
                message=f"Failed to create project config: {e}",
            )

    def update_gitignore(self) -> InitStepResult:
        """Add Claude-specific entries to .gitignore."""
        gitignore_path = self.project_path / ".gitignore"

        # Check which entries are already present
        existing_entries: set = set()
        if gitignore_path.exists():
            try:
                with open(gitignore_path) as f:
                    existing_entries = {line.strip() for line in f}
            except OSError:
                pass

        # Find entries to add
        new_entries: list[str] = []
        for entry in self.GITIGNORE_ENTRIES:
            if entry and entry.strip() not in existing_entries:
                if (
                    not entry.startswith("#")
                    or "# Claude Code Memory" not in existing_entries
                ):  # Don't check comments
                    new_entries.append(entry)

        if not new_entries:
            return InitStepResult(
                step_name="gitignore",
                success=True,
                skipped=True,
                message=".gitignore already has Claude entries",
            )

        try:
            with open(gitignore_path, "a") as f:
                f.write("\n".join(self.GITIGNORE_ENTRIES) + "\n")
            return InitStepResult(
                step_name="gitignore",
                success=True,
                message=f"Updated {gitignore_path} with Claude entries",
            )
        except OSError as e:
            return InitStepResult(
                step_name="gitignore",
                success=False,
                message=f"Failed to update .gitignore: {e}",
            )

    def ensure_claude_directory(self) -> InitStepResult:
        """Ensure .claude directory exists."""
        claude_dir = self.project_path / ".claude"
        hooks_dir = claude_dir / "hooks"

        try:
            claude_dir.mkdir(exist_ok=True)
            hooks_dir.mkdir(exist_ok=True)
            return InitStepResult(
                step_name="claude_directory",
                success=True,
                message=f"Created {claude_dir}",
            )
        except OSError as e:
            return InitStepResult(
                step_name="claude_directory",
                success=False,
                message=f"Failed to create .claude directory: {e}",
            )
