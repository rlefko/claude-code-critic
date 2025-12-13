"""Data models for UI consistency checking.

This module defines the core data structures used throughout the UI consistency
guard system, including symbol references, fingerprints, and findings.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(Enum):
    """Severity levels for UI consistency findings."""

    FAIL = "fail"  # Blocks commit/PR
    WARN = "warn"  # Highlighted but doesn't block
    INFO = "info"  # Informational only


class SymbolKind(Enum):
    """Types of UI symbols that can be analyzed."""

    COMPONENT = "component"  # React/Vue/Svelte component
    CSS = "css"  # CSS rule or class
    STYLE_OBJECT = "styleObject"  # Inline style object
    MODULE = "module"  # CSS module or style module


class EvidenceType(Enum):
    """Types of evidence that support a finding."""

    STATIC = "static"  # Code location + extracted style/component signature
    SEMANTIC = "semantic"  # Nearest neighbors from Qdrant (what to reuse)
    RUNTIME = "runtime"  # Computed style diff, layout metrics
    VISUAL = "visual"  # Screenshots or pHash similarity group


class Visibility(Enum):
    """Visibility of a symbol in the codebase."""

    PUBLIC = "public"  # Exported and documented
    EXPORTED = "exported"  # Exported but not necessarily documented
    INTERNAL = "internal"  # Used within module
    LOCAL = "local"  # Only used in defining file


@dataclass
class SymbolRef:
    """Reference to a code symbol location.

    Provides file path and line information for any UI-related symbol
    that can be analyzed for consistency.
    """

    file_path: str
    start_line: int
    end_line: int
    kind: SymbolKind
    visibility: Visibility = Visibility.LOCAL
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "kind": self.kind.value,
            "visibility": self.visibility.value,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SymbolRef":
        """Create from dictionary."""
        return cls(
            file_path=data["file_path"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            kind=SymbolKind(data["kind"]),
            visibility=Visibility(data.get("visibility", "local")),
            name=data.get("name"),
        )

    def __str__(self) -> str:
        """Return file:line format for easy navigation."""
        name_part = f" ({self.name})" if self.name else ""
        return f"{self.file_path}:{self.start_line}{name_part}"


@dataclass
class Evidence:
    """Evidence supporting a UI consistency finding.

    Each finding should have at least two evidence types to reduce noise
    and ensure high-confidence results.
    """

    evidence_type: EvidenceType
    description: str
    data: dict[str, Any] = field(default_factory=dict)
    source_ref: SymbolRef | None = None
    screenshot_path: str | None = None
    similarity_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "evidence_type": self.evidence_type.value,
            "description": self.description,
            "data": self.data,
        }
        if self.source_ref:
            result["source_ref"] = self.source_ref.to_dict()
        if self.screenshot_path:
            result["screenshot_path"] = self.screenshot_path
        if self.similarity_score is not None:
            result["similarity_score"] = self.similarity_score
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        """Create from dictionary."""
        source_ref = None
        if "source_ref" in data and data["source_ref"]:
            source_ref = SymbolRef.from_dict(data["source_ref"])

        return cls(
            evidence_type=EvidenceType(data["evidence_type"]),
            description=data["description"],
            data=data.get("data", {}),
            source_ref=source_ref,
            screenshot_path=data.get("screenshot_path"),
            similarity_score=data.get("similarity_score"),
        )


@dataclass
class StyleFingerprint:
    """Fingerprint for a style block or CSS rule.

    Used for detecting duplicate and near-duplicate styles across
    the codebase.
    """

    declaration_set: dict[str, str]  # Canonical {property: value}
    exact_hash: str  # SHA256 for exact match detection
    near_hash: str  # SimHash/MinHash for near-duplicate detection
    tokens_used: list[str] = field(default_factory=list)  # Resolved design tokens
    source_refs: list[SymbolRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "declaration_set": self.declaration_set,
            "exact_hash": self.exact_hash,
            "near_hash": self.near_hash,
            "tokens_used": self.tokens_used,
            "source_refs": [ref.to_dict() for ref in self.source_refs],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleFingerprint":
        """Create from dictionary."""
        return cls(
            declaration_set=data["declaration_set"],
            exact_hash=data["exact_hash"],
            near_hash=data["near_hash"],
            tokens_used=data.get("tokens_used", []),
            source_refs=[
                SymbolRef.from_dict(ref) for ref in data.get("source_refs", [])
            ],
        )


@dataclass
class StaticComponentFingerprint:
    """Fingerprint for a UI component based on static analysis.

    Used for detecting duplicate components and suggesting reuse
    opportunities.
    """

    structure_hash: str  # Normalized render tree / template skeleton hash
    style_refs: list[str] = field(
        default_factory=list
    )  # Class tokens, CSS module keys, inline style keys
    prop_shape_sketch: dict[str, str] | None = None  # Prop names only, optional types
    embedding_id: str | None = None  # Qdrant point id for semantic search
    source_ref: SymbolRef | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "structure_hash": self.structure_hash,
            "style_refs": self.style_refs,
            "prop_shape_sketch": self.prop_shape_sketch,
            "embedding_id": self.embedding_id,
        }
        if self.source_ref:
            result["source_ref"] = self.source_ref.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StaticComponentFingerprint":
        """Create from dictionary."""
        source_ref = None
        if "source_ref" in data and data["source_ref"]:
            source_ref = SymbolRef.from_dict(data["source_ref"])

        return cls(
            structure_hash=data["structure_hash"],
            style_refs=data.get("style_refs", []),
            prop_shape_sketch=data.get("prop_shape_sketch"),
            embedding_id=data.get("embedding_id"),
            source_ref=source_ref,
        )


@dataclass
class LayoutBox:
    """Layout box measurements for a runtime element."""

    x: float
    y: float
    width: float
    height: float
    padding: dict[str, float] = field(default_factory=dict)  # top, right, bottom, left
    margin: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "padding": self.padding,
            "margin": self.margin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LayoutBox":
        """Create from dictionary."""
        return cls(
            x=data["x"],
            y=data["y"],
            width=data["width"],
            height=data["height"],
            padding=data.get("padding", {}),
            margin=data.get("margin", {}),
        )


@dataclass
class RuntimeElementFingerprint:
    """Fingerprint for a UI element captured at runtime via Playwright.

    Contains computed styles, layout information, and optional
    visual similarity data.
    """

    page_id: str  # Page or story identifier
    selector: str  # Stable selector (prefer data-testid/data-component)
    role: str  # button/input/card/heading/link etc.
    computed_style_subset: dict[str, str] = field(
        default_factory=dict
    )  # Canonical computed styles
    layout_box: LayoutBox | None = None
    screenshot_hash: str | None = None  # pHash for visual clustering
    source_map_hint: str | None = None  # Component name if available

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "page_id": self.page_id,
            "selector": self.selector,
            "role": self.role,
            "computed_style_subset": self.computed_style_subset,
            "screenshot_hash": self.screenshot_hash,
            "source_map_hint": self.source_map_hint,
        }
        if self.layout_box:
            result["layout_box"] = self.layout_box.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeElementFingerprint":
        """Create from dictionary."""
        layout_box = None
        if "layout_box" in data and data["layout_box"]:
            layout_box = LayoutBox.from_dict(data["layout_box"])

        return cls(
            page_id=data["page_id"],
            selector=data["selector"],
            role=data["role"],
            computed_style_subset=data.get("computed_style_subset", {}),
            layout_box=layout_box,
            screenshot_hash=data.get("screenshot_hash"),
            source_map_hint=data.get("source_map_hint"),
        )


@dataclass
class Finding:
    """A UI consistency finding with evidence and remediation hints.

    Represents an issue detected by the UI quality system, with
    supporting evidence and actionable suggestions.
    """

    rule_id: str  # e.g., "COLOR.NON_TOKEN", "COMPONENT.DUPLICATE_CLUSTER"
    severity: Severity
    confidence: float  # 0.0 to 1.0
    summary: str  # Human-readable description
    evidence: list[Evidence] = field(default_factory=list)
    remediation_hints: list[str] = field(
        default_factory=list
    )  # Including "reuse these components"
    source_ref: SymbolRef | None = None  # Primary location
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_new: bool = True  # True if introduced in current PR/commit

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence": [e.to_dict() for e in self.evidence],
            "remediation_hints": self.remediation_hints,
            "created_at": self.created_at,
            "is_new": self.is_new,
        }
        if self.source_ref:
            result["source_ref"] = self.source_ref.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        """Create from dictionary."""
        source_ref = None
        if "source_ref" in data and data["source_ref"]:
            source_ref = SymbolRef.from_dict(data["source_ref"])

        return cls(
            rule_id=data["rule_id"],
            severity=Severity(data["severity"]),
            confidence=data["confidence"],
            summary=data["summary"],
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            remediation_hints=data.get("remediation_hints", []),
            source_ref=source_ref,
            created_at=data.get("created_at", datetime.now().isoformat()),
            is_new=data.get("is_new", True),
        )

    def has_multi_evidence(self) -> bool:
        """Check if finding has at least two evidence types (reduces noise)."""
        evidence_types = {e.evidence_type for e in self.evidence}
        return len(evidence_types) >= 2


@dataclass
class UIAnalysisResult:
    """Complete result of a UI consistency analysis run.

    Contains all findings organized by severity, along with metadata
    about the analysis run.
    """

    findings: list[Finding] = field(default_factory=list)
    files_analyzed: list[str] = field(default_factory=list)
    analysis_time_ms: float = 0.0
    tier: int = 0  # 0 = pre-commit, 1 = PR/CI, 2 = /redesign
    baseline_findings: list[Finding] = field(
        default_factory=list
    )  # Existing issues (not new)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "files_analyzed": self.files_analyzed,
            "analysis_time_ms": self.analysis_time_ms,
            "tier": self.tier,
            "baseline_findings": [f.to_dict() for f in self.baseline_findings],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UIAnalysisResult":
        """Create from dictionary."""
        return cls(
            findings=[Finding.from_dict(f) for f in data.get("findings", [])],
            files_analyzed=data.get("files_analyzed", []),
            analysis_time_ms=data.get("analysis_time_ms", 0.0),
            tier=data.get("tier", 0),
            baseline_findings=[
                Finding.from_dict(f) for f in data.get("baseline_findings", [])
            ],
            created_at=data.get("created_at", datetime.now().isoformat()),
        )

    @property
    def fail_count(self) -> int:
        """Count of FAIL severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.FAIL)

    @property
    def warn_count(self) -> int:
        """Count of WARN severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.WARN)

    @property
    def info_count(self) -> int:
        """Count of INFO severity findings."""
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    def should_block(self) -> bool:
        """Check if any findings should block the operation."""
        return self.fail_count > 0
