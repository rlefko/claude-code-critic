"""
Component duplication detection rule.

Detects duplicate functions and classes across files using multi-signal
similarity scoring: exact (hash), structural (AST features), and
semantic (embedding-based).
"""

import hashlib
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class DuplicationType(Enum):
    """Classification of duplicate type."""

    EXACT = "exact"  # Hash match (100% identical)
    STRUCTURAL = "structural"  # AST similarity >95%
    SEMANTIC = "semantic"  # Embedding similarity >90%
    SIMILAR = "similar"  # 60-90% similarity (refactoring opportunity)


@dataclass
class ExtractedEntity:
    """An extracted function or class from the code."""

    name: str
    entity_type: str
    start_line: int
    end_line: int
    content: str
    content_hash: str = ""
    structural_hash: str = ""


@dataclass
class DuplicateCandidate:
    """A potential duplicate match."""

    source_name: str
    source_file: str
    source_line: int
    target_name: str
    target_file: str
    target_line: int
    duplication_type: DuplicationType
    similarity_score: float
    hash_score: float = 0.0
    structural_score: float = 0.0
    semantic_score: float = 0.0
    source_snippet: str = ""
    target_snippet: str = ""


class ComponentDuplicationRule(BaseRule):
    """Detect duplicate functions and classes across files.

    Uses multi-signal similarity scoring:
    - Exact: SHA256 hash match (fastest)
    - Structural: SimHash of AST features (>95% match)
    - Semantic: Embedding similarity via memory search (>90% match)
    """

    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "exact": 1.0,
        "structural": 0.95,
        "semantic": 0.90,
        "similar": 0.60,
    }

    # Multi-signal weights
    DEFAULT_WEIGHTS = {
        "hash": 0.2,
        "structural": 0.4,
        "semantic": 0.4,
    }

    DEFAULT_MAX_CANDIDATES = 5
    DEFAULT_MIN_ENTITY_LINES = 5

    # Function detection patterns
    FUNCTION_PATTERNS = {
        "python": r"^\s*(?:async\s+)?def\s+(\w+)\s*\(",
        "javascript": r"(?:^|\s)(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)",
        "typescript": r"(?:^|\s)(?:async\s+)?function\s+(\w+)\s*\(|(?:const|let|var)\s+(\w+)\s*:\s*\w+\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)|(?:public|private|protected)?\s*(?:async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*\{",
    }

    CLASS_PATTERNS = {
        "python": r"^\s*class\s+(\w+)\s*[:\(]",
        "javascript": r"^\s*class\s+(\w+)",
        "typescript": r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(\w+)",
    }

    # Control flow patterns for structural hashing
    STRUCTURAL_PATTERNS = {
        "python": [
            (r"\bif\b", "CTRL:IF"),
            (r"\bfor\b", "CTRL:FOR"),
            (r"\bwhile\b", "CTRL:WHILE"),
            (r"\breturn\b", "CTRL:RETURN"),
            (r"\btry\b", "CTRL:TRY"),
            (r"\bclass\b", "DECL:CLASS"),
            (r"\bdef\b", "DECL:FUNC"),
        ],
        "javascript": [
            (r"\bif\b", "CTRL:IF"),
            (r"\bfor\b", "CTRL:FOR"),
            (r"\bwhile\b", "CTRL:WHILE"),
            (r"\breturn\b", "CTRL:RETURN"),
            (r"\btry\b", "CTRL:TRY"),
            (r"\bclass\b", "DECL:CLASS"),
            (r"\bfunction\b", "DECL:FUNC"),
            (r"=>", "DECL:ARROW"),
        ],
        "typescript": [
            (r"\bif\b", "CTRL:IF"),
            (r"\bfor\b", "CTRL:FOR"),
            (r"\bwhile\b", "CTRL:WHILE"),
            (r"\breturn\b", "CTRL:RETURN"),
            (r"\btry\b", "CTRL:TRY"),
            (r"\bclass\b", "DECL:CLASS"),
            (r"\bfunction\b", "DECL:FUNC"),
            (r"=>", "DECL:ARROW"),
        ],
    }

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.COMPONENT_DUPLICATION"

    @property
    def name(self) -> str:
        return "Component Duplication Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects duplicate functions and classes across files using "
            "multi-signal similarity scoring (hash, structural, semantic). "
            "Identifies exact duplicates, near-duplicates, and refactoring opportunities."
        )

    @property
    def is_fast(self) -> bool:
        return False  # Requires memory search

    def _get_threshold(self, context: RuleContext, level: str) -> float:
        """Get threshold for a specific level from config or default."""
        if context.config:
            return context.config.get_rule_parameter(
                self.rule_id,
                f"{level}_threshold",
                self.DEFAULT_THRESHOLDS.get(level, 0.5),
            )
        return self.DEFAULT_THRESHOLDS.get(level, 0.5)

    def _get_max_candidates(self, context: RuleContext) -> int:
        """Get max candidates from config or default."""
        if context.config:
            return context.config.get_rule_parameter(
                self.rule_id, "max_candidates", self.DEFAULT_MAX_CANDIDATES
            )
        return self.DEFAULT_MAX_CANDIDATES

    def _get_min_entity_lines(self, context: RuleContext) -> int:
        """Get minimum entity lines from config or default."""
        if context.config:
            return context.config.get_rule_parameter(
                self.rule_id, "min_entity_lines", self.DEFAULT_MIN_ENTITY_LINES
            )
        return self.DEFAULT_MIN_ENTITY_LINES

    def _normalize_for_hash(self, content: str) -> str:
        """Normalize content for hash comparison."""
        # Remove comments
        content = re.sub(r"#.*$", "", content, flags=re.MULTILINE)  # Python
        content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)  # JS/TS
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)  # Multi-line
        # Normalize whitespace
        content = re.sub(r"\s+", " ", content).strip()
        return content

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash for exact duplicate detection."""
        normalized = self._normalize_for_hash(content)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def _extract_structural_features(self, content: str, language: str) -> list[str]:
        """Extract structural features from code for SimHash."""
        features = []
        patterns = self.STRUCTURAL_PATTERNS.get(language, [])

        for pattern, feature in patterns:
            count = len(re.findall(pattern, content))
            features.extend([feature] * count)

        # Parameter count
        param_match = re.search(r"\(([^)]*)\)", content)
        if param_match:
            params = param_match.group(1).split(",")
            param_count = len([p for p in params if p.strip()])
            features.append(f"PARAMS:{param_count}")

        # Line count bucket
        lines = content.count("\n") + 1
        bucket = (lines // 5) * 5  # 5-line buckets
        features.append(f"LINES:{bucket}")

        return features

    def _compute_simhash(self, features: list[str]) -> int:
        """Compute SimHash from a list of features."""
        hash_bits = 64
        vector = [0] * hash_bits

        for feature in features:
            feature_hash = int(hashlib.md5(feature.encode()).hexdigest(), 16)
            for i in range(hash_bits):
                if (feature_hash >> i) & 1:
                    vector[i] += 1
                else:
                    vector[i] -= 1

        simhash = 0
        for i in range(hash_bits):
            if vector[i] > 0:
                simhash |= 1 << i

        return simhash

    def _simhash_similarity(self, hash1: int, hash2: int) -> float:
        """Calculate similarity between two SimHash values."""
        hash_bits = 64
        diff = bin(hash1 ^ hash2).count("1")
        return 1.0 - (diff / hash_bits)

    def _compute_structural_hash(self, content: str, language: str) -> int:
        """Compute structural hash from content."""
        features = self._extract_structural_features(content, language)
        return self._compute_simhash(features)

    def _find_python_function_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a Python function based on indentation."""
        if start_line >= len(lines):
            return start_line

        def_line = lines[start_line]
        base_indent = len(def_line) - len(def_line.lstrip())

        for i in range(start_line + 1, len(lines)):
            line = lines[i]
            stripped = line.strip()

            if not stripped or stripped.startswith("#"):
                continue

            current_indent = len(line) - len(line.lstrip())

            if current_indent <= base_indent:
                return i - 1

        return len(lines) - 1

    def _find_js_function_end(self, lines: list[str], start_line: int) -> int:
        """Find the end of a JS/TS function by counting braces."""
        brace_count = 0
        found_first_brace = False

        for i in range(start_line, len(lines)):
            line = lines[i]
            for char in line:
                if char == "{":
                    brace_count += 1
                    found_first_brace = True
                elif char == "}":
                    brace_count -= 1

            if found_first_brace and brace_count == 0:
                return i

        return len(lines) - 1

    def _extract_entities(self, context: RuleContext) -> list[ExtractedEntity]:
        """Extract functions and classes from the file."""
        entities = []
        language = context.language
        lines = context.lines
        min_lines = self._get_min_entity_lines(context)

        func_pattern = self.FUNCTION_PATTERNS.get(language)
        class_pattern = self.CLASS_PATTERNS.get(language)

        for line_num, line in enumerate(lines):
            entity_name = None
            entity_type = None

            # Check for function
            if func_pattern:
                match = re.search(func_pattern, line)
                if match:
                    for group in match.groups():
                        if group:
                            entity_name = group
                            entity_type = "function"
                            break

            # Check for class (if no function match)
            if entity_name is None and class_pattern:
                match = re.search(class_pattern, line)
                if match:
                    entity_name = match.group(1)
                    entity_type = "class"

            if entity_name and entity_type:
                if language == "python":
                    end_line = self._find_python_function_end(lines, line_num)
                else:
                    end_line = self._find_js_function_end(lines, line_num)

                # Check if entity is large enough
                if (end_line - line_num + 1) < min_lines:
                    continue

                # Check if any line in entity is in diff
                in_diff = any(
                    context.is_line_in_diff(ln)
                    for ln in range(line_num + 1, end_line + 2)
                )
                if not in_diff:
                    continue

                content = "\n".join(lines[line_num : end_line + 1])
                content_hash = self._compute_content_hash(content)
                structural_hash = self._compute_structural_hash(content, language)

                entities.append(
                    ExtractedEntity(
                        name=entity_name,
                        entity_type=entity_type,
                        start_line=line_num + 1,
                        end_line=end_line + 1,
                        content=content,
                        content_hash=content_hash,
                        structural_hash=str(structural_hash),
                    )
                )

        return entities

    def _classify_score(self, score: float, context: RuleContext) -> DuplicationType:
        """Classify duplicate type based on combined score."""
        if score >= self._get_threshold(context, "exact"):
            return DuplicationType.EXACT
        elif score >= self._get_threshold(context, "structural"):
            return DuplicationType.STRUCTURAL
        elif score >= self._get_threshold(context, "semantic"):
            return DuplicationType.SEMANTIC
        else:
            return DuplicationType.SIMILAR

    def _find_duplicates(
        self,
        entity: ExtractedEntity,
        context: RuleContext,
    ) -> list[DuplicateCandidate]:
        """Find duplicates for an entity using multi-signal search."""
        candidates = []
        max_candidates = self._get_max_candidates(context)
        similar_threshold = self._get_threshold(context, "similar")

        # Build query from entity content
        query = entity.content[:500]

        # Search memory for semantically similar entities
        results = context.search_memory(
            query=query,
            limit=max_candidates + 1,
            entity_types=[entity.entity_type, "method"],
        )

        for result in results:
            # Skip self-match
            if result.get("name") == entity.name and result.get("file_path") == str(
                context.file_path
            ):
                continue

            semantic_score = result.get("score", 0.0)

            # Filter by minimum similarity
            if semantic_score < similar_threshold:
                continue

            target_content = result.get("content", "")
            target_name = result.get("name", "")
            target_file = result.get("file_path", "")

            # Calculate hash score (exact match = 1.0)
            target_hash = self._compute_content_hash(target_content)
            hash_score = 1.0 if entity.content_hash == target_hash else 0.0

            # Calculate structural score
            if target_content:
                target_struct_hash = self._compute_structural_hash(
                    target_content, context.language
                )
                structural_score = self._simhash_similarity(
                    int(entity.structural_hash), target_struct_hash
                )
            else:
                structural_score = 0.0

            # Calculate combined score
            combined_score = (
                self.DEFAULT_WEIGHTS["hash"] * hash_score
                + self.DEFAULT_WEIGHTS["structural"] * structural_score
                + self.DEFAULT_WEIGHTS["semantic"] * semantic_score
            )

            # Classify duplication type
            dup_type = self._classify_score(combined_score, context)

            # Get snippets for evidence
            source_snippet = "\n".join(entity.content.split("\n")[:5])
            if len(entity.content.split("\n")) > 5:
                source_snippet += "\n..."

            target_snippet = "\n".join(target_content.split("\n")[:5])
            if len(target_content.split("\n")) > 5:
                target_snippet += "\n..."

            candidates.append(
                DuplicateCandidate(
                    source_name=entity.name,
                    source_file=str(context.file_path),
                    source_line=entity.start_line,
                    target_name=target_name,
                    target_file=target_file,
                    target_line=0,  # Not available from memory search
                    duplication_type=dup_type,
                    similarity_score=combined_score,
                    hash_score=hash_score,
                    structural_score=structural_score,
                    semantic_score=semantic_score,
                    source_snippet=source_snippet,
                    target_snippet=target_snippet,
                )
            )

            if len(candidates) >= max_candidates:
                break

        return candidates

    def _generate_refactoring_suggestions(
        self,
        entity: ExtractedEntity,
        duplicate: DuplicateCandidate,
    ) -> list[str]:
        """Generate actionable refactoring suggestions."""
        suggestions = []

        if duplicate.duplication_type == DuplicationType.EXACT:
            suggestions.extend(
                [
                    f"Extract '{entity.name}' to a shared module and import from both locations",
                    f"Consider creating a utility file for shared '{entity.name}' implementation",
                    "This is an exact duplicate - consider removing one copy",
                ]
            )
        elif duplicate.duplication_type == DuplicationType.STRUCTURAL:
            suggestions.extend(
                [
                    f"'{entity.name}' and '{duplicate.target_name}' have similar structure",
                    "Consider extracting common logic into a base class or helper function",
                    "If behavior differs by parameters, consider using a factory pattern",
                ]
            )
        elif duplicate.duplication_type == DuplicationType.SEMANTIC:
            suggestions.extend(
                [
                    f"'{entity.name}' appears to serve a similar purpose as '{duplicate.target_name}'",
                    "Review both implementations to determine if one can be reused",
                    "Consider creating a shared interface or abstract base class",
                ]
            )
        else:  # SIMILAR
            suggestions.extend(
                [
                    f"'{entity.name}' has some similarity with '{duplicate.target_name}'",
                    "This might be a refactoring opportunity to reduce code duplication",
                    "Review both implementations for potential consolidation",
                ]
            )

        return suggestions

    def _create_duplicate_finding(
        self,
        entity: ExtractedEntity,
        duplicate: DuplicateCandidate,
        context: RuleContext,
    ) -> "Finding":
        """Create a detailed finding for a duplicate."""
        # Determine severity based on duplicate type
        if duplicate.duplication_type == DuplicationType.EXACT:
            severity_override = Severity.HIGH
            summary = f"Exact duplicate of '{duplicate.target_name}' in {duplicate.target_file}"
        elif duplicate.duplication_type == DuplicationType.STRUCTURAL:
            severity_override = Severity.MEDIUM
            summary = (
                f"Structural duplicate ({duplicate.similarity_score:.0%}) "
                f"of '{duplicate.target_name}'"
            )
        elif duplicate.duplication_type == DuplicationType.SEMANTIC:
            severity_override = Severity.MEDIUM
            summary = (
                f"Semantic duplicate ({duplicate.similarity_score:.0%}) "
                f"of '{duplicate.target_name}'"
            )
        else:
            severity_override = Severity.LOW
            summary = (
                f"Similar to '{duplicate.target_name}' ({duplicate.similarity_score:.0%}) "
                f"- refactoring opportunity"
            )

        evidence = [
            Evidence(
                description="Multi-signal similarity analysis",
                line_number=entity.start_line,
                code_snippet=duplicate.source_snippet,
                data={
                    "hash_score": duplicate.hash_score,
                    "structural_score": duplicate.structural_score,
                    "semantic_score": duplicate.semantic_score,
                    "combined_score": duplicate.similarity_score,
                    "duplication_type": duplicate.duplication_type.value,
                    "target_file": duplicate.target_file,
                    "target_name": duplicate.target_name,
                },
            ),
        ]

        remediation_hints = self._generate_refactoring_suggestions(entity, duplicate)

        # Create finding with appropriate severity
        finding = self._create_finding(
            summary=summary,
            file_path=str(context.file_path),
            line_number=entity.start_line,
            end_line=entity.end_line,
            evidence=evidence,
            remediation_hints=remediation_hints,
            confidence=duplicate.similarity_score,
        )

        # Override severity based on duplication type
        finding.severity = severity_override

        return finding

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for duplicate components.

        Args:
            context: RuleContext with file content and memory access

        Returns:
            List of findings for duplicate components
        """
        findings = []

        # Skip if no memory client available
        if context.memory_client is None or context.collection_name is None:
            return findings

        # Skip unsupported languages
        if context.language not in (self.supported_languages or []):
            return findings

        # Extract functions and classes
        entities = self._extract_entities(context)

        for entity in entities:
            # Find duplicates
            duplicates = self._find_duplicates(entity, context)

            for duplicate in duplicates:
                # Only report significant duplicates (above similar threshold)
                if duplicate.similarity_score >= self._get_threshold(
                    context, "similar"
                ):
                    findings.append(
                        self._create_duplicate_finding(entity, duplicate, context)
                    )

        return findings
