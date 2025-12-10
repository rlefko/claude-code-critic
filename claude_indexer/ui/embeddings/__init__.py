"""UI embeddings package.

This package provides text representation generation for
UI component and style embedding.
"""

from .text_rep import (
    UITextRepresentationGenerator,
    generate_component_text,
    generate_style_text,
)

__all__ = [
    "UITextRepresentationGenerator",
    "generate_component_text",
    "generate_style_text",
]
