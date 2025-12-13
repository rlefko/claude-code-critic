#!/usr/bin/env python3
"""
SessionStart Hook - Immediate Project Context Injection.

Runs once when a Claude Code session starts to:
1. Show recent git activity for context
2. Display uncommitted changes summary
3. Remind about memory-first workflow
4. Check for pending analysis or issues

Performance target: <100ms total execution
"""

import json
import os
import subprocess
import sys


def run_git_command(cmd: list, cwd: str) -> str | None:
    """Run a git command and return output, or None on error."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,  # Fast timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def get_git_activity(cwd: str) -> dict:
    """Get recent git activity summary."""
    activity = {
        "branch": None,
        "uncommitted": False,
        "recent_commits": [],
        "changed_files": 0,
    }

    # Get current branch
    branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch:
        activity["branch"] = branch

    # Check for uncommitted changes
    status = run_git_command(["git", "status", "--porcelain"], cwd)
    if status:
        activity["uncommitted"] = True
        activity["changed_files"] = len(status.strip().split("\n"))

    # Get recent commit subjects (last 3)
    log = run_git_command(
        ["git", "log", "--oneline", "-3", "--format=%s"],
        cwd,
    )
    if log:
        activity["recent_commits"] = log.strip().split("\n")[:3]

    return activity


def build_context(cwd: str, collection: str) -> str:
    """Build session start context message."""
    lines = []
    prefix = f"mcp__{collection}-memory__"

    # Header
    lines.append("=== Session Context ===")

    # Git activity
    git = get_git_activity(cwd)
    if git["branch"]:
        lines.append(f"Branch: {git['branch']}")

    if git["uncommitted"]:
        lines.append(f"Uncommitted changes: {git['changed_files']} file(s)")

    if git["recent_commits"]:
        lines.append("Recent commits:")
        for commit in git["recent_commits"][:3]:
            # Truncate long commit messages
            msg = commit[:60] + "..." if len(commit) > 60 else commit
            lines.append(f"  - {msg}")

    # Memory reminder
    lines.append("")
    lines.append("Memory-First Reminder:")
    lines.append(f"  Use `{prefix}search_similar()` before reading files")
    lines.append(f"  Use `{prefix}read_graph()` to understand relationships")

    return "\n".join(lines)


def main():
    """Run the session start hook."""
    try:
        # Read input from stdin
        input_data = json.load(sys.stdin)
        cwd = input_data.get("cwd", os.getcwd())

        # Get collection from environment or default
        collection = os.environ.get("CLAUDE_MEMORY_COLLECTION", "project")

        # Build and output context
        context = build_context(cwd, collection)
        print(context)

        sys.exit(0)

    except Exception as e:
        # Fail open - don't block on errors
        sys.stderr.write(f"session_start warning: {e}\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
