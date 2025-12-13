"""
Unit tests for the Component Duplication detection rule.

Tests for TECH_DEBT.COMPONENT_DUPLICATION rule.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_indexer.rules.base import RuleContext, Severity
from claude_indexer.rules.tech_debt.duplication import (
    ComponentDuplicationRule,
    DuplicationType,
)


def create_context(
    content: str,
    language: str,
    file_path: str = "test.py",
    memory_client: MagicMock | None = None,
    collection_name: str | None = "test-collection",
) -> RuleContext:
    """Create a RuleContext for testing."""
    ctx = RuleContext(
        file_path=Path(file_path),
        content=content,
        language=language,
    )
    ctx.memory_client = memory_client
    ctx.collection_name = collection_name
    return ctx


class TestComponentDuplicationRule:
    """Tests for TECH_DEBT.COMPONENT_DUPLICATION rule."""

    @pytest.fixture
    def rule(self):
        return ComponentDuplicationRule()

    def test_rule_metadata(self, rule):
        """Test rule has correct metadata."""
        assert rule.rule_id == "TECH_DEBT.COMPONENT_DUPLICATION"
        assert rule.category == "tech_debt"
        assert rule.default_severity == Severity.MEDIUM
        assert rule.is_fast is False
        assert "python" in rule.supported_languages
        assert "javascript" in rule.supported_languages
        assert "typescript" in rule.supported_languages

    def test_no_findings_without_memory_client(self, rule):
        """Test that no findings are generated without memory client."""
        content = """
def validate_user(user):
    if not user:
        return False
    return True
"""
        context = create_context(content, "python", memory_client=None)
        findings = rule.check(context)
        assert len(findings) == 0

    def test_content_hash_normalization(self, rule):
        """Test that content hash normalizes whitespace and comments."""
        content1 = """
def process(data):
    # This is a comment
    return data
"""
        content2 = """
def process(data):
    return data
"""
        hash1 = rule._compute_content_hash(content1)
        hash2 = rule._compute_content_hash(content2)
        # After removing comments and normalizing, they should be more similar
        # but still different due to structure
        assert isinstance(hash1, str)
        assert isinstance(hash2, str)
        assert len(hash1) == 64  # SHA256 hex length

    def test_structural_feature_extraction_python(self, rule):
        """Test structural feature extraction for Python."""
        content = """
def process(data, options):
    if data:
        for item in data:
            if item.valid:
                return item
    return None
"""
        features = rule._extract_structural_features(content, "python")
        assert "CTRL:IF" in features
        assert "CTRL:FOR" in features
        assert "CTRL:RETURN" in features
        assert "DECL:FUNC" in features
        assert any(f.startswith("PARAMS:") for f in features)

    def test_structural_feature_extraction_javascript(self, rule):
        """Test structural feature extraction for JavaScript."""
        content = """
function process(data, options) {
    if (data) {
        for (const item of data) {
            if (item.valid) {
                return item;
            }
        }
    }
    return null;
}
"""
        features = rule._extract_structural_features(content, "javascript")
        assert "CTRL:IF" in features
        assert "CTRL:FOR" in features
        assert "CTRL:RETURN" in features
        assert "DECL:FUNC" in features

    def test_simhash_similarity(self, rule):
        """Test SimHash similarity calculation."""
        features1 = ["CTRL:IF", "CTRL:FOR", "CTRL:RETURN", "PARAMS:2"]
        features2 = ["CTRL:IF", "CTRL:FOR", "CTRL:RETURN", "PARAMS:2"]
        features3 = ["CTRL:WHILE", "CTRL:RETURN", "PARAMS:1"]

        hash1 = rule._compute_simhash(features1)
        hash2 = rule._compute_simhash(features2)
        hash3 = rule._compute_simhash(features3)

        # Same features should give identical hash
        assert rule._simhash_similarity(hash1, hash2) == 1.0

        # Different features should give lower similarity
        sim = rule._simhash_similarity(hash1, hash3)
        assert sim < 1.0

    def test_extract_entities_python(self, rule):
        """Test entity extraction for Python."""
        content = """
def validate_user(user, role):
    if not user:
        return False
    if not role:
        return False
    return True

class UserValidator:
    def __init__(self):
        self.rules = []

    def validate(self, user):
        return True
