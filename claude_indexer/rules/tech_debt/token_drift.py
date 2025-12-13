"""
Token drift detection rule.

Detects when similar code entities (functions, classes) have diverged
over time, indicating one may need updating to match the other.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


@dataclass
class ExtractedEntity:
    """An extracted function or class from the code."""

    name: str
    entity_type: str  # "function" or "class"
    start_line: int
    end_line: int
    content: str


@dataclass
class DriftCandidate:
    """A potential drift candidate found in memory."""

    name: str
    file_path: str
    content: str
    similarity_score: float
    entity_type: str


@dataclass
class DriftAnalysis:
    """Result of analyzing drift between two entities."""

    source_name: str
    candidate_name: str
    source_file: str
    candidate_file: str
    similarity_score: float
    drift_score: float  # 0-1, higher = more drift
    drift_indicators: list[str]
    is_significant: bool
    reconciliation_hint: str | None = None


class TokenDriftRule(BaseRule):
    """Detect token drift between similar code entities.

    Token drift occurs when similar code entities (functions, classes)
    have diverged over time. For example:
    - Two validation functions that were similar but one got updated
    - Copy-pasted code that evolved differently
    - Similar API handlers with inconsistent implementations
    """

    # Default thresholds
    DEFAULT_SIMILARITY_THRESHOLD = 0.85
    DEFAULT_DRIFT_THRESHOLD = 0.3
    DEFAULT_MAX_CANDIDATES = 5
    DEFAULT_MIN_ENTITY_LINES = 3

    # Function detection patterns (shared with ComplexityRule)
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

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.TOKEN_DRIFT"

    @property
    def name(self) -> str:
        return "Token Drift Detection"

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
            "Detects when similar code entities have diverged over time. "
            "Searches semantic memory for similar functions/classes and "
            "compares implementations to identify inconsistencies that "
            "may indicate one needs updating."
        )

    @property
    def is_fast(self) -> bool:
        return False  # Requires memory search

    def _get_similarity_threshold(self, context: RuleContext) -> float:
        """Get similarity threshold from config or default."""
        if context.config:
            return context.config.get_rule_parameter(
                self.rule_id, "similarity_threshold", self.DEFAULT_SIMILARITY_THRESHOLD
            )
        return self.DEFAULT_SIMILARITY_THRESHOLD

    def _get_drift_threshold(self, context: RuleContext) -> float:
        """Get drift threshold from config or default."""
        if context.config:
            return context.config.get_rule_parameter(
                self.rule_id, "drift_threshold", self.DEFAULT_DRIFT_THRESHOLD
            )
        return self.DEFAULT_DRIFT_THRESHOLD

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

    def _extract_changed_entities(self, context: RuleContext) -> list[ExtractedEntity]:
        """Extract functions and classes that were modified."""
        entities = []
        language = context.language
        lines = context.lines
        min_lines = self._get_min_entity_lines(context)

        func_pattern = self.FUNCTION_PATTERNS.get(language)
        class_pattern = self.CLASS_PATTERNS.get(language)

        for line_num, line in enumerate(lines):
            # Check for function
            if func_pattern:
                match = re.search(func_pattern, line)
                if match:
                    func_name = None
                    for group in match.groups():
                        if group:
                            func_name = group
                            break

                    if func_name:
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
                        entities.append(
                            ExtractedEntity(
                                name=func_name,
                                entity_type="function",
                                start_line=line_num + 1,
                                end_line=end_line + 1,
                                content=content,
                            )
                        )

            # Check for class
            if class_pattern:
                match = re.search(class_pattern, line)
                if match:
                    class_name = match.group(1)

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
                    entities.append(
                        ExtractedEntity(
                            name=class_name,
                            entity_type="class",
                            start_line=line_num + 1,
                            end_line=end_line + 1,
                            content=content,
                        )
                    )

        return entities

    def _find_similar_entities(
        self,
        entity: ExtractedEntity,
        context: RuleContext,
    ) -> list[DriftCandidate]:
        """Search memory for similar entities."""
        candidates = []
        max_candidates = self._get_max_candidates(context)
        similarity_threshold = self._get_similarity_threshold(context)

        # Build query from entity name and first few lines (signature)
        query_lines = entity.content.split("\n")[:3]
        query = f"{entity.name} {' '.join(query_lines)}"

        # Search memory
        results = context.search_memory(
            query=query[:500],  # Limit query length
            limit=max_candidates + 1,  # +1 to account for self
            entity_types=[entity.entity_type, "method"],
        )

        for result in results:
            # Skip self-match
            if result.get("name") == entity.name and result.get("file_path") == str(
                context.file_path
            ):
                continue

            score = result.get("score", 0.0)

            # Filter by similarity threshold
            if score >= similarity_threshold:
                candidates.append(
                    DriftCandidate(
                        name=result.get("name", ""),
                        file_path=result.get("file_path", ""),
                        content=result.get("content", ""),
                        similarity_score=score,
                        entity_type=result.get("type", entity.entity_type),
                    )
                )

            if len(candidates) >= max_candidates:
                break

        return candidates

    def _count_parameters(self, content: str, language: str) -> int:
        """Count parameters in a function signature."""
        if language == "python":
            match = re.search(r"def\s+\w+\s*\(([^)]*)\)", content)
        else:
            match = re.search(r"function\s+\w+\s*\(([^)]*)\)|=>\s*\(([^)]*)\)", content)

        if match:
            params = match.group(1) or (match.group(2) if match.lastindex > 1 else "")
            if params.strip():
                return len([p for p in params.split(",") if p.strip()])
        return 0

    def _compare_structure(self, source: str, target: str, language: str) -> float:
        """Compare structural elements (params, returns)."""
        # Count parameters
        source_params = self._count_parameters(source, language)
        target_params = self._count_parameters(target, language)
        param_diff = abs(source_params - target_params) / max(
            source_params, target_params, 1
        )

        # Count return statements
        source_returns = len(re.findall(r"\breturn\b", source))
        target_returns = len(re.findall(r"\breturn\b", target))
        return_diff = abs(source_returns - target_returns) / max(
            source_returns, target_returns, 1
        )

        return (param_diff + return_diff) / 2

    def _compare_logic_patterns(self, source: str, target: str, language: str) -> float:
        """Compare control flow patterns."""
        patterns = [
            r"\bif\b",
            r"\b(for|while)\b",
            r"\b(and|or|&&|\|\|)\b",
        ]

        diffs = []
        for pattern in patterns:
            src_count = len(re.findall(pattern, source, re.IGNORECASE))
            tgt_count = len(re.findall(pattern, target, re.IGNORECASE))
            if src_count > 0 or tgt_count > 0:
                diffs.append(abs(src_count - tgt_count) / max(src_count, tgt_count, 1))

        return sum(diffs) / max(len(diffs), 1)

    def _compare_error_handling(self, source: str, target: str, language: str) -> float:
        """Compare error handling patterns."""
        if language == "python":
            src_has_try = bool(re.search(r"\btry\b", source))
            tgt_has_try = bool(re.search(r"\btry\b", target))
            src_has_except = bool(re.search(r"\bexcept\b", source))
            tgt_has_except = bool(re.search(r"\bexcept\b", target))
        else:
            src_has_try = bool(re.search(r"\btry\b", source))
            tgt_has_try = bool(re.search(r"\btry\b", target))
            src_has_except = bool(re.search(r"\bcatch\b", source))
            tgt_has_except = bool(re.search(r"\bcatch\b", target))

        # Score: 1.0 if one has error handling and other doesn't
        if (src_has_try and src_has_except) != (tgt_has_try and tgt_has_except):
            return 1.0
        return 0.0

    def _compare_documentation(self, source: str, target: str) -> float:
        """Compare documentation presence."""
        # Check for docstrings/JSDoc
        src_has_doc = bool(
            re.search(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|/\*\*[\s\S]*?\*/', source)
        )
        tgt_has_doc = bool(
            re.search(r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|/\*\*[\s\S]*?\*/', target)
        )

        if src_has_doc != tgt_has_doc:
            return 0.5
        return 0.0

    def _analyze_drift(
        self,
        entity: ExtractedEntity,
        candidate: DriftCandidate,
        context: RuleContext,
    ) -> DriftAnalysis:
        """Perform detailed drift analysis."""
        drift_indicators = []
        scores = []

        source_content = entity.content
        target_content = candidate.content
        language = context.language

        # 1. Structural comparison
        structural_score = self._compare_structure(
            source_content, target_content, language
        )
        if structural_score > 0.2:
            drift_indicators.append(f"Structural divergence: {structural_score:.0%}")
        scores.append(structural_score)

        # 2. Logic pattern comparison
        logic_score = self._compare_logic_patterns(
            source_content, target_content, language
        )
        if logic_score > 0.2:
            drift_indicators.append(f"Logic pattern drift: {logic_score:.0%}")
        scores.append(logic_score)

        # 3. Error handling comparison
        error_score = self._compare_error_handling(
            source_content, target_content, language
        )
        if error_score > 0.3:
            drift_indicators.append("Error handling inconsistency")
        scores.append(error_score)

        # 4. Documentation comparison
        doc_score = self._compare_documentation(source_content, target_content)
        if doc_score > 0.3:
            drift_indicators.append("Documentation drift")
        scores.append(doc_score)

        # Calculate weighted drift score
        drift_score = (
            0.3 * scores[0]  # structural
            + 0.3 * scores[1]  # logic
            + 0.2 * scores[2]  # error handling
            + 0.2 * scores[3]  # documentation
        )

        # Determine significance
        drift_threshold = self._get_drift_threshold(context)
        is_significant = drift_score >= drift_threshold

        # Generate reconciliation hint
        reconciliation_hint = None
        if is_significant:
            if structural_score > 0.3:
                reconciliation_hint = (
                    f"'{entity.name}' and '{candidate.name}' have divergent "
                    f"signatures. Review parameter and return patterns."
                )
            elif logic_score > 0.3:
                reconciliation_hint = (
                    f"'{entity.name}' has different control flow than "
                    f"'{candidate.name}'. Consider harmonizing logic."
                )
            elif error_score > 0.5:
                reconciliation_hint = (
                    f"One of '{entity.name}' or '{candidate.name}' has "
                    f"error handling the other lacks. Consider adding to both."
                )
            else:
                reconciliation_hint = (
                    f"Review both '{entity.name}' and '{candidate.name}' "
                    f"for potential reconciliation."
                )

        return DriftAnalysis(
            source_name=entity.name,
            candidate_name=candidate.name,
            source_file=str(context.file_path),
            candidate_file=candidate.file_path,
            similarity_score=candidate.similarity_score,
            drift_score=drift_score,
            drift_indicators=drift_indicators,
            is_significant=is_significant,
            reconciliation_hint=reconciliation_hint,
        )

    def _create_drift_finding(
        self,
        entity: ExtractedEntity,
        analysis: DriftAnalysis,
        context: RuleContext,
    ) -> "Finding":
        """Create a finding for detected token drift."""
        # Get first few lines of both entities for evidence
        source_snippet = "\n".join(entity.content.split("\n")[:5])
        if len(entity.content.split("\n")) > 5:
            source_snippet += "\n..."

        evidence = [
            Evidence(
                description=(
                    f"Similar to '{analysis.candidate_name}' in "
                    f"{analysis.candidate_file} ({analysis.similarity_score:.0%} similar)"
                ),
                line_number=entity.start_line,
                code_snippet=source_snippet,
                data={
                    "source_name": analysis.source_name,
                    "candidate_name": analysis.candidate_name,
                    "candidate_file": analysis.candidate_file,
                    "similarity_score": analysis.similarity_score,
                    "drift_score": analysis.drift_score,
                    "drift_indicators": analysis.drift_indicators,
                },
            )
        ]

        remediation_hints = []
        if analysis.reconciliation_hint:
            remediation_hints.append(analysis.reconciliation_hint)
        remediation_hints.extend(
            [
                f"Check if '{analysis.candidate_name}' should be updated to match",
                "Consider extracting common logic to a shared helper function",
                "If differences are intentional, consider renaming to clarify purpose",
            ]
        )

        return self._create_finding(
            summary=(
                f"'{entity.name}' has drifted from similar "
                f"'{analysis.candidate_name}' ({analysis.drift_score:.0%} drift)"
            ),
            file_path=str(context.file_path),
            line_number=entity.start_line,
            end_line=entity.end_line,
            evidence=evidence,
            remediation_hints=remediation_hints,
            confidence=analysis.similarity_score * (1 - analysis.drift_score),
        )

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for token drift between similar entities.

        Args:
            context: RuleContext with file content and memory access

        Returns:
            List of findings for entities with significant drift
        """
        findings = []

        # Skip if no memory client available
        if context.memory_client is None or context.collection_name is None:
            return findings

        # Skip unsupported languages
        if context.language not in (self.supported_languages or []):
            return findings

        # Extract entities from changed code
        entities = self._extract_changed_entities(context)

        for entity in entities:
            # Find similar entities in memory
            candidates = self._find_similar_entities(entity, context)

            for candidate in candidates:
                # Analyze drift
                analysis = self._analyze_drift(entity, candidate, context)

                # Generate finding if significant drift detected
                if analysis.is_significant:
                    findings.append(
                        self._create_drift_finding(entity, analysis, context)
                    )

        return findings
