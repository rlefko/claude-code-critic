"""
Base classes and types for the code quality rule engine.

This module provides the foundational abstractions for creating
code quality rules including security, tech debt, resilience,
documentation, and git safety checks.
"""

import contextlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import RuleConfig, RuleEngineConfig


class Severity(Enum):
    """Severity levels for code quality findings."""

    CRITICAL = "critical"  # Must fix immediately, blocks commit
    HIGH = "high"  # Should fix soon, may block commit
    MEDIUM = "medium"  # Should fix eventually, warning
    LOW = "low"  # Nice to fix, informational

    def __lt__(self, other: "Severity") -> bool:
        order = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "Severity") -> bool:
        return self == other or self < other

    def __gt__(self, other: "Severity") -> bool:
        return not self <= other

    def __ge__(self, other: "Severity") -> bool:
        return not self < other


class Trigger(Enum):
    """When rules should run."""

    ON_WRITE = "on_write"  # After file write (PostToolUse)
    ON_STOP = "on_stop"  # End of turn (Stop hook)
    ON_COMMIT = "on_commit"  # Pre-commit hook
    ON_DEMAND = "on_demand"  # Manual invocation only


@dataclass
class DiffHunk:
    """Represents a diff hunk from git."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)

    @property
    def added_lines(self) -> set[int]:
        """Get line numbers of added lines."""
        result = set()
        current_line = self.new_start
        for line in self.lines:
            if line.startswith("+") and not line.startswith("+++"):
                result.add(current_line)
                current_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass  # Deleted line, don't increment
            else:
                current_line += 1
        return result


@dataclass
class Evidence:
    """Evidence supporting a finding."""

    description: str
    line_number: int | None = None
    code_snippet: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "description": self.description,
            "line_number": self.line_number,
            "code_snippet": self.code_snippet,
            "data": self.data,
        }


@dataclass
class Finding:
    """A code quality finding."""

    rule_id: str
    severity: Severity
    summary: str
    file_path: str
    line_number: int | None = None
    end_line: int | None = None
    evidence: list[Evidence] = field(default_factory=list)
    remediation_hints: list[str] = field(default_factory=list)
    can_auto_fix: bool = False
    confidence: float = 1.0
    is_new: bool = True  # New in this PR/commit
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "summary": self.summary,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "end_line": self.end_line,
            "evidence": [e.to_dict() for e in self.evidence],
            "remediation_hints": self.remediation_hints,
            "can_auto_fix": self.can_auto_fix,
            "confidence": self.confidence,
            "is_new": self.is_new,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        """Create Finding from dictionary."""
        return cls(
            rule_id=data["rule_id"],
            severity=Severity(data["severity"]),
            summary=data["summary"],
            file_path=data["file_path"],
            line_number=data.get("line_number"),
            end_line=data.get("end_line"),
            evidence=[
                Evidence(
                    description=e["description"],
                    line_number=e.get("line_number"),
                    code_snippet=e.get("code_snippet"),
                    data=e.get("data", {}),
                )
                for e in data.get("evidence", [])
            ],
            remediation_hints=data.get("remediation_hints", []),
            can_auto_fix=data.get("can_auto_fix", False),
            confidence=data.get("confidence", 1.0),
            is_new=data.get("is_new", True),
            created_at=data.get("created_at", datetime.now().isoformat()),
        )


@dataclass
class RuleContext:
    """Context passed to rules for evaluation."""

    # File context
    file_path: Path
    content: str
    language: str

    # Git/diff context
    diff_hunks: list[DiffHunk] | None = None
    is_new_file: bool = False
    changed_lines: set[int] | None = None

    # AST context (lazy-loaded)
    _ast_tree: Any = field(default=None, repr=False)
    _parser: Any = field(default=None, repr=False)

    # Memory context
    memory_client: Any = field(default=None, repr=False)  # Qdrant client
    collection_name: str | None = None

    # Configuration
    config: "RuleEngineConfig | None" = field(default=None, repr=False)

    @property
    def ast_tree(self) -> Any:
        """Lazy-load AST tree."""
        if self._ast_tree is None and self._parser is not None:
            with contextlib.suppress(Exception):
                self._ast_tree = self._parser.parse(self.content.encode())
        return self._ast_tree

    @property
    def lines(self) -> list[str]:
        """Get content as list of lines."""
        return self.content.split("\n")

    def is_line_in_diff(self, line_number: int) -> bool:
        """Check if a line is in the diff scope."""
        if self.changed_lines is None:
            return True  # No diff = assume everything is in scope
        return line_number in self.changed_lines

    def search_memory(
        self,
        query: str,
        limit: int = 5,
        entity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search semantic memory for similar code.

        Args:
            query: Search query string
            limit: Maximum number of results
            entity_types: Optional filter for entity types

        Returns:
            List of search results with score, name, type, etc.
        """
        if self.memory_client is None or self.collection_name is None:
            return []

        try:
            # Build search request
            results = self.memory_client.search(
                collection_name=self.collection_name,
                query_text=query,
                limit=limit,
            )
            return [
                {
                    "score": r.score,
                    "name": r.payload.get("name", ""),
                    "type": r.payload.get("entity_type", ""),
                    "file_path": r.payload.get("file_path", ""),
                    "content": r.payload.get("content", ""),
                }
                for r in results
            ]
        except Exception:
            return []

    def get_line_content(self, line_number: int) -> str | None:
        """Get content of a specific line (1-indexed)."""
        lines = self.lines
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]
        return None

    @classmethod
    def from_file(
        cls,
        file_path: Path,
        language: str | None = None,
        config: "RuleEngineConfig | None" = None,
    ) -> "RuleContext":
        """Create context from a file path."""
        content = file_path.read_text()

        # Auto-detect language from extension
        if language is None:
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
            }
            language = ext_to_lang.get(file_path.suffix.lower(), "unknown")

        return cls(
            file_path=file_path,
            content=content,
            language=language,
            config=config,
        )


