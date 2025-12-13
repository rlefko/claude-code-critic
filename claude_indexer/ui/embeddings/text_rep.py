"""Text representation generator for UI component embeddings.

This module generates text representations of UI components suitable
for embedding and semantic similarity search.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import StaticComponentFingerprint, StyleFingerprint


class UITextRepresentationGenerator:
    """Generates text representations for UI component embedding.

    Creates structured text strings that capture the semantic meaning
    of components for use with embedding models.
    """

    def __init__(
        self,
        include_props: bool = True,
        include_structure: bool = True,
        include_style_refs: bool = True,
        include_design_tokens: bool = True,
        max_style_refs: int = 20,
        max_tokens: int = 20,
    ):
        """Initialize the generator.

        Args:
            include_props: Whether to include prop names.
            include_structure: Whether to include structure tokens.
            include_style_refs: Whether to include style references.
            include_design_tokens: Whether to include design token names.
            max_style_refs: Maximum style refs to include.
            max_tokens: Maximum design tokens to include.
        """
        self.include_props = include_props
        self.include_structure = include_structure
        self.include_style_refs = include_style_refs
        self.include_design_tokens = include_design_tokens
        self.max_style_refs = max_style_refs
        self.max_tokens = max_tokens

    def generate_component_text(
        self,
        fingerprint: "StaticComponentFingerprint",
        component_name: str | None = None,
    ) -> str:
        """Generate text representation for a component.

        Creates a structured text string that captures:
        - Component name
        - Prop names (if available)
        - Structural tokens from render tree
        - Style references (classes, CSS modules)
        - Design tokens used

        Args:
            fingerprint: Component fingerprint.
            component_name: Optional component name.

        Returns:
            Text representation suitable for embedding.
        """
        parts = []

        # Component name
        name = component_name
        if not name and fingerprint.source_ref:
            name = fingerprint.source_ref.name
        if name:
            parts.append(f"Component: {name}")

        # Props
        if self.include_props and fingerprint.prop_shape_sketch:
            prop_names = list(fingerprint.prop_shape_sketch.keys())
            if prop_names:
                parts.append(f"Props: {', '.join(prop_names)}")

        # Structure tokens
        if self.include_structure and fingerprint.structure_hash:
            structure_tokens = self._extract_structure_tokens(
                fingerprint.structure_hash
            )
            if structure_tokens:
                parts.append(f"Structure: {' '.join(structure_tokens)}")

        # Style refs
        if self.include_style_refs and fingerprint.style_refs:
            refs = fingerprint.style_refs[: self.max_style_refs]
            # Clean up refs (remove hashes, normalize)
            clean_refs = [self._clean_style_ref(r) for r in refs]
            clean_refs = [r for r in clean_refs if r]
            if clean_refs:
                parts.append(f"Styles: {', '.join(clean_refs)}")

        # Build final text
        return "\n".join(parts) if parts else "Empty component"

    def generate_style_text(
        self,
        fingerprint: "StyleFingerprint",
        selector: str | None = None,
    ) -> str:
        """Generate text representation for a style block.

        Creates a structured text string that captures:
        - Selector (if available)
        - Property names
        - Token references
        - Key values

        Args:
            fingerprint: Style fingerprint.
            selector: Optional CSS selector.

        Returns:
            Text representation suitable for embedding.
        """
        parts = []

        # Selector
        if selector:
            parts.append(f"Selector: {selector}")

        # Properties
        if fingerprint.declaration_set:
            props = list(fingerprint.declaration_set.keys())
            parts.append(f"Properties: {', '.join(props)}")

            # Include some key values
            key_values = self._extract_key_values(fingerprint.declaration_set)
            if key_values:
                parts.append(f"Values: {', '.join(key_values)}")

        # Tokens used
        if self.include_design_tokens and fingerprint.tokens_used:
            tokens = fingerprint.tokens_used[: self.max_tokens]
            parts.append(f"Tokens: {', '.join(tokens)}")

        return "\n".join(parts) if parts else "Empty style"

    def generate_batch(
        self,
        fingerprints: list["StaticComponentFingerprint"],
        names: list[str | None] | None = None,
    ) -> list[str]:
        """Generate text representations for multiple components.

        Args:
            fingerprints: List of component fingerprints.
            names: Optional list of component names.

        Returns:
            List of text representations.
        """
        if names is None:
            names = [None] * len(fingerprints)

        return [
            self.generate_component_text(fp, name)
            for fp, name in zip(fingerprints, names, strict=False)
        ]

    def _extract_structure_tokens(self, structure_hash: str) -> list[str]:
        """Extract meaningful tokens from structure representation.

        Attempts to parse common structure patterns to extract
        element and component names.

        Args:
            structure_hash: Structure hash or representation.

        Returns:
            List of meaningful tokens.
        """
        # If it's a hex hash, return a truncated version
        if all(c in "0123456789abcdef" for c in structure_hash.lower()):
            return [structure_hash[:8]]

        # Try to extract element names from common patterns
        tokens = []

        # Common JSX/HTML element patterns
        import re

        # Match tag names: <div>, <Button>, etc.
        tag_matches = re.findall(r"<([A-Za-z][A-Za-z0-9]*)", structure_hash)
        tokens.extend(tag_matches)

        # Match component references
        comp_matches = re.findall(r"\b([A-Z][a-z0-9]+[A-Za-z0-9]*)\b", structure_hash)
        tokens.extend(comp_matches)

        return list(set(tokens))[:10]  # Dedupe and limit

    def _clean_style_ref(self, ref: str) -> str:
        """Clean a style reference for text representation.

        Removes hash suffixes, normalizes case.

        Args:
            ref: Style reference string.

        Returns:
            Cleaned reference.
        """
        import re

        # Remove CSS module hash suffixes (e.g., _abc123)
        cleaned = re.sub(r"_[a-f0-9]{6,}$", "", ref)

        # Remove leading dots for class names
        cleaned = cleaned.lstrip(".")

        return cleaned

    def _extract_key_values(
        self,
        declarations: dict[str, str],
        max_values: int = 5,
    ) -> list[str]:
        """Extract key values from declarations.

        Focuses on important properties like colors, spacing.

        Args:
            declarations: CSS declarations.
            max_values: Maximum values to extract.

        Returns:
            List of key values.
        """
        key_props = [
            "color",
            "background-color",
            "padding",
            "margin",
            "border-radius",
            "font-size",
            "display",
        ]

        values = []
        for prop in key_props:
            if prop in declarations:
                value = declarations[prop]
                # Skip inherit/initial
                if value not in ("inherit", "initial", "unset"):
                    values.append(f"{prop}:{value}")

        return values[:max_values]


def generate_component_text(
    fingerprint: "StaticComponentFingerprint",
    name: str | None = None,
) -> str:
    """Convenience function to generate component text.

    Args:
        fingerprint: Component fingerprint.
        name: Optional component name.

    Returns:
        Text representation.
    """
    generator = UITextRepresentationGenerator()
    return generator.generate_component_text(fingerprint, name)


def generate_style_text(
    fingerprint: "StyleFingerprint",
    selector: str | None = None,
) -> str:
    """Convenience function to generate style text.

    Args:
        fingerprint: Style fingerprint.
        selector: Optional CSS selector.

    Returns:
        Text representation.
    """
    generator = UITextRepresentationGenerator()
    return generator.generate_style_text(fingerprint, selector)


__all__ = [
    "UITextRepresentationGenerator",
    "generate_component_text",
    "generate_style_text",
]
