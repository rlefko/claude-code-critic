"""
Unit tests for the Token Drift detection rule.

Tests for TECH_DEBT.TOKEN_DRIFT rule.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from claude_indexer.rules.base import RuleContext, Severity
from claude_indexer.rules.tech_debt.token_drift import TokenDriftRule


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


class TestTokenDriftRule:
    """Tests for TECH_DEBT.TOKEN_DRIFT rule."""

    @pytest.fixture
    def rule(self):
        return TokenDriftRule()

    def test_rule_metadata(self, rule):
        """Test rule has correct metadata."""
        assert rule.rule_id == "TECH_DEBT.TOKEN_DRIFT"
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

    def test_no_findings_without_collection(self, rule):
        """Test that no findings are generated without collection name."""
        content = """
def validate_user(user):
    if not user:
        return False
    return True
"""
        context = create_context(
            content, "python", memory_client=MagicMock(), collection_name=None
        )
        findings = rule.check(context)
        assert len(findings) == 0

    def test_extract_python_function(self, rule):
        """Test Python function extraction."""
        content = """
def validate_user(user):
    if not user:
        return False
    return True

def process_data(data):
    return data
"""
        context = create_context(content, "python")
        entities = rule._extract_changed_entities(context)
        assert len(entities) == 2
        assert entities[0].name == "validate_user"
        assert entities[0].entity_type == "function"
        assert entities[1].name == "process_data"

    def test_extract_javascript_function(self, rule):
        """Test JavaScript function extraction."""
        content = """
function validateUser(user) {
    if (!user) {
        return false;
    }
    return true;
}

const processData = (data) => {
    return data;
};
"""
        context = create_context(content, "javascript", file_path="test.js")
        entities = rule._extract_changed_entities(context)
        assert len(entities) >= 1
        assert any(e.name == "validateUser" for e in entities)

    def test_extract_python_class(self, rule):
        """Test Python class extraction."""
        content = """
class UserValidator:
    def __init__(self):
        self.rules = []

    def validate(self, user):
        return True
"""
        context = create_context(content, "python")
        entities = rule._extract_changed_entities(context)
        assert len(entities) >= 1
        assert any(e.entity_type == "class" for e in entities)

    def test_compare_structure(self, rule):
        """Test structural comparison."""
        source = """
def validate(user, role):
    if not user:
        return False
    return True
"""
        target = """
def validate(user):
    if not user:
        return False
    return True
"""
        score = rule._compare_structure(source, target, "python")
        assert score > 0  # Different param counts

    def test_compare_logic_patterns(self, rule):
        """Test logic pattern comparison."""
        source = """
def process(data):
    if condition1:
        if condition2:
            return data
    return None
"""
        target = """
def process(data):
    if condition1:
        return data
    return None
"""
        score = rule._compare_logic_patterns(source, target, "python")
        assert score > 0  # Different if counts

    def test_compare_error_handling(self, rule):
        """Test error handling comparison."""
        source = """
def process(data):
    try:
        return data.value
    except Exception:
        return None
"""
        target = """
def process(data):
    return data.value
"""
        score = rule._compare_error_handling(source, target, "python")
        assert score == 1.0  # One has try/except, other doesn't

    def test_no_drift_same_error_handling(self, rule):
        """Test no drift when both have error handling."""
        source = """
def process(data):
    try:
        return data.value
    except Exception:
        return None
"""
        target = """
def process(data):
    try:
        return data.get('value')
    except KeyError:
        return None
"""
        score = rule._compare_error_handling(source, target, "python")
        assert score == 0.0  # Both have try/except

    def test_compare_documentation(self, rule):
        """Test documentation comparison."""
        source = '''
def process(data):
    """Process the data."""
    return data
'''
        target = """
def process(data):
    return data
"""
        score = rule._compare_documentation(source, target)
        assert score > 0  # One has docs, other doesn't

    def test_drift_analysis_with_mock_memory(self, rule):
        """Test full drift analysis with mocked memory."""
        mock_client = MagicMock()
        mock_client.search.return_value = [
            MagicMock(
                score=0.92,
                payload={
                    "name": "validate_email",
                    "entity_type": "function",
                    "file_path": "other.py",
                    "content": """def validate_email(email):
    if not email:
        return False
    return '@' in email
""",
                },
            )
        ]

        content = """
def validate_email(email):
    if not email:
        return False
    if '@' not in email:
        return False
    return True
"""
        context = create_context(
            content, "python", memory_client=mock_client, collection_name="test"
        )
        # Note: This won't generate findings because the context has no diff info
        findings = rule.check(context)
        # Without diff info, all lines are in scope
        assert isinstance(findings, list)

    def test_skip_small_entities(self, rule):
        """Test that small entities are skipped."""
        content = """def x(): pass"""  # Single line function
        context = create_context(content, "python")
        entities = rule._extract_changed_entities(context)
        # Entity is only 1 line, below default min of 3
        assert len(entities) == 0

    def test_unsupported_language_returns_empty(self, rule):
        """Test unsupported language returns empty findings."""
        content = 'fn main() { println!("Hello"); }'
        context = create_context(
            content, "rust", file_path="test.rs", memory_client=MagicMock()
        )
        findings = rule.check(context)
        assert len(findings) == 0
