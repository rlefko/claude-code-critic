"""Duplication rules for UI consistency checking.

This module provides rules that detect duplicate and near-duplicate
styles and components that could be consolidated.
"""

import re
from collections import Counter
from typing import TYPE_CHECKING

from ..models import Finding, Severity, SymbolRef
from ..normalizers.style import StyleNormalizer
from .base import BaseRule, RuleContext

if TYPE_CHECKING:
    pass


class StyleDuplicateSetRule(BaseRule):
    """Detects exact duplicate style blocks across files.

    Finds styles with identical normalized declarations that
    could be consolidated into a shared definition.
    """

    @property
    def rule_id(self) -> str:
        return "STYLE.DUPLICATE_SET"

    @property
    def category(self) -> str:
        return "duplication"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def is_fast(self) -> bool:
        return False  # Requires cross-file comparison

    @property
    def description(self) -> str:
        return "Detects exact duplicate style blocks"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find exact duplicate styles by hash."""
        if len(context.styles) < 2:
            return []

        findings = []
        normalizer = StyleNormalizer()

        # Normalize all styles and group by exact hash
        hash_groups: dict[str, list[tuple[int, any]]] = {}

        for i, style in enumerate(context.styles):
            if not hasattr(style, "declaration_set"):
                continue

            normalized = normalizer.normalize(style.declaration_set)

            if normalized.exact_hash not in hash_groups:
                hash_groups[normalized.exact_hash] = []
            hash_groups[normalized.exact_hash].append((i, style))

        # Report groups with duplicates
        for hash_val, group in hash_groups.items():
            if len(group) < 2:
                continue

            # Get source refs for all duplicates
            source_refs = []
            for _idx, style in group:
                if hasattr(style, "source_refs") and style.source_refs:
                    source_refs.extend(style.source_refs)

            if not source_refs:
                continue

            # Create evidence for each location
            evidence = []
            for ref in source_refs[:5]:  # Limit evidence
                evidence.append(
                    self._create_static_evidence(
                        description=f"Duplicate style at {ref}",
                        source_ref=ref,
                        data={"hash": hash_val[:16]},
                    )
                )

            # Build remediation hints
            files = list({ref.file_path for ref in source_refs})
            hints = [
                f"Consolidate {len(group)} identical style blocks into a shared class",
                f"Found in files: {', '.join(files[:3])}",
            ]

            findings.append(
                self._create_finding(
                    summary=f"Found {len(group)} exact duplicate style blocks",
                    evidence=evidence,
                    config=context.config,
                    source_ref=source_refs[0] if source_refs else None,
                    confidence=1.0,  # Exact duplicates have high confidence
                    remediation_hints=hints,
                )
            )

        return findings


class StyleNearDuplicateSetRule(BaseRule):
    """Detects near-duplicate style blocks.

    Finds styles that differ by only 1-2 properties and could
    potentially be unified with variants.
    """

    @property
    def rule_id(self) -> str:
        return "STYLE.NEAR_DUPLICATE_SET"

    @property
    def category(self) -> str:
        return "duplication"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def is_fast(self) -> bool:
        return False

    @property
    def description(self) -> str:
        return "Detects near-duplicate style blocks"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find near-duplicate styles using SimHash."""
        if len(context.styles) < 2:
            return []

        findings = []
        normalizer = StyleNormalizer()
        threshold = context.config.gating.similarity_thresholds.near_duplicate

        # Normalize all styles
        normalized_styles = []
        for style in context.styles:
            if hasattr(style, "declaration_set"):
                normalized = normalizer.normalize(style.declaration_set)
                normalized_styles.append((style, normalized))

        # Find near-duplicates
        near_dups = normalizer.find_near_duplicates(
            [n for _, n in normalized_styles],
            threshold=threshold,
        )

        # Group by reported pairs
        reported_pairs = set()

        for idx1, idx2, similarity in near_dups:
            # Skip if already reported
            pair_key = tuple(sorted([idx1, idx2]))
            if pair_key in reported_pairs:
                continue
            reported_pairs.add(pair_key)

            style1, norm1 = normalized_styles[idx1]
            style2, norm2 = normalized_styles[idx2]

            # Get source refs
            ref1 = None
            ref2 = None
            if hasattr(style1, "source_refs") and style1.source_refs:
                ref1 = style1.source_refs[0]
            if hasattr(style2, "source_refs") and style2.source_refs:
                ref2 = style2.source_refs[0]

            # Find differences
            diffs = self._find_declaration_diffs(norm1.declarations, norm2.declarations)

            evidence = [
                self._create_static_evidence(
                    description=f"Style block with {similarity:.0%} similarity",
                    source_ref=ref1,
                    data={"declarations": norm1.declarations},
                ),
                self._create_static_evidence(
                    description="Near-duplicate style block",
                    source_ref=ref2,
                    data={"declarations": norm2.declarations},
                ),
            ]

            hints = [
                f"These styles are {similarity:.0%} similar",
                f"Differences: {', '.join(diffs[:3])}",
                "Consider creating a base style with variants",
            ]

            findings.append(
                self._create_finding(
                    summary=f"Near-duplicate styles ({similarity:.0%} similar)",
                    evidence=evidence,
                    config=context.config,
                    source_ref=ref1,
                    confidence=similarity,
                    remediation_hints=hints,
                )
            )

        return findings

    def _find_declaration_diffs(
        self,
        decl1: dict[str, str],
        decl2: dict[str, str],
    ) -> list[str]:
        """Find differences between two declaration sets."""
        diffs = []

        all_props = set(decl1.keys()) | set(decl2.keys())

        for prop in all_props:
            val1 = decl1.get(prop)
            val2 = decl2.get(prop)

            if val1 != val2:
                if val1 is None:
                    diffs.append(f"+{prop}")
                elif val2 is None:
                    diffs.append(f"-{prop}")
                else:
                    diffs.append(f"{prop}: {val1} vs {val2}")

        return diffs


