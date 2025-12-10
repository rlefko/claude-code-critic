"""Critique engine for comprehensive UI design analysis.

The CritiqueEngine orchestrates consistency, hierarchy, and affordance
analyzers to generate evidence-backed design critiques.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..ci.audit_runner import CIAuditResult
    from ..collectors.pseudo_states import PseudoStateCapture
    from ..collectors.runtime import CrawlResult
    from ..collectors.screenshots import VisualClusteringResult
    from ..config import UIQualityConfig
    from ..similarity.engine import SimilarityEngine

from ..models import Evidence, EvidenceType, RuntimeElementFingerprint, Severity, SymbolRef
from .affordance import AffordanceAnalyzer
from .consistency import ConsistencyAnalyzer
from .hierarchy import HierarchyAnalyzer


@dataclass
class CritiqueItem:
    """Single critique item with evidence.

    Each critique represents a design issue with supporting
    evidence from static analysis, runtime capture, or visual
    clustering.
    """

    id: str
    category: str  # "consistency" | "hierarchy" | "affordance"
    subcategory: str  # e.g., "token_adherence", "heading_scale", "focus_visibility"
    severity: Severity
    title: str
    description: str
    evidence: list[Evidence] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    affected_elements: list[RuntimeElementFingerprint] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    remediation_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "category": self.category,
            "subcategory": self.subcategory,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "evidence": [e.to_dict() for e in self.evidence],
            "screenshots": self.screenshots,
            "affected_elements": [e.to_dict() for e in self.affected_elements],
            "metrics": self.metrics,
            "remediation_hints": self.remediation_hints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CritiqueItem":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            category=data["category"],
            subcategory=data["subcategory"],
            severity=Severity(data["severity"]),
            title=data["title"],
            description=data["description"],
            evidence=[Evidence.from_dict(e) for e in data.get("evidence", [])],
            screenshots=data.get("screenshots", []),
            affected_elements=[
                RuntimeElementFingerprint.from_dict(e)
                for e in data.get("affected_elements", [])
            ],
            metrics=data.get("metrics", {}),
            remediation_hints=data.get("remediation_hints", []),
        )


@dataclass
class CritiqueSummary:
    """Summary statistics for a critique report."""

    total_critiques: int = 0
    by_category: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    token_adherence_rate: float = 1.0
    role_variant_counts: dict[str, int] = field(default_factory=dict)
    accessibility_issues: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_critiques": self.total_critiques,
            "by_category": self.by_category,
            "by_severity": self.by_severity,
            "token_adherence_rate": self.token_adherence_rate,
            "role_variant_counts": self.role_variant_counts,
            "accessibility_issues": self.accessibility_issues,
        }


@dataclass
class CritiqueStatistics:
    """Detailed statistics from critique analysis."""

    elements_analyzed: int = 0
    pages_crawled: int = 0
    visual_clusters_found: int = 0
    analysis_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "elements_analyzed": self.elements_analyzed,
            "pages_crawled": self.pages_crawled,
            "visual_clusters_found": self.visual_clusters_found,
            "analysis_time_ms": self.analysis_time_ms,
        }


@dataclass
class CritiqueReport:
    """Complete critique report with all analysis results."""

    critiques: list[CritiqueItem] = field(default_factory=list)
    summary: CritiqueSummary = field(default_factory=CritiqueSummary)
    statistics: CritiqueStatistics = field(default_factory=CritiqueStatistics)
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "critiques": [c.to_dict() for c in self.critiques],
            "summary": self.summary.to_dict(),
            "statistics": self.statistics.to_dict(),
            "generated_at": self.generated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CritiqueReport":
        """Create from dictionary."""
        return cls(
            critiques=[CritiqueItem.from_dict(c) for c in data.get("critiques", [])],
            summary=CritiqueSummary(**data.get("summary", {})),
            statistics=CritiqueStatistics(**data.get("statistics", {})),
            generated_at=data.get("generated_at", datetime.now().isoformat()),
        )

    @property
    def fail_count(self) -> int:
        """Count of FAIL severity critiques."""
        return sum(1 for c in self.critiques if c.severity == Severity.FAIL)

    @property
    def warn_count(self) -> int:
        """Count of WARN severity critiques."""
        return sum(1 for c in self.critiques if c.severity == Severity.WARN)

    @property
    def info_count(self) -> int:
        """Count of INFO severity critiques."""
        return sum(1 for c in self.critiques if c.severity == Severity.INFO)

    def get_critiques_by_category(self, category: str) -> list[CritiqueItem]:
        """Get critiques filtered by category."""
        return [c for c in self.critiques if c.category == category]

    def get_critiques_by_severity(self, severity: Severity) -> list[CritiqueItem]:
        """Get critiques filtered by severity."""
        return [c for c in self.critiques if c.severity == severity]


class CritiqueEngine:
    """Generates evidence-backed design critiques.

    Coordinates consistency, hierarchy, and affordance analyzers
    to produce comprehensive UI design critiques grounded in
    runtime data and evidence.
    """

    # Category-specific remediation hints
    REMEDIATION_HINTS = {
        "token_adherence": [
            "Replace hardcoded values with design tokens",
            "Add missing values to your design system scale",
            "Use CSS custom properties for consistency",
        ],
        "role_variants": [
            "Consolidate similar variants into a shared component",
            "Add variant prop to existing component",
            "Document intentional variants in design system",
        ],
        "outlier": [
            "Align outlier styles with majority pattern",
            "Document intentional deviation if needed",
        ],
        "heading_scale": [
            "Use a consistent typographic scale (e.g., 1.25 ratio)",
            "Define heading sizes in design tokens",
        ],
        "contrast": [
            "Increase text color contrast to meet WCAG 4.5:1",
            "Use darker text or lighter backgrounds",
            "Check contrast with WebAIM contrast checker",
        ],
        "spacing_rhythm": [
            "Use spacing values from design scale (4, 8, 12, 16, 24...)",
            "Add missing spacing values to scale if intentional",
        ],
        "focus_visibility": [
            "Add visible focus ring using outline or box-shadow",
            "Ensure focus indicator has 3:1 contrast ratio",
            "Test with keyboard navigation",
        ],
        "tap_targets": [
            "Increase element size to minimum 44x44px",
            "Add padding to improve touch area",
        ],
        "form_labels": [
            "Add explicit <label> elements with for attribute",
            "Use aria-label for icon-only inputs",
            "Never rely solely on placeholder text",
        ],
        "feedback_states": [
            "Add disabled state styling (opacity, cursor)",
            "Include loading indicators for async actions",
            "Show clear error states with messages",
        ],
    }

    def __init__(
        self,
        config: "UIQualityConfig",
        similarity_engine: "SimilarityEngine | None" = None,
    ):
        """Initialize the critique engine.

        Args:
            config: UI quality configuration.
            similarity_engine: Optional similarity engine for component matching.
        """
        self.config = config
        self.similarity_engine = similarity_engine

        # Initialize analyzers
        self.consistency_analyzer = ConsistencyAnalyzer(config)
        self.hierarchy_analyzer = HierarchyAnalyzer(config)
        self.affordance_analyzer = AffordanceAnalyzer(config)

        self._critique_counter = 0

    def _generate_critique_id(self, category: str, subcategory: str) -> str:
        """Generate unique critique ID."""
        self._critique_counter += 1
        return f"{category.upper()}-{subcategory.upper()}-{self._critique_counter:04d}"

    def _raw_to_critique_item(self, raw: dict[str, Any]) -> CritiqueItem:
        """Convert raw critique dict to CritiqueItem.

        Args:
            raw: Raw critique dictionary from analyzer.

        Returns:
            CritiqueItem with proper structure.
        """
        category = raw["category"]
        subcategory = raw["subcategory"]

        # Build evidence list from raw evidence
        evidence_list: list[Evidence] = []
        for ev in raw.get("evidence", []):
            evidence_list.append(Evidence(
                evidence_type=EvidenceType.RUNTIME,
                description=str(ev),
                data=ev if isinstance(ev, dict) else {"value": ev},
            ))

        # Get remediation hints for subcategory
        hints = self.REMEDIATION_HINTS.get(subcategory, [])

        return CritiqueItem(
            id=self._generate_critique_id(category, subcategory),
            category=category,
            subcategory=subcategory,
            severity=raw["severity"],
            title=raw["title"],
            description=raw["description"],
            evidence=evidence_list,
            screenshots=raw.get("screenshots", []),
            metrics=raw.get("metrics", {}),
            remediation_hints=hints,
        )

    def _build_summary(
        self,
        critiques: list[CritiqueItem],
        consistency_metrics: dict[str, Any] | None = None,
    ) -> CritiqueSummary:
        """Build summary statistics from critiques.

        Args:
            critiques: List of critique items.
            consistency_metrics: Optional consistency metrics for summary.

        Returns:
            CritiqueSummary with aggregated statistics.
        """
        summary = CritiqueSummary(total_critiques=len(critiques))

        # Count by category
        for critique in critiques:
            if critique.category not in summary.by_category:
                summary.by_category[critique.category] = 0
            summary.by_category[critique.category] += 1

            if critique.severity.value not in summary.by_severity:
                summary.by_severity[critique.severity.value] = 0
            summary.by_severity[critique.severity.value] += 1

            # Count accessibility issues
            if critique.category == "affordance":
                summary.accessibility_issues += 1

        # Add consistency metrics
        if consistency_metrics:
            summary.token_adherence_rate = consistency_metrics.get(
                "token_adherence_rate", 1.0
            )
            summary.role_variant_counts = consistency_metrics.get(
                "role_variants", {}
            )

        return summary

    def generate_critique(
        self,
        runtime_fingerprints: list[RuntimeElementFingerprint],
        crawl_results: list["CrawlResult"] | None = None,
        ci_result: "CIAuditResult | None" = None,
        visual_clusters: "VisualClusteringResult | None" = None,
        pseudo_states: list["PseudoStateCapture"] | None = None,
    ) -> CritiqueReport:
        """Generate comprehensive design critique.

        Runs all analyzers and aggregates results into a complete
        critique report with evidence and remediation hints.

        Args:
            runtime_fingerprints: Element fingerprints from Playwright crawl.
            crawl_results: Optional crawl results for screenshot paths.
            ci_result: Optional CI audit result for static analysis context.
            visual_clusters: Optional visual clustering results.
            pseudo_states: Optional pseudo-state captures.

        Returns:
            CritiqueReport with all critiques and summary.
        """
        import time
        start_time = time.time()

        self._critique_counter = 0  # Reset counter
        all_critiques: list[CritiqueItem] = []
        consistency_metrics: dict[str, Any] = {}

        # 1. Run consistency analysis
        consistency_raws = self.consistency_analyzer.generate_consistency_critiques(
            runtime_fingerprints,
            crawl_results,
            visual_clusters,
        )
        for raw in consistency_raws:
            all_critiques.append(self._raw_to_critique_item(raw))
            # Extract metrics for summary
            if "token_adherence" in raw.get("subcategory", ""):
                metrics = raw.get("metrics", {})
                consistency_metrics["token_adherence_rate"] = metrics.get(
                    "adherence_rate", 1.0
                )
            if "role_variants" in raw.get("subcategory", ""):
                metrics = raw.get("metrics", {})
                role = metrics.get("role", "unknown")
                consistency_metrics.setdefault("role_variants", {})[role] = metrics.get(
                    "variant_count", 0
                )

        # 2. Run hierarchy analysis
        hierarchy_raws = self.hierarchy_analyzer.generate_hierarchy_critiques(
            runtime_fingerprints,
            crawl_results,
        )
        for raw in hierarchy_raws:
            all_critiques.append(self._raw_to_critique_item(raw))

        # 3. Run affordance analysis
        affordance_raws = self.affordance_analyzer.generate_affordance_critiques(
            runtime_fingerprints,
            crawl_results,
            pseudo_states,
        )
        for raw in affordance_raws:
            all_critiques.append(self._raw_to_critique_item(raw))

        # 4. Add CI audit findings as additional evidence (if available)
        if ci_result:
            for finding in ci_result.new_findings[:5]:  # Limit to top 5
                # Map CI findings to critique items
                category = "consistency"
                subcategory = "static_analysis"
                if "ROLE" in finding.rule_id:
                    subcategory = "role_variants"
                elif "TOKEN" in finding.rule_id or "SCALE" in finding.rule_id:
                    subcategory = "token_adherence"

                all_critiques.append(CritiqueItem(
                    id=self._generate_critique_id(category, subcategory),
                    category=category,
                    subcategory=subcategory,
                    severity=finding.severity,
                    title=f"Static Analysis: {finding.rule_id}",
                    description=finding.summary,
                    evidence=[
                        Evidence(
                            evidence_type=EvidenceType.STATIC,
                            description=f"From static analysis: {finding.rule_id}",
                            source_ref=finding.source_ref,
                        )
                    ],
                    remediation_hints=finding.remediation_hints,
                ))

        # Sort critiques by severity (FAIL first, then WARN, then INFO)
        severity_order = {Severity.FAIL: 0, Severity.WARN: 1, Severity.INFO: 2}
        all_critiques.sort(key=lambda c: severity_order.get(c.severity, 3))

        # Build summary
        summary = self._build_summary(all_critiques, consistency_metrics)

        # Build statistics
        statistics = CritiqueStatistics(
            elements_analyzed=len(runtime_fingerprints),
            pages_crawled=len(crawl_results) if crawl_results else 0,
            visual_clusters_found=(
                len(visual_clusters.clusters) if visual_clusters else 0
            ),
            analysis_time_ms=(time.time() - start_time) * 1000,
        )

        return CritiqueReport(
            critiques=all_critiques,
            summary=summary,
            statistics=statistics,
        )


__all__ = [
    "CritiqueEngine",
    "CritiqueItem",
    "CritiqueReport",
    "CritiqueSummary",
    "CritiqueStatistics",
]
