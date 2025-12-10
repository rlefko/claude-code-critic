"""Base class for design token adapters.

Token adapters extract design tokens from various source formats
(CSS variables, Tailwind config, JSON token files) and convert them
to the unified TokenSet format.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from ..tokens import TokenSet


class TokenAdapter(ABC):
    """Abstract base class for design token adapters.

    Each adapter is responsible for extracting tokens from a specific
    file format and converting them to the unified TokenSet format.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle."""
        ...

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file.

        Args:
            file_path: Path to the token source file.

        Returns:
            True if this adapter can extract tokens from the file.
        """
        ...

    @abstractmethod
    def extract(self, file_path: Path) -> TokenSet:
        """Extract tokens from the given file.

        Args:
            file_path: Path to the token source file.

        Returns:
            TokenSet containing all extracted tokens.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file format is invalid.
        """
        ...

    def extract_from_content(self, content: str, source_name: str = "inline") -> TokenSet:
        """Extract tokens from content string (for testing or inline configs).

        Args:
            content: The content to parse.
            source_name: Name to use for source tracking.

        Returns:
            TokenSet containing all extracted tokens.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support content extraction"
        )


class TokenAdapterRegistry:
    """Registry for token adapters.

    Manages multiple adapters and selects the appropriate one
    based on file type.
    """

    def __init__(self) -> None:
        self._adapters: list[TokenAdapter] = []

    def register(self, adapter: TokenAdapter) -> None:
        """Register a token adapter."""
        self._adapters.append(adapter)

    def get_adapter(self, file_path: Path) -> TokenAdapter | None:
        """Get an adapter that can handle the given file.

        Args:
            file_path: Path to the token source file.

        Returns:
            An adapter that can handle the file, or None if no adapter matches.
        """
        for adapter in self._adapters:
            if adapter.can_handle(file_path):
                return adapter
        return None

    def extract(self, file_path: Path) -> TokenSet:
        """Extract tokens from a file using the appropriate adapter.

        Args:
            file_path: Path to the token source file.

        Returns:
            TokenSet containing all extracted tokens.

        Raises:
            ValueError: If no adapter can handle the file.
        """
        adapter = self.get_adapter(file_path)
        if adapter is None:
            raise ValueError(f"No adapter found for file: {file_path}")
        return adapter.extract(file_path)

    def extract_all(self, file_paths: list[Path]) -> TokenSet:
        """Extract and merge tokens from multiple files.

        Args:
            file_paths: List of paths to token source files.

        Returns:
            Merged TokenSet containing tokens from all files.
        """
        result = TokenSet()
        for file_path in file_paths:
            adapter = self.get_adapter(file_path)
            if adapter is not None:
                tokens = adapter.extract(file_path)
                result = result.merge(tokens)
        return result


# Global registry instance
_default_registry: TokenAdapterRegistry | None = None


def get_default_registry() -> TokenAdapterRegistry:
    """Get the default token adapter registry with all built-in adapters.

    Returns:
        TokenAdapterRegistry with CSS, Tailwind, and JSON adapters registered.
    """
    global _default_registry
    if _default_registry is None:
        from .css_vars import CSSVariablesAdapter
        from .json_tokens import JSONTokenAdapter
        from .tailwind import TailwindConfigAdapter

        _default_registry = TokenAdapterRegistry()
        _default_registry.register(CSSVariablesAdapter())
        _default_registry.register(TailwindConfigAdapter())
        _default_registry.register(JSONTokenAdapter())
    return _default_registry
