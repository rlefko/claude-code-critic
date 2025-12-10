"""Base rule class for UI consistency checking.

This module defines the abstract base class for all UI consistency rules,
providing a standard interface for rule evaluation and finding generation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import Evidence, EvidenceType, Finding, Severity, SymbolRef

if TYPE_CHECKING:
    from ..config import UIQualityConfig


@dataclass
class RuleResult:
    """Result of a single rule evaluation.

    Contains findings, timing information, and any errors encountered.
    """

    rule_id: str
    findings: list[Finding] = field(default_factory=list)
    execution_time_ms: float = 0.0
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if rule executed without errors."""
        return self.error is None

    @property
    def finding_count(self) -> int:
        """Number of findings produced."""
        return len(self.findings)


class BaseRule(ABC):
    """Abstract base class for UI consistency rules.

    All rules must inherit from this class and implement the required
    abstract methods. Rules are responsible for:
    - Defining their unique identifier and category
    - Specifying default severity
    - Implementing evaluation logic
    - Generating properly structured findings with evidence
    """

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """Unique rule identifier.

        Format: CATEGORY.SPECIFIC_RULE (e.g., 'COLOR.NON_TOKEN')
        """

    @property
    @abstractmethod
    def category(self) -> str:
        """Rule category for severity mapping.

        One of: 'token_drift', 'duplication', 'inconsistency', 'smells'
        """

    @property
    @abstractmethod
    def default_severity(self) -> Severity:
        """Default severity level for findings from this rule."""

    @property
    def description(self) -> str:
        """Human-readable description of what this rule checks."""
        return f"Rule {self.rule_id}"

    @property
    def is_fast(self) -> bool:
        """Whether this rule is fast enough for pre-commit tier (<50ms).

        Override and return False for rules that require cross-file
        analysis, clustering, or other expensive operations.
        """
        return True

    @abstractmethod
    def evaluate(self, context: "RuleContext") -> list[Finding]:
        """Evaluate the rule and return findings.

        Args:
            context: RuleContext containing all data needed for evaluation.

        Returns:
            List of Finding objects for any violations detected.
        """

    def get_severity(self, config: "UIQualityConfig") -> Severity:
        """Get severity from config or use default.

        Args:
            config: UI quality configuration.

        Returns:
            Severity level for findings from this rule.
        """
        severity_map = {
            "token_drift": config.gating.severity_thresholds.token_drift,
            "duplication": config.gating.severity_thresholds.duplication,
            "inconsistency": config.gating.severity_thresholds.inconsistency,
            "smells": config.gating.severity_thresholds.smells,
        }
        severity_str = severity_map.get(self.category, "WARN")
        try:
            return Severity(severity_str.lower())
        except ValueError:
            return self.default_severity

    def _create_finding(
        self,
        summary: str,
        evidence: list[Evidence],
        config: "UIQualityConfig",
        source_ref: SymbolRef | None = None,
        confidence: float = 0.8,
        remediation_hints: list[str] | None = None,
        is_new: bool = True,
    ) -> Finding:
        """Create a properly structured Finding.

        Args:
            summary: Human-readable description of the issue.
            evidence: List of Evidence objects supporting this finding.
            config: UI quality configuration for severity lookup.
            source_ref: Primary code location for this finding.
            confidence: Confidence score between 0.0 and 1.0.
            remediation_hints: List of suggested fixes.
            is_new: Whether this is a new issue (vs baseline).

        Returns:
            Properly structured Finding object.
        """
        return Finding(
            rule_id=self.rule_id,
            severity=self.get_severity(config),
            confidence=confidence,
            summary=summary,
            evidence=evidence,
            remediation_hints=remediation_hints or [],
            source_ref=source_ref,
            created_at=datetime.now().isoformat(),
            is_new=is_new,
        )

    def _create_static_evidence(
        self,
        description: str,
        source_ref: SymbolRef | None = None,
        data: dict[str, Any] | None = None,
    ) -> Evidence:
        """Create static evidence (code location + signature).

        Args:
            description: Description of the evidence.
            source_ref: Code location reference.
            data: Additional evidence data.

        Returns:
            Evidence object of type STATIC.
        """
        return Evidence(
            evidence_type=EvidenceType.STATIC,
            description=description,
            source_ref=source_ref,
            data=data or {},
        )

    def _create_semantic_evidence(
        self,
        description: str,
        similarity_score: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> Evidence:
        """Create semantic evidence (Qdrant neighbors).

        Args:
            description: Description of the evidence.
            similarity_score: Similarity score from vector search.
            data: Additional evidence data (e.g., neighbor info).

        Returns:
            Evidence object of type SEMANTIC.
        """
        return Evidence(
            evidence_type=EvidenceType.SEMANTIC,
            description=description,
            similarity_score=similarity_score,
            data=data or {},
        )

    def _create_runtime_evidence(
        self,
        description: str,
        data: dict[str, Any] | None = None,
    ) -> Evidence:
        """Create runtime evidence (computed styles, layout).

        Args:
            description: Description of the evidence.
            data: Computed style or layout data.

        Returns:
            Evidence object of type RUNTIME.
        """
        return Evidence(
            evidence_type=EvidenceType.RUNTIME,
            description=description,
            data=data or {},
        )

    def _create_visual_evidence(
        self,
        description: str,
        screenshot_path: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Evidence:
        """Create visual evidence (screenshots, pHash).

        Args:
            description: Description of the evidence.
            screenshot_path: Path to screenshot file.
            data: Additional visual data (e.g., pHash).

        Returns:
            Evidence object of type VISUAL.
        """
        return Evidence(
            evidence_type=EvidenceType.VISUAL,
            description=description,
            screenshot_path=screenshot_path,
            data=data or {},
        )

    def __repr__(self) -> str:
        """String representation of the rule."""
        return f"<{self.__class__.__name__} {self.rule_id}>"


@dataclass
class RuleContext:
    """Context passed to rules for evaluation.

    Contains all the data rules need to evaluate consistency issues,
    including configuration, diff information, and extracted fingerprints.
    """

    config: "UIQualityConfig"
    styles: list[Any] = field(default_factory=list)  # StyleFingerprint
    components: list[Any] = field(default_factory=list)  # StaticComponentFingerprint
    diff_result: Any | None = None  # DiffResult
    token_resolver: Any | None = None  # TokenResolver
    similarity_engine: Any | None = None  # SimilarityEngine
    file_path: Path | None = None
    source_files: dict[str, str] = field(default_factory=dict)  # path -> content

    def get_style_declarations(self) -> list[dict[str, str]]:
        """Get declaration dicts from all style fingerprints."""
        declarations = []
        for style in self.styles:
            if hasattr(style, "declaration_set"):
                declarations.append(style.declaration_set)
        return declarations

    def get_changed_files(self) -> list[Path]:
        """Get list of changed files from diff result."""
        if self.diff_result is None:
            return []
        if hasattr(self.diff_result, "changes"):
            return [change.file_path for change in self.diff_result.changes]
        return []

    def is_line_in_diff(self, file_path: str, line_number: int) -> bool:
        """Check if a specific line is in the diff scope.

        Args:
            file_path: Path to the file.
            line_number: Line number to check.

        Returns:
            True if the line is in a changed region.
        """
        if self.diff_result is None:
            return True  # No diff = assume everything is new

        for change in getattr(self.diff_result, "changes", []):
            if str(change.file_path) == file_path:
                return change.contains_line(line_number)

        return False
