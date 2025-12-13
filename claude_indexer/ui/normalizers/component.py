"""Component normalizer for duplicate component detection.

This module provides functionality to normalize UI component structures
for accurate comparison and duplicate detection. It creates stable
render-tree skeletons that can be compared across framework variations.
"""

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from .hashing import compute_simhash, jaccard_similarity


@dataclass
class NormalizedComponent:
    """Normalized component structure for comparison.

    Contains a structural skeleton and hashes for finding duplicate
    or similar components.
    """

    structure: str  # Normalized template skeleton
    structure_hash: str  # SHA256 of structure
    tag_sequence: list[str] = field(default_factory=list)  # Ordered tags
    attribute_keys: set[str] = field(default_factory=set)  # Attribute names used
    style_refs: list[str] = field(default_factory=list)  # Class names, CSS modules
    prop_names: list[str] = field(default_factory=list)  # Component props

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "structure": self.structure,
            "structure_hash": self.structure_hash,
            "tag_sequence": self.tag_sequence,
            "attribute_keys": list(self.attribute_keys),
            "style_refs": self.style_refs,
            "prop_names": self.prop_names,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NormalizedComponent":
        """Create from dictionary."""
        return cls(
            structure=data["structure"],
            structure_hash=data["structure_hash"],
            tag_sequence=data.get("tag_sequence", []),
            attribute_keys=set(data.get("attribute_keys", [])),
            style_refs=data.get("style_refs", []),
            prop_names=data.get("prop_names", []),
        )

    def is_exact_duplicate(self, other: "NormalizedComponent") -> bool:
        """Check if this component is an exact structural duplicate."""
        return self.structure_hash == other.structure_hash