class UtilityDuplicateSequenceRule(BaseRule):
    """Detects repeated sequences of utility classes.

    Finds common patterns like 'px-4 py-2 bg-white' that appear
    multiple times and could be extracted to a component or class.
    """

    @property
    def rule_id(self) -> str:
        return "UTILITY.DUPLICATE_SEQUENCE"

    @property
    def category(self) -> str:
        return "duplication"

    @property
    def default_severity(self) -> Severity:
        return Severity.INFO

    @property
    def description(self) -> str:
        return "Detects repeated utility class sequences"

    # Minimum sequence length to report
    MIN_SEQUENCE_LENGTH = 3
    # Minimum occurrences to report
    MIN_OCCURRENCES = 3

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find repeated utility class sequences."""
        findings = []

        # Extract class sequences from components
        sequences: list[tuple[str, SymbolRef | None]] = []

        for component in context.components:
            if not hasattr(component, "style_refs"):
                continue

            # Get class-like style refs
            classes = [
                ref for ref in component.style_refs if self._is_utility_class(ref)
            ]

            if len(classes) >= self.MIN_SEQUENCE_LENGTH:
                sequence = " ".join(sorted(classes))
                ref = component.source_ref if hasattr(component, "source_ref") else None
                sequences.append((sequence, ref))

        # Count occurrences
        sequence_counts = Counter(seq for seq, _ in sequences)

        # Report sequences that appear multiple times
        reported = set()
        for sequence, count in sequence_counts.items():
            if count < self.MIN_OCCURRENCES:
                continue
            if sequence in reported:
                continue
            reported.add(sequence)

            # Get source refs for this sequence
            refs = [ref for seq, ref in sequences if seq == sequence and ref]

            evidence = []
            for ref in refs[:3]:
                evidence.append(
                    self._create_static_evidence(
                        description=f"Utility sequence at {ref}",
                        source_ref=ref,
                        data={"classes": sequence.split()},
                    )
                )

            hints = [
                f"Found '{sequence}' repeated {count} times",
                "Consider extracting to a component or utility class",
            ]

            findings.append(
                self._create_finding(
                    summary=f"Utility class sequence repeated {count} times",
                    evidence=evidence,
                    config=context.config,
                    source_ref=refs[0] if refs else None,
                    confidence=min(0.9, 0.5 + count * 0.1),
                    remediation_hints=hints,
                )
            )

        return findings

    def _is_utility_class(self, class_name: str) -> bool:
        """Check if a class name looks like a utility class."""
        # Common utility class patterns (Tailwind-like)
        utility_patterns = [
            r"^(p|m|px|py|pt|pb|pl|pr|mx|my|mt|mb|ml|mr)-",
            r"^(w|h|min-w|min-h|max-w|max-h)-",
            r"^(bg|text|border|ring)-",
            r"^(flex|grid|block|inline|hidden)",
            r"^(rounded|shadow|opacity|z)-",
            r"^(font|text|leading|tracking)-",
            r"^(gap|space)-",
        ]

        return any(re.match(p, class_name) for p in utility_patterns)


class ComponentDuplicateClusterRule(BaseRule):
    """Detects clusters of similar components.

    Uses multi-signal similarity and clustering to find groups
    of components that could be consolidated.
    """

    @property
    def rule_id(self) -> str:
        return "COMPONENT.DUPLICATE_CLUSTER"

    @property
    def category(self) -> str:
        return "duplication"

    @property
    def default_severity(self) -> Severity:
        return Severity.WARN

    @property
    def is_fast(self) -> bool:
        return False  # Requires clustering

    @property
    def description(self) -> str:
        return "Detects clusters of similar components"

    def evaluate(self, context: RuleContext) -> list[Finding]:
        """Find component clusters using similarity engine."""
        if len(context.components) < 2:
            return []

        if context.similarity_engine is None:
            return []

        findings = []

        # Import clustering
        try:
            from ..similarity.clustering import SimilarityClustering

            clustering = SimilarityClustering(
                context.similarity_engine,
                min_cluster_size=2,
                eps=0.2,  # 0.8 similarity threshold
            )

            result = clustering.cluster_components(context.components)

            # Report meaningful clusters
            for cluster in result.clusters:
                if cluster.size < 2:
                    continue

                # Get components in cluster
                cluster_components = [
                    c
                    for c in context.components
                    if self._get_component_id(c) in cluster.items
                ]

                # Create evidence for each component
                evidence = []
                for comp in cluster_components[:4]:
                    ref = comp.source_ref if hasattr(comp, "source_ref") else None
                    evidence.append(
                        self._create_static_evidence(
                            description="Similar component",
                            source_ref=ref,
                            data={"structure_hash": comp.structure_hash[:16]},
                        )
                    )

                # Add semantic evidence about cluster
                evidence.append(
                    self._create_semantic_evidence(
                        description=f"Cluster of {cluster.size} similar components",
                        similarity_score=cluster.avg_internal_similarity,
                        data={
                            "cluster_id": cluster.cluster_id,
                            "representative": cluster.representative,
                        },
                    )
                )

                hints = [
                    f"Found {cluster.size} components with {cluster.avg_internal_similarity:.0%} avg similarity",
                    "Consider extracting a shared base component",
                    f"Representative: {cluster.representative}",
                ]

                # Get first component's source ref
                first_ref = None
                if cluster_components and hasattr(cluster_components[0], "source_ref"):
                    first_ref = cluster_components[0].source_ref

                findings.append(
                    self._create_finding(
                        summary=f"Found cluster of {cluster.size} similar components",
                        evidence=evidence,
                        config=context.config,
                        source_ref=first_ref,
                        confidence=cluster.avg_internal_similarity,
                        remediation_hints=hints,
                    )
                )

        except ImportError:
            pass

        return findings

    def _get_component_id(self, component) -> str:
        """Get component ID for matching."""
        if hasattr(component, "embedding_id") and component.embedding_id:
            return component.embedding_id
        if hasattr(component, "source_ref") and component.source_ref:
            return f"{component.source_ref.file_path}:{component.source_ref.start_line}"
        return component.structure_hash[:16]


__all__ = [
    "StyleDuplicateSetRule",
    "StyleNearDuplicateSetRule",
    "UtilityDuplicateSequenceRule",
    "ComponentDuplicateClusterRule",
]
