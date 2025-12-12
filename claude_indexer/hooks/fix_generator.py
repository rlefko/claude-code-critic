"""
Fix suggestion generator for Claude self-repair loop.

This module generates fix suggestions from rules with auto-fix capability.
Each finding is analyzed to determine if the corresponding rule can
automatically fix the issue, and if so, generates a preview of the fix.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..rules.base import Finding, RuleContext
from ..rules.fix import AutoFix

if TYPE_CHECKING:
    from ..rules.base import BaseRule
    from ..rules.engine import RuleEngine

logger = logging.getLogger(__name__)


@dataclass
class FixSuggestion:
    """A suggested fix for a finding.

    Contains the original finding, optional auto-fix, and metadata
    about the fix confidence and action required.

    Attributes:
        finding: The original Finding being fixed
        auto_fix: AutoFix object if rule supports auto-fixing, None otherwise
        confidence: Confidence score (0.0-1.0) for the fix
        action: Action type - "auto_available" or "manual_required"
        description: Human-readable description of the fix
        code_preview: Diff-style preview of the fix, or None
    """

    finding: Finding
    auto_fix: AutoFix | None = None
    confidence: float = 0.0
    action: str = "manual_required"  # "auto_available" | "manual_required"
    description: str = ""
    code_preview: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "rule_id": self.finding.rule_id,
            "file_path": self.finding.file_path,
            "line_number": self.finding.line_number,
            "action": self.action,
            "confidence": self.confidence,
            "description": self.description,
        }

        if self.auto_fix:
            result["auto_fix"] = {
                "old_code": self.auto_fix.old_code,
                "new_code": self.auto_fix.new_code,
                "line_start": self.auto_fix.line_start,
                "line_end": self.auto_fix.line_end,
            }

        if self.code_preview:
            result["code_preview"] = self.code_preview

        return result


@dataclass
class FixSuggestionGenerator:
    """Generates fix suggestions by invoking rule auto_fix methods.

    Works with the RuleEngine to look up rules by ID and generate
    fix suggestions for findings that have auto-fix capability.

    Attributes:
        engine: RuleEngine instance for rule lookup
    """

    engine: "RuleEngine"
    _rule_cache: dict[str, "BaseRule"] = field(default_factory=dict)

    def generate_suggestions(
        self,
        findings: list[Finding],
        context_map: dict[str, RuleContext],
    ) -> list[FixSuggestion]:
        """Generate fix suggestions for all findings.

        Args:
            findings: List of findings to generate suggestions for
            context_map: Map of file_path -> RuleContext for each file

        Returns:
            List of FixSuggestion objects
        """
        suggestions = []

        for finding in findings:
            suggestion = self._generate_suggestion(finding, context_map)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _generate_suggestion(
        self,
        finding: Finding,
        context_map: dict[str, RuleContext],
    ) -> FixSuggestion | None:
        """Generate a fix suggestion for a single finding.

        Args:
            finding: Finding to generate suggestion for
            context_map: Map of file_path -> RuleContext

        Returns:
            FixSuggestion or None if suggestion cannot be generated
        """
        # Get the rule that produced this finding
        rule = self._get_rule_for_finding(finding)
        if not rule:
            logger.debug(f"Rule not found for finding: {finding.rule_id}")
            return self._create_manual_suggestion(finding)

        # Get context for the file
        context = context_map.get(finding.file_path)
        if not context:
            logger.debug(f"Context not found for file: {finding.file_path}")
            return self._create_manual_suggestion(finding)

        # Check if rule supports auto-fix
        if not rule.can_auto_fix():
            return self._create_manual_suggestion(finding)

        # Try to generate auto-fix
        auto_fix = self._try_auto_fix(finding, rule, context)
        if not auto_fix:
            return self._create_manual_suggestion(finding)

        # Generate preview
        code_preview = auto_fix.preview()

        return FixSuggestion(
            finding=finding,
            auto_fix=auto_fix,
            confidence=finding.confidence,
            action="auto_available",
            description=auto_fix.description,
            code_preview=code_preview,
        )

    def _get_rule_for_finding(self, finding: Finding) -> "BaseRule | None":
        """Look up rule by finding.rule_id.

        Args:
            finding: Finding to look up rule for

        Returns:
            BaseRule instance or None if not found
        """
        rule_id = finding.rule_id

        # Check cache first
        if rule_id in self._rule_cache:
            return self._rule_cache[rule_id]

        # Look up in engine
        rule = self.engine._rules.get(rule_id)
        if rule:
            self._rule_cache[rule_id] = rule

        return rule

    def _try_auto_fix(
        self,
        finding: Finding,
        rule: "BaseRule",
        context: RuleContext,
    ) -> AutoFix | None:
        """Safely invoke rule.auto_fix(), return None on error.

        Args:
            finding: Finding to generate fix for
            rule: Rule that produced the finding
            context: RuleContext for the file

        Returns:
            AutoFix or None if auto-fix failed
        """
        try:
            return rule.auto_fix(finding, context)
        except Exception as e:
            logger.warning(
                f"Auto-fix failed for {finding.rule_id} at "
                f"{finding.file_path}:{finding.line_number}: {e}"
            )
            return None

    def _create_manual_suggestion(self, finding: Finding) -> FixSuggestion:
        """Create a manual-fix suggestion for findings without auto-fix.

        Args:
            finding: Finding to create suggestion for

        Returns:
            FixSuggestion with action="manual_required"
        """
        # Use remediation hints if available
        description = (
            finding.remediation_hints[0]
            if finding.remediation_hints
            else f"Review and fix: {finding.summary}"
        )

        return FixSuggestion(
            finding=finding,
            auto_fix=None,
            confidence=finding.confidence,
            action="manual_required",
            description=description,
            code_preview=None,
        )


def _detect_language(file_path: Path) -> str:
    """Detect language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language identifier string
    """
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


def create_context_for_file(file_path: Path, content: str | None = None) -> RuleContext:
    """Create a RuleContext for a file.

    Args:
        file_path: Path to the file
        content: Optional file content (will read from disk if not provided)

    Returns:
        RuleContext for the file
    """
    path = Path(file_path)

    if content is None:
        try:
            content = path.read_text()
        except (OSError, UnicodeDecodeError):
            content = ""

    language = _detect_language(path)

    return RuleContext(
        file_path=path,
        content=content,
        language=language,
    )
