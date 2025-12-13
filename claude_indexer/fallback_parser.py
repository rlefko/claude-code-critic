"""
Fallback parser for files with syntax errors.

This module provides regex-based extraction when AST parsing fails,
ensuring that even broken files are indexed and searchable.
"""

import logging
import re
from pathlib import Path

from .analysis.entities import Entity, EntityType, Relation, RelationType
from .analysis.parser import ParserResult

logger = logging.getLogger(__name__)


class FallbackParser:
    """
    Regex-based fallback parser for files with syntax errors.

    Extracts as much information as possible from broken files using
    pattern matching, ensuring nothing is lost from the index.
    """

    # Common programming patterns across languages
    PATTERNS = {
        # Functions/Methods (JS/TS/Python)
        "function": [
            r"(?:async\s+)?function\s+(\w+)\s*\(",  # JS/TS functions
            r"(?:export\s+)?(?:async\s+)?(?:function\s+)?(\w+)\s*(?::\s*\w+)?\s*=\s*(?:async\s*)?\(",  # Arrow functions
            r"def\s+(\w+)\s*\(",  # Python functions
            r"(?:public|private|protected)?\s*(?:static)?\s*(?:async)?\s*(\w+)\s*\(",  # Method-like
        ],
        # Classes
        "class": [
            r"class\s+(\w+)(?:\s+extends\s+\w+)?",  # JS/TS/Python classes
            r"interface\s+(\w+)",  # TypeScript interfaces
            r"type\s+(\w+)\s*=",  # TypeScript type aliases
            r"struct\s+(\w+)",  # Go/Rust structs
        ],
        # Variables/Constants
        "variable": [
            r"(?:const|let|var)\s+(\w+)\s*=",  # JS/TS
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)",  # Exported vars
            r"^(\w+)\s*=\s*[^=]",  # Python variables (simple)
        ],
        # Imports
        "import": [
            r'import\s+(?:\{[^}]*\}|\*|\w+)\s+from\s+[\'"]([^\'"\n]+)',  # ES6
            r"import\s+([^\s;]+)",  # Python/Java
            r'require\s*\([\'"]([^\'"\)]+)',  # CommonJS
            r"from\s+([^\s]+)\s+import",  # Python from import
        ],
        # Comments with TODOs, FIXMEs, etc
        "documentation": [
            r"//\s*(TODO|FIXME|HACK|NOTE|BUG|XXX):?\s*(.+)$",  # Single-line
            r"#\s*(TODO|FIXME|HACK|NOTE|BUG|XXX):?\s*(.+)$",  # Python/Shell
            r"/\*\s*(TODO|FIXME|HACK|NOTE|BUG|XXX):?\s*([^*]+)",  # Multi-line
        ],
    }

    @classmethod
    def parse_with_fallback(
        cls, file_path: Path, error_message: str = None
    ) -> ParserResult:
        """
        Attempt to extract entities from a file with syntax errors.

        Args:
            file_path: Path to the file with syntax errors
            error_message: Original parser error message

        Returns:
            ParserResult with extracted entities and a warning about syntax errors
        """
        entities = []
        relations = []

        try:
            # Read file content
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            # Create file entity with syntax error warning
            file_entity = Entity(
                name=str(file_path),
                entity_type=EntityType.FILE,
                observations=[
                    f"⚠️ File has syntax errors: {error_message or 'Unknown error'}",
                    "Fallback parsing applied - partial content extracted",
                    f"File size: {file_path.stat().st_size} bytes",
                    f"Lines: {len(lines)}",
                ],
                file_path=file_path,
                line_number=1,
            )
            entities.append(file_entity)

            # Extract functions
            functions = cls._extract_patterns(content, cls.PATTERNS["function"])
            for func_name, line_num in functions:
                if func_name and cls._is_valid_identifier(func_name):
                    entity = Entity(
                        name=func_name,
                        entity_type=EntityType.FUNCTION,
                        observations=[
                            "Function extracted via fallback parser",
                            f"Found at line {line_num}",
                            "⚠️ Full signature unavailable due to syntax errors",
                        ],
                        file_path=file_path,
                        line_number=line_num,
                    )
                    entities.append(entity)

            # Extract classes
            classes = cls._extract_patterns(content, cls.PATTERNS["class"])
            for class_name, line_num in classes:
                if class_name and cls._is_valid_identifier(class_name):
                    entity = Entity(
                        name=class_name,
                        entity_type=EntityType.CLASS,
                        observations=[
                            "Class/Interface extracted via fallback parser",
                            f"Found at line {line_num}",
                            "⚠️ Members unavailable due to syntax errors",
                        ],
                        file_path=file_path,
                        line_number=line_num,
                    )
                    entities.append(entity)

            # Extract variables/constants
            variables = cls._extract_patterns(content, cls.PATTERNS["variable"])
            for var_name, line_num in variables[:20]:  # Limit to avoid noise
                if var_name and cls._is_valid_identifier(var_name):
                    entity = Entity(
                        name=var_name,
                        entity_type=EntityType.VARIABLE,
                        observations=[
                            "Variable/Constant extracted via fallback parser",
                            f"Found at line {line_num}",
                        ],
                        file_path=file_path,
                        line_number=line_num,
                    )
                    entities.append(entity)

            # Extract imports for relations
            imports = cls._extract_patterns(content, cls.PATTERNS["import"])
            for import_path, line_num in imports:
                if import_path:
                    # Create a relation from file to imported module
                    relation = Relation(
                        from_entity=str(file_path),
                        to_entity=import_path,
                        relation_type=RelationType.IMPORTS,
                        metadata={"line_number": line_num, "fallback_parsed": True},
                    )
                    relations.append(relation)

            # Extract important comments
            docs = cls._extract_patterns(content, cls.PATTERNS["documentation"])
            for doc_match, line_num in docs[:10]:  # Limit TODO/FIXME extraction
                if isinstance(doc_match, tuple) and len(doc_match) >= 2:
                    doc_type, doc_text = doc_match[0], doc_match[1]
                    entity = Entity(
                        name=f"{doc_type}: {doc_text[:50]}...",
                        entity_type=EntityType.DOCUMENTATION,
                        observations=[
                            f"{doc_type} comment: {doc_text}",
                            f"Found at line {line_num}",
                        ],
                        file_path=file_path,
                        line_number=line_num,
                    )
                    entities.append(entity)

            # Create a searchable content entity with the first 1000 chars
            content_preview = content[:1000].replace("\n", " ")
            if content_preview:
                content_entity = Entity(
                    name=f"{file_path.name}_content",
                    entity_type=EntityType.DOCUMENTATION,
                    observations=[
                        "File content preview (first 1000 chars)",
                        content_preview,
                        "⚠️ Complete parsing unavailable due to syntax errors",
                    ],
                    file_path=file_path,
                    line_number=1,
                )
                entities.append(content_entity)

            logger.debug(
                f"Fallback parser extracted {len(entities)} entities, "
                f"{len(relations)} relations from {file_path.name}"
            )

            return ParserResult(
                file_path=file_path,
                entities=entities,
                relations=relations,
                implementation_chunks=[],  # No detailed implementations for broken files
                errors=[],  # Clear errors since we handled it
                warnings=[
                    f"Syntax errors in file - used fallback parser: {error_message}"
                ],
            )

        except Exception as e:
            logger.error(f"Fallback parser also failed for {file_path}: {e}")
            # Return minimal result with file entity only
            return ParserResult(
                file_path=file_path,
                entities=[
                    Entity(
                        name=str(file_path),
                        entity_type=EntityType.FILE,
                        observations=[
                            f"⚠️ File could not be parsed: {error_message or 'Unknown error'}",
                            f"⚠️ Fallback parser also failed: {str(e)}",
                            "File exists but content extraction failed",
                        ],
                        file_path=file_path,
                        line_number=1,
                    )
                ],
                relations=[],
                implementation_chunks=[],
                errors=[f"Fallback parsing failed: {str(e)}"],
                warnings=[],
            )

    @staticmethod
    def _extract_patterns(content: str, patterns: list[str]) -> list[tuple[str, int]]:
        """
        Extract matches for given regex patterns with line numbers.

        Returns list of (match, line_number) tuples.
        """
        results = []
        lines = content.split("\n")

        for pattern in patterns:
            try:
                # Search line by line to get line numbers
                for line_num, line in enumerate(lines, 1):
                    matches = re.finditer(pattern, line, re.MULTILINE)
                    for match in matches:
                        # Get the first captured group (the name)
                        if match.groups():
                            # Handle nested groups from complex patterns
                            captured = match.groups()
                            if len(captured) == 1:
                                results.append((captured[0], line_num))
                            else:
                                # For patterns with multiple groups (like TODO comments)
                                results.append((captured, line_num))
            except re.error:
                # Skip invalid regex patterns
                continue

        return results

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """Check if a name is a valid identifier (not too short or too long)."""
        if not name:
            return False
        # Filter out common false positives
        if len(name) < 2 or len(name) > 100:
            return False
        # Must start with letter or underscore
        if not (name[0].isalpha() or name[0] == "_"):
            return False
        # Avoid operators and special chars
        return name not in [
            "if",
            "for",
            "while",
            "return",
            "true",
            "false",
            "null",
            "undefined",
        ]
