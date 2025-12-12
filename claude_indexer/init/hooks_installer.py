"""Hooks installation for project initialization."""

import os
import shutil
import stat
from pathlib import Path
from typing import List

from ..git_hooks import GitHooksManager
from ..indexer_logging import get_logger
from .types import InitStepResult

logger = get_logger()


class HooksInstaller:
    """Installs Claude Code hooks and git hooks."""

    # Source directory for hook scripts (relative to this file)
    HOOKS_SOURCE_DIR = Path(__file__).parent.parent.parent / "hooks"

    # Hook files to copy to .claude/hooks/
    CLAUDE_HOOK_FILES = [
        "after-write.sh",
        "end-of-turn-check.sh",
        "post-file-change.sh",
        "pre-tool-guard.sh",
        "pre-commit-guard.sh",
        "ui-pre-tool-guard.sh",
        "session_start.py",
        "prompt_handler.py",
    ]

    def __init__(self, project_path: Path, collection_name: str):
        self.project_path = Path(project_path).resolve()
        self.collection_name = collection_name
        self.hooks_dest = self.project_path / ".claude" / "hooks"

    def install_claude_hooks(self, force: bool = False) -> InitStepResult:
        """Copy hook scripts to .claude/hooks/ directory.

        Args:
            force: If True, overwrite existing hooks.

        Returns:
            InitStepResult indicating success or failure.
        """
        # Check if hooks source exists
        if not self.HOOKS_SOURCE_DIR.exists():
            return InitStepResult(
                step_name="claude_hooks",
                success=True,
                skipped=True,
                warning=f"Hooks source directory not found: {self.HOOKS_SOURCE_DIR}",
                message="Skipped Claude hooks installation (source not found)",
            )

        # Create destination directory
        try:
            self.hooks_dest.mkdir(parents=True, exist_ok=True)
        except IOError as e:
            return InitStepResult(
                step_name="claude_hooks",
                success=False,
                message=f"Failed to create hooks directory: {e}",
            )

        installed: List[str] = []
        skipped: List[str] = []
        failed: List[str] = []

        for hook_file in self.CLAUDE_HOOK_FILES:
            source = self.HOOKS_SOURCE_DIR / hook_file
            dest = self.hooks_dest / hook_file

            if not source.exists():
                # Hook file doesn't exist in source, skip silently
                continue

            if dest.exists() and not force:
                skipped.append(hook_file)
                continue

            try:
                shutil.copy2(source, dest)
                # Make executable if it's a shell script
                if hook_file.endswith(".sh"):
                    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
                installed.append(hook_file)
            except IOError as e:
                logger.error(f"Failed to copy hook {hook_file}: {e}")
                failed.append(hook_file)

        # Build result message
        message_parts = []
        if installed:
            message_parts.append(f"Installed {len(installed)} hooks")
        if skipped:
            message_parts.append(f"skipped {len(skipped)} existing")
        if failed:
            message_parts.append(f"failed {len(failed)}")

        message = ", ".join(message_parts) if message_parts else "No hooks to install"

        return InitStepResult(
            step_name="claude_hooks",
            success=len(failed) == 0,
            message=message,
            skipped=len(installed) == 0 and len(failed) == 0,
            details={
                "installed": installed,
                "skipped": skipped,
                "failed": failed,
            },
        )

    def install_git_hooks(self, force: bool = False) -> InitStepResult:
        """Install git pre-commit hook using GitHooksManager.

        Args:
            force: If True, overwrite existing git hooks.

        Returns:
            InitStepResult indicating success or failure.
        """
        manager = GitHooksManager(str(self.project_path), self.collection_name)

        if not manager.is_git_repository():
            return InitStepResult(
                step_name="git_hooks",
                success=True,
                skipped=True,
                message="Not a git repository, skipping git hooks",
            )

        # Check if already installed
        if manager.is_hook_installed() and not force:
            return InitStepResult(
                step_name="git_hooks",
                success=True,
                skipped=True,
                message="Git pre-commit hook already installed",
            )

        # Install the hook
        try:
            success = manager.install_pre_commit_hook(quiet=True)
            if success:
                return InitStepResult(
                    step_name="git_hooks",
                    success=True,
                    message=f"Installed git pre-commit hook for collection '{self.collection_name}'",
                )
            else:
                return InitStepResult(
                    step_name="git_hooks",
                    success=False,
                    message="Failed to install git pre-commit hook",
                )
        except Exception as e:
            return InitStepResult(
                step_name="git_hooks",
                success=False,
                message=f"Error installing git hook: {e}",
            )

    def verify_hooks(self) -> dict:
        """Verify that installed hooks are functional.

        Returns:
            Dictionary with verification results.
        """
        results = {
            "claude_hooks": {},
            "git_hook": False,
        }

        # Check Claude hooks
        for hook_file in self.CLAUDE_HOOK_FILES:
            hook_path = self.hooks_dest / hook_file
            results["claude_hooks"][hook_file] = {
                "exists": hook_path.exists(),
                "executable": hook_path.exists()
                and os.access(hook_path, os.X_OK)
                if hook_file.endswith(".sh")
                else True,
            }

        # Check git hook
        manager = GitHooksManager(str(self.project_path), self.collection_name)
        results["git_hook"] = manager.is_hook_installed()

        return results

    def uninstall_claude_hooks(self) -> InitStepResult:
        """Remove Claude hooks from .claude/hooks/ directory.

        Returns:
            InitStepResult indicating success or failure.
        """
        if not self.hooks_dest.exists():
            return InitStepResult(
                step_name="uninstall_claude_hooks",
                success=True,
                skipped=True,
                message="No hooks directory found",
            )

        removed: List[str] = []
        for hook_file in self.CLAUDE_HOOK_FILES:
            hook_path = self.hooks_dest / hook_file
            if hook_path.exists():
                try:
                    hook_path.unlink()
                    removed.append(hook_file)
                except IOError as e:
                    logger.error(f"Failed to remove {hook_file}: {e}")

        return InitStepResult(
            step_name="uninstall_claude_hooks",
            success=True,
            message=f"Removed {len(removed)} hooks" if removed else "No hooks to remove",
        )

    def uninstall_git_hooks(self) -> InitStepResult:
        """Remove git pre-commit hook.

        Returns:
            InitStepResult indicating success or failure.
        """
        manager = GitHooksManager(str(self.project_path), self.collection_name)

        if not manager.is_git_repository():
            return InitStepResult(
                step_name="uninstall_git_hooks",
                success=True,
                skipped=True,
                message="Not a git repository",
            )

        if not manager.is_hook_installed():
            return InitStepResult(
                step_name="uninstall_git_hooks",
                success=True,
                skipped=True,
                message="Git hook not installed",
            )

        try:
            success = manager.uninstall_pre_commit_hook()
            return InitStepResult(
                step_name="uninstall_git_hooks",
                success=success,
                message="Removed git pre-commit hook" if success else "Failed to remove hook",
            )
        except Exception as e:
            return InitStepResult(
                step_name="uninstall_git_hooks",
                success=False,
                message=f"Error removing git hook: {e}",
            )
