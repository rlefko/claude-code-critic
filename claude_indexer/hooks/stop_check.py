"""
Stop check executor for end-of-turn comprehensive quality checks.

Runs at the end of each Claude turn to analyze ALL uncommitted changes.
Unlike PostToolUse (<300ms, single file), the Stop hook:
- Checks all uncommitted files in a single execution
- Runs all ON_STOP rules (not just fast ones)
- Has a relaxed time budget of <5 seconds
- Can BLOCK Claude with exit code 2 for critical issues
- Provides structured error messages for Claude's self-repair loop

This module is used by the end-of-turn-check.sh hook.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from ..rules.base import DiffHunk, Finding, RuleContext, Severity, Trigger
from ..rules.engine import RuleEngine, RuleEngineResult, create_rule_engine


@dataclass
class StopCheckResult:
    """Result of stop check quality analysis."""

    findings: list[Finding] = field(default_factory=list)
    execution_time_ms: float = 0.0
    rules_executed: int = 0
    files_checked: int = 0
    should_block: bool = False
    error: str | None = None

    @property
    def critical_count(self) -> int:
        """Count of critical findings."""
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        """Count of high findings."""
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        """Count of medium findings."""
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        """Count of low findings."""
        return sum(1 for f in self.findings if f.severity == Severity.LOW)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        status = "blocked" if self.should_block else ("warn" if self.findings else "ok")
        return {
            "status": status,
            "should_block": self.should_block,
            "findings": [f.to_dict() for f in self.findings],
            "execution_time_ms": round(self.execution_time_ms, 2),
            "rules_executed": self.rules_executed,
            "files_checked": self.files_checked,
            "summary": {
                "total": len(self.findings),
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
            "error": self.error,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


@dataclass
class FileChange:
    """Simplified file change info for stop check."""

    file_path: Path
    change_type: str  # 'added', 'modified', 'deleted'
    added_lines: list[tuple[int, int]] = field(default_factory=list)


class StopCheckExecutor:
    """Singleton executor for comprehensive end-of-turn checks.

    Uses singleton pattern to avoid repeated rule loading overhead.
    Unlike PostWriteExecutor, this:
    - Checks ALL uncommitted files
    - Runs ALL ON_STOP rules (not just fast ones)
    - Populates diff context for change-aware checking
    - Has 5s time budget (vs 300ms for post-write)

    Example usage:
        executor = StopCheckExecutor.get_instance()
        result = executor.check_uncommitted_changes(Path("/project"))
        if result.should_block:
            print(format_findings_for_claude(result))
            sys.exit(2)
    """

    _instance: ClassVar["StopCheckExecutor | None"] = None
    _engine: ClassVar[RuleEngine | None] = None

    @classmethod
    def get_instance(cls) -> "StopCheckExecutor":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        cls._instance = None
        cls._engine = None

    def __init__(self) -> None:
        """Initialize with pre-loaded rules."""
        if StopCheckExecutor._engine is None:
            StopCheckExecutor._engine = create_rule_engine(auto_load=True)

    @property
    def engine(self) -> RuleEngine:
        """Get the rule engine instance."""
        if StopCheckExecutor._engine is None:
            StopCheckExecutor._engine = create_rule_engine(auto_load=True)
        return StopCheckExecutor._engine

    def check_uncommitted_changes(
        self,
        project_path: Path,
        timeout_ms: float = 5000.0,
        severity_threshold: Severity = Severity.HIGH,
    ) -> StopCheckResult:
        """Run comprehensive checks on all uncommitted changes.

        Args:
            project_path: Root directory of the project
            timeout_ms: Maximum execution time (soft limit for logging)
            severity_threshold: Minimum severity to trigger blocking

        Returns:
            StopCheckResult with findings and blocking status
        """
        start_time = time.time()
        all_findings: list[Finding] = []
        total_rules_executed = 0
        files_checked = 0

        try:
            # Collect all changed files using git
            changed_files = self._collect_changed_files(project_path)

            if not changed_files:
                # No uncommitted changes
                elapsed_ms = (time.time() - start_time) * 1000
                return StopCheckResult(
                    execution_time_ms=elapsed_ms,
                    files_checked=0,
                )

            # Process each changed file
            for file_change in changed_files:
                # Skip deleted files
                if file_change.change_type == "deleted":
                    continue

                file_path = project_path / file_change.file_path

                # Skip if file doesn't exist or isn't readable
                if not file_path.exists() or not file_path.is_file():
                    continue

                # Skip binary and non-code files
                if not self._is_code_file(file_path):
                    continue

                try:
                    # Create context with diff info
                    context = self._create_context_with_diff(
                        file_path, file_change, project_path
                    )

                    # Run ON_STOP rules
                    engine_result: RuleEngineResult = self.engine.run(
                        context, trigger=Trigger.ON_STOP
                    )

                    all_findings.extend(engine_result.findings)
                    total_rules_executed += engine_result.rules_executed
                    files_checked += 1

                except Exception as e:
                    # Log but continue on file errors
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Error checking {file_path}: {e}"
                    )

            elapsed_ms = (time.time() - start_time) * 1000

            # Log warning if we exceeded time budget
            if elapsed_ms > timeout_ms:
                import logging

                logging.getLogger(__name__).warning(
                    f"Stop check exceeded time budget: {elapsed_ms:.1f}ms > {timeout_ms}ms"
                )

            # Determine if we should block based on severity threshold
            should_block = self._should_block(all_findings, severity_threshold)

            return StopCheckResult(
                findings=all_findings,
                execution_time_ms=elapsed_ms,
                rules_executed=total_rules_executed,
                files_checked=files_checked,
                should_block=should_block,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return StopCheckResult(
                error=str(e),
                execution_time_ms=elapsed_ms,
            )

    def _collect_changed_files(self, project_path: Path) -> list[FileChange]:
        """Collect all uncommitted changes using git.

        Gets both staged and unstaged changes.

        Args:
            project_path: Root directory of the git repository

        Returns:
            List of FileChange objects for changed files
        """
        changes: list[FileChange] = []

        try:
            # Get staged + unstaged changes (all uncommitted)
            result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                # Try without HEAD (for initial commits)
                result = subprocess.run(
                    ["git", "diff", "--name-status", "--cached"],
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                parts = line.split("\t")
                if len(parts) < 2:
                    continue

                status = parts[0][0]
                file_path_str = parts[-1]

                if status == "A":
                    change_type = "added"
                elif status == "M":
                    change_type = "modified"
                elif status == "D":
                    change_type = "deleted"
                else:
                    change_type = "modified"

                # Get line-level changes for non-deleted files
                added_lines: list[tuple[int, int]] = []
                if change_type != "deleted":
                    added_lines = self._get_added_line_ranges(
                        project_path, Path(file_path_str)
                    )

                changes.append(
                    FileChange(
                        file_path=Path(file_path_str),
                        change_type=change_type,
                        added_lines=added_lines,
                    )
                )

            # Also get untracked files
            untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in untracked.stdout.strip().split("\n"):
                if line:
                    changes.append(
                        FileChange(
                            file_path=Path(line),
                            change_type="added",
                            added_lines=[],  # New file = all lines are new
                        )
                    )

        except subprocess.TimeoutExpired:
            import logging

            logging.getLogger(__name__).warning("Git command timed out")
        except subprocess.CalledProcessError:
            pass  # Not a git repo or git error
        except FileNotFoundError:
            pass  # Git not installed

        return changes

    def _get_added_line_ranges(
        self, project_path: Path, file_path: Path
    ) -> list[tuple[int, int]]:
        """Get line ranges that were added/modified.

        Args:
            project_path: Root directory of the project
            file_path: Relative path to the file

        Returns:
            List of (start, end) tuples for added line ranges
        """
        import re

        added_ranges: list[tuple[int, int]] = []

        try:
            result = subprocess.run(
                ["git", "diff", "-U0", "HEAD", "--", str(file_path)],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=5,
            )

            for line in result.stdout.split("\n"):
                if line.startswith("@@"):
                    # Parse @@ -a,b +c,d @@ format
                    match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
                    if match:
                        start = int(match.group(1))
                        count = int(match.group(2)) if match.group(2) else 1
                        if count > 0:
                            end = start + count - 1
                            added_ranges.append((start, end))

        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            pass

        return added_ranges

    def _create_context_with_diff(
        self,
        file_path: Path,
        file_change: FileChange,
        project_path: Path,
    ) -> RuleContext:
        """Create RuleContext with diff hunks populated.

        Args:
            file_path: Absolute path to the file
            file_change: FileChange with line range info
            project_path: Root directory for relative paths

        Returns:
            RuleContext with changed_lines and is_new_file set
        """
        content = file_path.read_text()
        language = self._detect_language(file_path)

        # Convert line ranges to set of individual line numbers
        changed_lines: set[int] = set()
        for start, end in file_change.added_lines:
            changed_lines.update(range(start, end + 1))

        # For new files, mark all lines as changed
        is_new_file = file_change.change_type == "added"
        if is_new_file and not changed_lines:
            # All lines are new for added files
            line_count = len(content.split("\n"))
            changed_lines = set(range(1, line_count + 1))

        # Create diff hunks for rules that need them
        diff_hunks: list[DiffHunk] = []
        for start, end in file_change.added_lines:
            diff_hunks.append(
                DiffHunk(
                    old_start=0,
                    old_count=0,
                    new_start=start,
                    new_count=end - start + 1,
                    lines=[],
                )
            )

        return RuleContext(
            file_path=file_path,
            content=content,
            language=language,
            diff_hunks=diff_hunks if diff_hunks else None,
            is_new_file=is_new_file,
            changed_lines=changed_lines if changed_lines else None,
        )

    def _detect_language(self, file_path: Path) -> str:
        """Detect language from file extension."""
        ext_to_lang = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".sh": "bash",
            ".bash": "bash",
            ".go": "go",
            ".rs": "rust",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
        }
        return ext_to_lang.get(file_path.suffix.lower(), "unknown")

    def _is_code_file(self, file_path: Path) -> bool:
        """Check if file is a code file worth checking.

        Args:
            file_path: Path to the file

        Returns:
            True if this is a code file that should be checked
        """
        # Skip binary/non-code extensions
        skip_extensions = {
            ".pyc",
            ".pyo",
            ".class",
            ".o",
            ".so",
            ".dll",
            ".exe",
            ".bin",
            ".db",
            ".sqlite",
            ".sqlite3",
            ".log",
            ".lock",
            ".png",
            ".jpg",
            ".jpeg",
            ".gif",
            ".ico",
            ".svg",
            ".woff",
            ".woff2",
            ".ttf",
            ".eot",
            ".pdf",
            ".zip",
            ".tar",
            ".gz",
            ".bz2",
            ".7z",
            ".rar",
        }

        # Skip certain directories
        skip_dirs = {
            "__pycache__",
            "node_modules",
            ".git",
            ".venv",
            "venv",
            ".env",
            "dist",
            "build",
            ".index_cache",
            ".claude",
        }

        # Check extension
        if file_path.suffix.lower() in skip_extensions:
            return False

        # Check if in skip directory
        return all(part not in skip_dirs for part in file_path.parts)

    def _should_block(self, findings: list[Finding], threshold: Severity) -> bool:
        """Determine if findings should block Claude.

        Args:
            findings: List of findings to check
            threshold: Minimum severity to trigger blocking

        Returns:
            True if Claude should be blocked
        """
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
        }

        threshold_value = severity_order.get(threshold, 1)

        for finding in findings:
            finding_value = severity_order.get(finding.severity, 3)
            if finding_value <= threshold_value:
                return True

        return False


def format_findings_for_claude(result: StopCheckResult) -> str:
    """Format findings for Claude's self-repair consumption.

    Uses the error message format specified in MILESTONES.md:

    CRITICAL: [rule_name] - [file:line]
    Description: [clear explanation]
    Suggestion: [how to fix]
    ---

    Args:
        result: StopCheckResult to format

    Returns:
        Multi-line string suitable for Claude self-repair
    """
    if not result.findings:
        return ""

    lines = [
        "",
        (
            "=== QUALITY CHECK BLOCKED ==="
            if result.should_block
            else "=== QUALITY CHECK WARNINGS ==="
        ),
        "",
    ]

    # Sort findings by severity (critical first)
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.HIGH: 1,
        Severity.MEDIUM: 2,
        Severity.LOW: 3,
    }
    sorted_findings = sorted(
        result.findings, key=lambda f: severity_order.get(f.severity, 3)
    )

    for finding in sorted_findings:
        lines.append(format_single_finding_for_claude(finding))
        lines.append("---")

    # Add summary
    lines.append("")
    result.critical_count + result.high_count
    lines.append(
        f"Found {len(result.findings)} issue(s): "
        f"{result.critical_count} critical, {result.high_count} high, "
        f"{result.medium_count} medium, {result.low_count} low"
    )

    if result.should_block:
        lines.append("Please fix the critical/high issues to proceed.")

    lines.append(
        f"Checked {result.files_checked} files in {result.execution_time_ms:.0f}ms"
    )
    lines.append("")

    return "\n".join(lines)


def format_single_finding_for_claude(finding: Finding) -> str:
    """Format a single finding for Claude self-repair.

    Args:
        finding: Finding to format

    Returns:
        Formatted string for this finding
    """
    severity = finding.severity.value.upper()
    location = str(finding.file_path)
    if finding.line_number:
        location += f":{finding.line_number}"

    lines = [
        f"{severity}: {finding.rule_id} - {location}",
        f"Description: {finding.summary}",
    ]

    if finding.remediation_hints:
        lines.append(f"Suggestion: {finding.remediation_hints[0]}")

    return "\n".join(lines)


def format_findings_for_display(result: StopCheckResult) -> str:
    """Format findings for human-readable display.

    Args:
        result: StopCheckResult to format

    Returns:
        Multi-line string suitable for terminal output
    """
    if not result.findings:
        return ""

    lines = []

    # Group findings by severity
    severity_order = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]
    severity_icons = {
        Severity.CRITICAL: "\u274c",  # Red X
        Severity.HIGH: "\u26a0\ufe0f",  # Warning
        Severity.MEDIUM: "\u2139\ufe0f",  # Info
        Severity.LOW: "\U0001f4dd",  # Memo
    }

    for severity in severity_order:
        findings = [f for f in result.findings if f.severity == severity]
        if not findings:
            continue

        for finding in findings:
            icon = severity_icons.get(severity, "")
            location = str(finding.file_path)
            if finding.line_number:
                location += f":{finding.line_number}"

            lines.append(f"{icon} [{severity.value.upper()}] {finding.rule_id}")
            lines.append(f"   {location}")
            lines.append(f"   {finding.summary}")

            if finding.remediation_hints:
                lines.append(f"   Suggestion: {finding.remediation_hints[0]}")

            lines.append("")

    # Add summary
    if result.execution_time_ms:
        lines.append(
            f"Checked {result.files_checked} files in {result.execution_time_ms:.0f}ms"
        )

    return "\n".join(lines)


def run_stop_check(
    project: str = ".",
    output_json: bool = False,
    timeout_ms: int = 5000,
    threshold: str = "high",
) -> int:
    """Run stop checks and output results.

    This is the main entry point for the CLI command.

    Args:
        project: Path to project directory
        output_json: Whether to output JSON format
        timeout_ms: Timeout in milliseconds
        threshold: Severity threshold ('critical', 'high', 'medium', 'low')

    Returns:
        Exit code: 0 = no blocking issues, 1 = warnings, 2 = blocked
    """
    # Map threshold string to Severity
    threshold_map = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    severity_threshold = threshold_map.get(threshold.lower(), Severity.HIGH)

    executor = StopCheckExecutor.get_instance()
    result = executor.check_uncommitted_changes(
        Path(project).resolve(),
        timeout_ms=float(timeout_ms),
        severity_threshold=severity_threshold,
    )

    if output_json:
        print(result.to_json())
    elif result.findings:
        if result.should_block:
            print(format_findings_for_claude(result))
        else:
            print(format_findings_for_display(result))
    elif result.error:
        print(f"Error: {result.error}", file=sys.stderr)

    # Exit code: 2 = blocked, 1 = warnings, 0 = clean
    if result.should_block:
        return 2
    elif result.findings:
        return 1
    return 0


def run_stop_check_with_repair(
    project: str = ".",
    output_json: bool = False,
    timeout_ms: int = 5000,
    threshold: str = "high",
) -> int:
    """Run stop checks with repair loop tracking.

    Like run_stop_check but tracks session state for retry limiting.
    After 3 failed attempts with the same findings, escalates to user.

    Args:
        project: Path to project directory
        output_json: Whether to output JSON format
        timeout_ms: Timeout in milliseconds
        threshold: Severity threshold ('critical', 'high', 'medium', 'low')

    Returns:
        Exit code:
            0 = no blocking issues
            1 = warnings (non-blocking)
            2 = blocked (Claude should fix)
            3 = escalated (max retries exceeded, ask user)
    """
    from .fix_generator import FixSuggestionGenerator, create_context_for_file
    from .repair_result import RepairCheckResult
    from .repair_session import RepairSessionManager

    # Map threshold string to Severity
    threshold_map = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
    }
    severity_threshold = threshold_map.get(threshold.lower(), Severity.HIGH)

    project_path = Path(project).resolve()

    # Run the base stop check
    executor = StopCheckExecutor.get_instance()
    base_result = executor.check_uncommitted_changes(
        project_path,
        timeout_ms=float(timeout_ms),
        severity_threshold=severity_threshold,
    )

    # If no blocking issues, return clean
    if not base_result.should_block:
        if output_json:
            print(base_result.to_json())
        elif base_result.findings:
            print(format_findings_for_display(base_result))

        return 1 if base_result.findings else 0

    # Track repair session for blocking issues
    session_manager = RepairSessionManager(project_path)

    # Get or create session based on findings
    session = session_manager.get_or_create_session(base_result.findings)

    # Check if this is the same issue as before
    current_hash = session_manager.compute_findings_hash(base_result.findings)
    is_same_issue = session.findings_hash == current_hash

    # Record this attempt
    session = session_manager.record_attempt(session)

    # Generate fix suggestions
    fix_suggestions = []
    if base_result.findings:
        try:
            # Build context map for fix generation
            context_map = {}
            for finding in base_result.findings:
                if finding.file_path not in context_map:
                    file_path = project_path / finding.file_path
                    if file_path.exists():
                        context_map[finding.file_path] = create_context_for_file(
                            file_path
                        )

            # Generate suggestions
            generator = FixSuggestionGenerator(engine=executor._engine)
            fix_suggestions = generator.generate_suggestions(
                base_result.findings, context_map
            )
        except Exception as e:
            # Log but continue without fix suggestions
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to generate fix suggestions: {e}"
            )

    # Create repair result
    repair_result = RepairCheckResult(
        base_result=base_result,
        session=session,
        fix_suggestions=fix_suggestions,
        is_same_issue=is_same_issue,
    )

    # Output result
    if output_json:
        print(repair_result.to_json())
    else:
        print(repair_result.format_for_claude())

    # Determine exit code
    if repair_result.should_escalate:
        return 3  # Escalated to user
    elif repair_result.should_block:
        return 2  # Blocked, Claude should fix
    elif base_result.findings:
        return 1  # Warnings
    return 0  # Clean
