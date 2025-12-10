"""Token adapters for extracting design tokens from various sources.

This package provides adapters for different token file formats:
- CSS Variables (css_vars.py)
- Tailwind CSS config (tailwind.py)
- JSON token files (json_tokens.py)
"""

from .base import TokenAdapter, TokenAdapterRegistry, get_default_registry
from .css_vars import CSSVariablesAdapter
from .json_tokens import JSONTokenAdapter
from .tailwind import TailwindConfigAdapter

__all__ = [
    "TokenAdapter",
    "TokenAdapterRegistry",
    "get_default_registry",
    "CSSVariablesAdapter",
    "TailwindConfigAdapter",
    "JSONTokenAdapter",
]