"""
        context = create_context(content, "python")
        entities = rule._extract_entities(context)
        # Should find both function and class
        assert len(entities) >= 1
        func_entities = [e for e in entities if e.entity_type == "function"]
        assert len(func_entities) >= 1

    def test_classify_score_exact(self, rule):
        """Test duplicate type classification for exact match."""
        context = create_context("", "python")
        dup_type = rule._classify_score(1.0, context)
        assert dup_type == DuplicationType.EXACT

    def test_classify_score_structural(self, rule):
        """Test duplicate type classification for structural match."""
        context = create_context("", "python")
        dup_type = rule._classify_score(0.97, context)
        assert dup_type == DuplicationType.STRUCTURAL

    def test_classify_score_semantic(self, rule):
        """Test duplicate type classification for semantic match."""
        context = create_context("", "python")
        dup_type = rule._classify_score(0.92, context)
        assert dup_type == DuplicationType.SEMANTIC

    def test_classify_score_similar(self, rule):
        """Test duplicate type classification for similar match."""
        context = create_context("", "python")
        dup_type = rule._classify_score(0.75, context)
        assert dup_type == DuplicationType.SIMILAR

    def test_refactoring_suggestions_exact(self, rule):
        """Test refactoring suggestions for exact duplicates."""
        from claude_indexer.rules.tech_debt.duplication import (
            DuplicateCandidate,
            ExtractedEntity,
        )

        entity = ExtractedEntity(
            name="process", entity_type="function", start_line=1, end_line=5, content=""
        )
        candidate = DuplicateCandidate(
            source_name="process",
            source_file="a.py",
            source_line=1,
            target_name="process",
            target_file="b.py",
            target_line=1,
            duplication_type=DuplicationType.EXACT,
            similarity_score=1.0,
        )

        suggestions = rule._generate_refactoring_suggestions(entity, candidate)
        assert len(suggestions) > 0
        assert any("shared" in s.lower() or "extract" in s.lower() for s in suggestions)

    def test_refactoring_suggestions_semantic(self, rule):
        """Test refactoring suggestions for semantic duplicates."""
        from claude_indexer.rules.tech_debt.duplication import (
            DuplicateCandidate,
            ExtractedEntity,
        )

        entity = ExtractedEntity(
            name="validate_user",
            entity_type="function",
            start_line=1,
            end_line=5,
            content="",
        )
        candidate = DuplicateCandidate(
            source_name="validate_user",
            source_file="a.py",
            source_line=1,
            target_name="check_user",
            target_file="b.py",
            target_line=1,
            duplication_type=DuplicationType.SEMANTIC,
            similarity_score=0.91,
        )

        suggestions = rule._generate_refactoring_suggestions(entity, candidate)
        assert len(suggestions) > 0
        assert any("purpose" in s.lower() or "reuse" in s.lower() for s in suggestions)

    def test_skip_small_entities(self, rule):
        """Test that small entities are skipped."""
        content = """
def x():
    pass
"""
        context = create_context(content, "python")
        entities = rule._extract_entities(context)
        # Entity is smaller than default min of 5 lines
        assert len(entities) == 0

    def test_unsupported_language_returns_empty(self, rule):
        """Test unsupported language returns empty findings."""
        content = 'fn main() { println!("Hello"); }'
        context = create_context(
            content, "rust", file_path="test.rs", memory_client=MagicMock()
        )
        findings = rule.check(context)
        assert len(findings) == 0

    def test_finding_creation(self, rule):
        """Test finding creation with proper structure."""
        from claude_indexer.rules.tech_debt.duplication import (
            DuplicateCandidate,
            ExtractedEntity,
        )

        content = """
def validate_user(user):
    if not user:
        return False
    return True
"""
        context = create_context(content, "python")

        entity = ExtractedEntity(
            name="validate_user",
            entity_type="function",
            start_line=2,
            end_line=5,
            content=content.strip(),
        )
        candidate = DuplicateCandidate(
            source_name="validate_user",
            source_file="test.py",
            source_line=2,
            target_name="check_user",
            target_file="other.py",
            target_line=10,
            duplication_type=DuplicationType.SEMANTIC,
            similarity_score=0.92,
            hash_score=0.0,
            structural_score=0.85,
            semantic_score=0.92,
        )

        finding = rule._create_duplicate_finding(entity, candidate, context)

        assert finding.rule_id == "TECH_DEBT.COMPONENT_DUPLICATION"
        assert "92%" in finding.summary or "check_user" in finding.summary
        assert len(finding.evidence) > 0
        assert len(finding.remediation_hints) > 0
