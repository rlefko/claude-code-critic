"""Base classes for source code collection.

This module defines the abstract base classes and data structures
used by all source collectors and framework adapters.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..models import SymbolKind, SymbolRef, Visibility


@dataclass
class ExtractedComponent:
    """Represents an extracted UI component.

    Contains information about a component's structure, props, and
    style usage extracted from source code.
    """

    name: str
    source_ref: SymbolRef
    tag_name: str  # 'Button', 'div', etc.
    props: dict[str, Any] = field(default_factory=dict)
    children_structure: str = ""  # Normalized template skeleton
    style_refs: list[str] = field(default_factory=list)  # Class names, CSS module keys
    framework: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "source_ref": self.source_ref.to_dict(),
            "tag_name": self.tag_name,
            "props": self.props,
            "children_structure": self.children_structure,
            "style_refs": self.style_refs,
            "framework": self.framework,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedComponent":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            source_ref=SymbolRef.from_dict(data["source_ref"]),
            tag_name=data["tag_name"],
            props=data.get("props", {}),
            children_structure=data.get("children_structure", ""),
            style_refs=data.get("style_refs", []),
            framework=data.get("framework", ""),
        )


@dataclass
class ExtractedStyle:
    """Represents extracted style information.

    Contains style declarations, selectors, and class usage
    extracted from CSS or component files.
    """

    source_ref: SymbolRef
    selector: str | None = None  # CSS selector
    declarations: dict[str, str] = field(default_factory=dict)
    is_inline: bool = False
    class_names: list[str] = field(default_factory=list)  # For utility class usage

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_ref": self.source_ref.to_dict(),
            "selector": self.selector,
            "declarations": self.declarations,
            "is_inline": self.is_inline,
            "class_names": self.class_names,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedStyle":
        """Create from dictionary."""
        return cls(
            source_ref=SymbolRef.from_dict(data["source_ref"]),
            selector=data.get("selector"),
            declarations=data.get("declarations", {}),
            is_inline=data.get("is_inline", False),
            class_names=data.get("class_names", []),
        )


@dataclass
class ExtractionResult:
    """Result of source extraction.

    Contains all extracted components and styles from a file,
    along with any errors encountered.
    """

    components: list[ExtractedComponent] = field(default_factory=list)
    styles: list[ExtractedStyle] = field(default_factory=list)
    file_path: Path | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "components": [c.to_dict() for c in self.components],
            "styles": [s.to_dict() for s in self.styles],
            "file_path": str(self.file_path) if self.file_path else None,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractionResult":
        """Create from dictionary."""
        return cls(
            components=[
                ExtractedComponent.from_dict(c) for c in data.get("components", [])
            ],
            styles=[ExtractedStyle.from_dict(s) for s in data.get("styles", [])],
            file_path=Path(data["file_path"]) if data.get("file_path") else None,
            errors=data.get("errors", []),
        )

    @property
    def has_errors(self) -> bool:
        """Check if extraction had any errors."""
        return len(self.errors) > 0

    @property
    def is_empty(self) -> bool:
        """Check if no components or styles were extracted."""
        return len(self.components) == 0 and len(self.styles) == 0

    def merge(self, other: "ExtractionResult") -> "ExtractionResult":
        """Merge another extraction result into this one.

        Args:
            other: Another ExtractionResult to merge.

        Returns:
            New ExtractionResult with combined data.
        """
        return ExtractionResult(
            components=self.components + other.components,
            styles=self.styles + other.styles,
            file_path=self.file_path,
            errors=self.errors + other.errors,
        )


class BaseSourceAdapter(ABC):
    """Abstract base for framework-specific source adapters.

    Each framework adapter (React, Vue, Svelte, CSS) extends this
    base class to provide framework-specific extraction logic.
    """

    @property
    @abstractmethod
    def supported_extensions(self) -> list[str]:
        """File extensions this adapter can handle.

        Returns:
            List of file extensions (including dot, e.g., '.tsx').
        """
        ...

    @property
    def name(self) -> str:
        """Human-readable name of this adapter."""
        return self.__class__.__name__

    @abstractmethod
    def can_handle(self, file_path: Path) -> bool:
        """Check if this adapter can handle the given file.

        Args:
            file_path: Path to the file.

        Returns:
            True if this adapter can process the file.
        """
        ...

    @abstractmethod
    def extract_components(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedComponent]:
        """Extract component definitions from file.

        Args:
            file_path: Path to the source file.
            content: Optional file content (read from file if not provided).

        Returns:
            List of extracted components.
        """
        ...

    @abstractmethod
    def extract_style_usage(
        self, file_path: Path, content: str | None = None
    ) -> list[ExtractedStyle]:
        """Extract style usage from file.

        Args:
            file_path: Path to the source file.
            content: Optional file content (read from file if not provided).

        Returns:
            List of extracted styles.
        """
        ...

    def extract(self, file_path: Path, content: str | None = None) -> ExtractionResult:
        """Extract both components and styles from file.

        Args:
            file_path: Path to the source file.
            content: Optional file content.

        Returns:
            ExtractionResult with components, styles, and any errors.
        """
        errors = []
        components = []
        styles = []

        try:
            components = self.extract_components(file_path, content)
        except Exception as e:
            errors.append(f"Component extraction failed: {e}")

        try:
            styles = self.extract_style_usage(file_path, content)
        except Exception as e:
            errors.append(f"Style extraction failed: {e}")

        return ExtractionResult(
            components=components,
            styles=styles,
            file_path=file_path,
            errors=errors,
        )

    def _read_file(self, file_path: Path, content: str | None = None) -> str:
        """Read file content if not provided.

        Args:
            file_path: Path to the file.
            content: Pre-provided content.

        Returns:
            File content as string.
        """
        if content is not None:
            return content
        return file_path.read_text(encoding="utf-8")

    def _create_symbol_ref(
        self,
        file_path: Path,
        start_line: int,
        end_line: int,
        name: str | None = None,
        kind: SymbolKind = SymbolKind.COMPONENT,
        visibility: Visibility = Visibility.LOCAL,
    ) -> SymbolRef:
        """Create a SymbolRef for extracted code.

        Args:
            file_path: Path to the source file.
            start_line: Starting line number (1-based).
            end_line: Ending line number (1-based).
            name: Optional symbol name.
            kind: Type of symbol.
            visibility: Visibility level.

        Returns:
            SymbolRef instance.
        """
        return SymbolRef(
            file_path=str(file_path),
            start_line=start_line,
            end_line=end_line,
            kind=kind,
            visibility=visibility,
            name=name,
        )