class ComponentNormalizer:
    """Normalizes UI component structures for comparison.

    Creates stable template skeletons by:
    - Preserving element/component tags
    - Replacing literal values with placeholders
    - Normalizing class ordering
    - Extracting structural information for hashing
    """

    # Placeholder tokens for literal replacement
    TEXT_PLACEHOLDER = "{TEXT}"
    NUMBER_PLACEHOLDER = "{NUM}"
    STRING_PLACEHOLDER = "{STR}"
    EXPR_PLACEHOLDER = "{EXPR}"

    # Framework-specific expression patterns
    EXPRESSION_PATTERNS = {
        # React/JSX expressions
        "react": r"\{[^}]+\}",
        # Vue template expressions
        "vue": r"\{\{[^}]+\}\}|:[a-z-]+=\"[^\"]+\"|v-[a-z-]+(?:=\"[^\"]+\")?",
        # Svelte expressions
        "svelte": r"\{[^}]+\}|on:[a-z]+(?:=\"[^\"]+\")?",
        # Generic
        "unknown": r"\{[^}]+\}",
    }

    def __init__(self):
        """Initialize the component normalizer."""
        pass

    def normalize(
        self,
        template: str,
        props: dict[str, Any] | None = None,
        framework: str = "unknown",
    ) -> NormalizedComponent:
        """Normalize component template for comparison.

        Args:
            template: The component template/JSX source.
            props: Optional dictionary of component props.
            framework: Framework hint ('react', 'vue', 'svelte', 'unknown').

        Returns:
            NormalizedComponent with structure and hashes.
        """
        # Step 1: Replace expressions with placeholders
        normalized = self._replace_expressions(template, framework)

        # Step 2: Replace literals with placeholders
        normalized = self._replace_literals(normalized)

        # Step 3: Normalize class order in attributes
        normalized = self._normalize_class_order(normalized)

        # Step 4: Extract structure (tag hierarchy)
        structure = self._extract_structure(normalized)

        # Step 5: Extract tag sequence
        tag_sequence = self._extract_tag_sequence(template)

        # Step 6: Extract attribute keys
        attribute_keys = self._extract_attribute_keys(template)

        # Step 7: Extract style references
        style_refs = self._extract_style_refs(template)

        # Step 8: Compute structure hash
        structure_hash = hashlib.sha256(structure.encode()).hexdigest()

        return NormalizedComponent(
            structure=structure,
            structure_hash=structure_hash,
            tag_sequence=tag_sequence,
            attribute_keys=attribute_keys,
            style_refs=style_refs,
            prop_names=list(props.keys()) if props else [],
        )

    def _replace_expressions(self, template: str, framework: str) -> str:
        """Replace framework-specific expressions with placeholders.

        Args:
            template: Original template string.
            framework: Framework name for pattern selection.

        Returns:
            Template with expressions replaced.
        """
        pattern = self.EXPRESSION_PATTERNS.get(
            framework, self.EXPRESSION_PATTERNS["unknown"]
        )
        return re.sub(pattern, self.EXPR_PLACEHOLDER, template)

    def _replace_literals(self, template: str) -> str:
        """Replace literal values with placeholders.

        Replaces string literals, numbers, and text content with
        placeholders to focus on structure rather than content.

        Args:
            template: Template string (possibly with expressions already replaced).

        Returns:
            Template with literals replaced.
        """
        result = template

        # Replace quoted string literals (careful to preserve attribute names)
        # Match attribute values: name="value" or name='value'
        result = re.sub(
            r'(\s\w+)=("[^"]*"|\'[^\']*\')',
            r"\1=" + f'"{self.STRING_PLACEHOLDER}"',
            result,
        )

        # Replace standalone numbers
        result = re.sub(r"\b\d+\.?\d*\b", self.NUMBER_PLACEHOLDER, result)

        # Replace text content between tags
        # This regex matches content between > and <, being careful with whitespace
        result = re.sub(
            r">([^<]+)<",
            lambda m: f">{self.TEXT_PLACEHOLDER}<" if m.group(1).strip() else "><",
            result,
        )

        return result

    def _normalize_class_order(self, template: str) -> str:
        """Sort class names in class/className attributes.

        Ensures consistent ordering for comparison regardless of
        how classes are written in the source.

        Args:
            template: Template string.

        Returns:
            Template with sorted class names.
        """

        def sort_classes(match: re.Match) -> str:
            attr_name = match.group(1)
            quote = match.group(2)
            classes = match.group(3)
            sorted_classes = " ".join(sorted(classes.split()))
            return f"{attr_name}={quote}{sorted_classes}{quote}"

        # Handle class="..." and className="..."
        result = re.sub(
            r'(class(?:Name)?)\s*=\s*(["\'])([^"\']+)\2',
            sort_classes,
            template,
        )
        return result

    def _extract_structure(self, template: str) -> str:
        """Extract structural skeleton (tags without content/values).

        Creates a normalized representation that captures the DOM structure
        without specific values.

        Args:
            template: Normalized template string.

        Returns:
            Structural skeleton string.
        """
        # Remove text content placeholders
        structure = re.sub(r">\s*\{TEXT\}\s*<", "><", template)

        # Normalize whitespace
        structure = re.sub(r"\s+", " ", structure)

        # Remove attribute values, keep attribute names
        # This removes ="..." while keeping the attribute name
        structure = re.sub(r'(\s\w+)=["\'][^"\']*["\']', r"\1", structure)

        # Remove expression placeholders in attributes
        structure = re.sub(r"(\s\w+)=\{EXPR\}", r"\1", structure)

        return structure.strip()

    def _extract_tag_sequence(self, template: str) -> list[str]:
        """Extract ordered list of element tags.

        Args:
            template: Original template string.

        Returns:
            List of tag names in order of appearance.
        """
        # Match opening tags (including self-closing)
        tags = re.findall(r"<([A-Za-z][A-Za-z0-9]*)", template)
        return tags

    def _extract_attribute_keys(self, template: str) -> set[str]:
        """Extract all attribute names used in the template.

        Args:
            template: Original template string.

        Returns:
            Set of attribute names.
        """
        # Match attribute names before =
        attrs = re.findall(r"\s([a-zA-Z][a-zA-Z0-9_-]*)\s*=", template)
        return set(attrs)

    def _extract_style_refs(self, template: str) -> list[str]:
        """Extract class names and CSS module references.

        Args:
            template: Original template string.

        Returns:
            Deduplicated list of style references.
        """
        refs = []

        # Extract from class/className string values
        class_matches = re.findall(
            r'class(?:Name)?\s*=\s*["\']([^"\']+)["\']', template
        )
        for match in class_matches:
            refs.extend(match.split())

        # Extract CSS module references (styles.xxx or styles["xxx"])
        module_refs = re.findall(r"styles\.([a-zA-Z_][a-zA-Z0-9_]*)", template)
        refs.extend(module_refs)

        # Extract bracket notation styles["className"]
        bracket_refs = re.findall(r'styles\[["\']([\w-]+)["\']\]', template)
        refs.extend(bracket_refs)

        # Deduplicate while preserving order
        seen = set()
        unique_refs = []
        for ref in refs:
            if ref not in seen:
                seen.add(ref)
                unique_refs.append(ref)

        return unique_refs

    def compute_similarity(
        self,
        comp1: NormalizedComponent,
        comp2: NormalizedComponent,
    ) -> float:
        """Compute structural similarity between two components.

        Uses a combination of:
        - Tag sequence similarity (Jaccard)
        - Attribute similarity (Jaccard)
        - Style reference similarity (Jaccard)

        Args:
            comp1: First normalized component.
            comp2: Second normalized component.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        if comp1.structure_hash == comp2.structure_hash:
            return 1.0

        # Compute individual similarities
        tag_sim = jaccard_similarity(set(comp1.tag_sequence), set(comp2.tag_sequence))
        attr_sim = jaccard_similarity(comp1.attribute_keys, comp2.attribute_keys)
        style_sim = jaccard_similarity(set(comp1.style_refs), set(comp2.style_refs))

        # Weighted combination: structure > styles > attributes
        return 0.5 * tag_sim + 0.3 * style_sim + 0.2 * attr_sim

    def compute_simhash_similarity(
        self,
        comp1: NormalizedComponent,
        comp2: NormalizedComponent,
    ) -> float:
        """Compute SimHash-based similarity between components.

        Uses the structure string to compute SimHash similarity.

        Args:
            comp1: First normalized component.
            comp2: Second normalized component.

        Returns:
            Similarity score between 0.0 and 1.0.
        """
        from .hashing import simhash_similarity

        # Create feature sets from structure
        features1 = self._structure_to_features(comp1.structure)
        features2 = self._structure_to_features(comp2.structure)

        hash1 = compute_simhash(features1)
        hash2 = compute_simhash(features2)

        return simhash_similarity(hash1, hash2)

    def _structure_to_features(self, structure: str) -> list[str]:
        """Convert structure to feature list for SimHash.

        Args:
            structure: Structural skeleton string.

        Returns:
            List of feature strings.
        """
        features = []

        # Add individual tags as features
        tags = re.findall(r"<([A-Za-z][A-Za-z0-9]*)", structure)
        features.extend(f"tag:{t}" for t in tags)

        # Add tag pairs (parent-child relationships)
        for i in range(len(tags) - 1):
            features.append(f"pair:{tags[i]}-{tags[i+1]}")

        # Add attribute names as features
        attrs = re.findall(r"\s([a-zA-Z][a-zA-Z0-9_-]*)", structure)
        features.extend(f"attr:{a}" for a in attrs)

        return features

    def are_near_duplicates(
        self,
        comp1: NormalizedComponent,
        comp2: NormalizedComponent,
        threshold: float = 0.85,
    ) -> bool:
        """Check if two components are near-duplicates.

        Args:
            comp1: First normalized component.
            comp2: Second normalized component.
            threshold: Similarity threshold for near-duplicate.

        Returns:
            True if components are near-duplicates.
        """
        if comp1.structure_hash == comp2.structure_hash:
            return True
        return self.compute_similarity(comp1, comp2) >= threshold

    def find_duplicates(
        self,
        components: list[NormalizedComponent],
    ) -> list[tuple[int, int]]:
        """Find exact duplicate pairs in a list of components.

        Args:
            components: List of normalized components.

        Returns:
            List of (index1, index2) pairs that are exact duplicates.
        """
        duplicates = []
        seen: dict[str, int] = {}

        for i, comp in enumerate(components):
            if comp.structure_hash in seen:
                duplicates.append((seen[comp.structure_hash], i))
            else:
                seen[comp.structure_hash] = i

        return duplicates

    def find_near_duplicates(
        self,
        components: list[NormalizedComponent],
        threshold: float = 0.85,
    ) -> list[tuple[int, int, float]]:
        """Find near-duplicate pairs in a list of components.

        Args:
            components: List of normalized components.
            threshold: Similarity threshold for near-duplicate.

        Returns:
            List of (index1, index2, similarity) tuples.
        """
        near_duplicates = []

        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                # Skip exact duplicates
                if components[i].structure_hash == components[j].structure_hash:
                    continue

                similarity = self.compute_similarity(components[i], components[j])
                if similarity >= threshold:
                    near_duplicates.append((i, j, similarity))

        return near_duplicates