class BaseRule(ABC):
    """Abstract base class for all code quality rules."""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier (e.g., 'SECURITY.SQL_INJECTION').

        Format: CATEGORY.RULE_NAME where CATEGORY is uppercase and
        RULE_NAME uses UPPER_SNAKE_CASE.
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Rule category: security, tech_debt, resilience, documentation, git."""

    @property
    @abstractmethod
    def default_severity(self) -> Severity:
        """Default severity level for findings from this rule."""

    @property
    def triggers(self) -> list[Trigger]:
        """When this rule should run. Default: all triggers except ON_DEMAND."""
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        """Languages this rule supports. None = all languages."""
        return None

    @property
    def description(self) -> str:
        """Detailed description of what this rule checks."""
        return f"Rule {self.rule_id}: {self.name}"

    @property
    def is_fast(self) -> bool:
        """Whether this rule is fast enough for on-write checks (<50ms).

        Fast rules use pattern matching or simple AST traversal.
        Slow rules use semantic analysis or external calls.
        """
        return True

    @abstractmethod
    def check(self, context: RuleContext) -> list[Finding]:
        """Run the rule check and return findings.

        Args:
            context: RuleContext with file content, diff info, etc.

        Returns:
            List of Finding objects for any issues detected.
        """

    def can_auto_fix(self) -> bool:
        """Whether this rule supports automatic fixes."""
        return False

    def auto_fix(self, finding: Finding, context: RuleContext) -> "AutoFix | None":
        """Generate an auto-fix for a finding.

        Override this method in subclasses that support auto-fix.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix object if fix is possible, None otherwise
        """
        return None

    def get_severity(self, config: "RuleConfig | None") -> Severity:
        """Get severity from config or use default.

        Args:
            config: Optional rule-specific configuration

        Returns:
            Severity level to use for findings
        """
        if config and config.severity_override:
            return Severity(config.severity_override)
        return self.default_severity

    def _create_finding(
        self,
        summary: str,
        file_path: str,
        line_number: int | None = None,
        end_line: int | None = None,
        evidence: list[Evidence] | None = None,
        remediation_hints: list[str] | None = None,
        config: "RuleConfig | None" = None,
        confidence: float = 1.0,
        is_new: bool = True,
    ) -> Finding:
        """Helper to create a Finding with this rule's ID and severity.

        Args:
            summary: Brief description of the issue
            file_path: Path to the file containing the issue
            line_number: Starting line number (1-indexed)
            end_line: Ending line number (optional)
            evidence: List of Evidence objects
            remediation_hints: List of suggestions for fixing
            config: Rule configuration for severity override
            confidence: Confidence score (0.0-1.0)
            is_new: Whether this is a new issue

        Returns:
            Populated Finding object
        """
        return Finding(
            rule_id=self.rule_id,
            severity=self.get_severity(config),
            summary=summary,
            file_path=file_path,
            line_number=line_number,
            end_line=end_line,
            evidence=evidence or [],
            remediation_hints=remediation_hints or [],
            can_auto_fix=self.can_auto_fix(),
            confidence=confidence,
            is_new=is_new,
        )


# Import AutoFix here to avoid circular imports
# The actual class is defined in fix.py
try:
    from .fix import AutoFix
except ImportError:
    # AutoFix not yet available during initial import
    AutoFix = None  # type: ignore
