"""Unit tests for fix suggestion generator."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.hooks.fix_generator import (
    FixSuggestion,
    FixSuggestionGenerator,
    create_context_for_file,
)
from claude_indexer.rules.base import Finding, RuleContext, Severity
from claude_indexer.rules.fix import AutoFix


class TestFixSuggestion:
    """Tests for FixSuggestion dataclass."""

    @pytest.fixture
    def sample_finding(self):
        """Create a sample finding."""
        return Finding(
            rule_id="TEST.RULE",
            severity=Severity.HIGH,
            summary="Test issue",
            file_path="test.py",
            line_number=10,
            remediation_hints=["Fix the issue"],
        )

    def test_create_manual_suggestion(self, sample_finding):
        """Test creating a manual fix suggestion."""
        suggestion = FixSuggestion(
            finding=sample_finding,
            auto_fix=None,
            confidence=0.8,
            action="manual_required",
            description="Fix the issue manually",
        )

        assert suggestion.action == "manual_required"
        assert suggestion.auto_fix is None
        assert suggestion.confidence == 0.8

    def test_create_auto_suggestion(self, sample_finding):
        """Test creating an auto-fix suggestion."""
        auto_fix = AutoFix(
            finding=sample_finding,
            old_code="old_code",
            new_code="new_code",
            line_start=10,
            line_end=10,
            description="Replace code",
        )

        suggestion = FixSuggestion(
            finding=sample_finding,
            auto_fix=auto_fix,
            confidence=0.95,
            action="auto_available",
            description="Replace code",
            code_preview="- old_code\n+ new_code",
        )

        assert suggestion.action == "auto_available"
        assert suggestion.auto_fix is not None
        assert suggestion.code_preview is not None

    def test_to_dict_manual(self, sample_finding):
        """Test JSON serialization of manual suggestion."""
        suggestion = FixSuggestion(
            finding=sample_finding,
            action="manual_required",
            description="Fix manually",
            confidence=0.75,
        )

        data = suggestion.to_dict()

        assert data["rule_id"] == "TEST.RULE"
        assert data["file_path"] == "test.py"
        assert data["line_number"] == 10
        assert data["action"] == "manual_required"
        assert data["confidence"] == 0.75
        assert "auto_fix" not in data

    def test_to_dict_auto(self, sample_finding):
        """Test JSON serialization of auto suggestion."""
        auto_fix = AutoFix(
            finding=sample_finding,
            old_code="old",
            new_code="new",
            line_start=10,
            line_end=10,
            description="Replace",
        )

        suggestion = FixSuggestion(
            finding=sample_finding,
            auto_fix=auto_fix,
            action="auto_available",
            description="Replace",
            confidence=0.9,
            code_preview="preview",
        )

        data = suggestion.to_dict()

        assert data["action"] == "auto_available"
        assert "auto_fix" in data
        assert data["auto_fix"]["old_code"] == "old"
        assert data["auto_fix"]["new_code"] == "new"
        assert data["code_preview"] == "preview"


class TestFixSuggestionGenerator:
    """Tests for FixSuggestionGenerator."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock rule engine."""
        engine = MagicMock()
        engine._rules = {}
        return engine

    @pytest.fixture
    def generator(self, mock_engine):
        """Create a generator with mock engine."""
        return FixSuggestionGenerator(engine=mock_engine)

    @pytest.fixture
    def sample_finding(self):
        """Create a sample finding."""
        return Finding(
            rule_id="TEST.RULE",
            severity=Severity.HIGH,
            summary="Test issue",
            file_path="test.py",
            line_number=10,
            remediation_hints=["Fix this issue"],
            confidence=0.85,
        )

    @pytest.fixture
    def sample_context(self):
        """Create a sample rule context."""
        return RuleContext(
            file_path=Path("test.py"),
            content="line1\nline2\nline3",
            language="python",
        )

    def test_generate_empty_findings(self, generator):
        """Test generating suggestions for empty findings."""
        suggestions = generator.generate_suggestions([], {})
        assert suggestions == []

    def test_generate_manual_suggestion_no_rule(
        self, generator, sample_finding, sample_context
    ):
        """Test generating manual suggestion when rule not found."""
        context_map = {"test.py": sample_context}

        suggestions = generator.generate_suggestions([sample_finding], context_map)

        assert len(suggestions) == 1
        assert suggestions[0].action == "manual_required"
        assert suggestions[0].auto_fix is None

    def test_generate_manual_suggestion_no_autofix(
        self, generator, mock_engine, sample_finding, sample_context
    ):
        """Test generating manual suggestion when rule doesn't support auto-fix."""
        # Create mock rule without auto-fix
        mock_rule = MagicMock()
        mock_rule.can_auto_fix.return_value = False
        mock_engine._rules["TEST.RULE"] = mock_rule

        context_map = {"test.py": sample_context}

        suggestions = generator.generate_suggestions([sample_finding], context_map)

        assert len(suggestions) == 1
        assert suggestions[0].action == "manual_required"

    def test_generate_auto_suggestion(
        self, generator, mock_engine, sample_finding, sample_context
    ):
        """Test generating auto-fix suggestion."""
        # Create mock rule with auto-fix
        mock_rule = MagicMock()
        mock_rule.can_auto_fix.return_value = True
        mock_auto_fix = AutoFix(
            finding=sample_finding,
            old_code="old",
            new_code="new",
            line_start=10,
            line_end=10,
            description="Auto fix",
        )
        mock_rule.auto_fix.return_value = mock_auto_fix
        mock_engine._rules["TEST.RULE"] = mock_rule

        context_map = {"test.py": sample_context}

        suggestions = generator.generate_suggestions([sample_finding], context_map)

        assert len(suggestions) == 1
        assert suggestions[0].action == "auto_available"
        assert suggestions[0].auto_fix is not None
        assert suggestions[0].description == "Auto fix"

    def test_generate_handles_autofix_exception(
        self, generator, mock_engine, sample_finding, sample_context
    ):
        """Test graceful handling of auto-fix exceptions."""
        # Create mock rule that raises exception
        mock_rule = MagicMock()
        mock_rule.can_auto_fix.return_value = True
        mock_rule.auto_fix.side_effect = Exception("Auto-fix failed")
        mock_engine._rules["TEST.RULE"] = mock_rule

        context_map = {"test.py": sample_context}

        suggestions = generator.generate_suggestions([sample_finding], context_map)

        # Should fall back to manual suggestion
        assert len(suggestions) == 1
        assert suggestions[0].action == "manual_required"

    def test_generate_multiple_findings(self, generator, mock_engine):
        """Test generating suggestions for multiple findings."""
        findings = [
            Finding(
                rule_id="TEST.RULE_1",
                severity=Severity.HIGH,
                summary="Issue 1",
                file_path="test.py",
                line_number=10,
                remediation_hints=["Fix 1"],
            ),
            Finding(
                rule_id="TEST.RULE_2",
                severity=Severity.MEDIUM,
                summary="Issue 2",
                file_path="test.py",
                line_number=20,
                remediation_hints=["Fix 2"],
            ),
        ]

        context = RuleContext(
            file_path=Path("test.py"),
            content="content",
            language="python",
        )
        context_map = {"test.py": context}

        suggestions = generator.generate_suggestions(findings, context_map)

        assert len(suggestions) == 2

    def test_generate_missing_context(self, generator, sample_finding):
        """Test generating suggestion when context is missing."""
        suggestions = generator.generate_suggestions([sample_finding], {})

        # Should still produce manual suggestion
        assert len(suggestions) == 1
        assert suggestions[0].action == "manual_required"

    def test_rule_lookup_caching(self, generator, mock_engine, sample_finding):
        """Test that rule lookup is cached."""
        mock_rule = MagicMock()
        mock_rule.can_auto_fix.return_value = False
        mock_engine._rules["TEST.RULE"] = mock_rule

        # Look up same rule twice
        rule1 = generator._get_rule_for_finding(sample_finding)
        rule2 = generator._get_rule_for_finding(sample_finding)

        assert rule1 is rule2
        assert "TEST.RULE" in generator._rule_cache

    def test_confidence_propagation(
        self, generator, mock_engine, sample_finding, sample_context
    ):
        """Test that finding confidence is propagated to suggestion."""
        sample_finding.confidence = 0.92

        # Create mock rule with auto-fix
        mock_rule = MagicMock()
        mock_rule.can_auto_fix.return_value = True
        mock_auto_fix = AutoFix(
            finding=sample_finding,
            old_code="old",
            new_code="new",
            line_start=10,
            line_end=10,
            description="Fix",
        )
        mock_rule.auto_fix.return_value = mock_auto_fix
        mock_engine._rules["TEST.RULE"] = mock_rule

        context_map = {"test.py": sample_context}

        suggestions = generator.generate_suggestions([sample_finding], context_map)

        assert suggestions[0].confidence == 0.92


class TestCreateContextForFile:
    """Tests for create_context_for_file helper."""

    def test_create_context_with_content(self, tmp_path):
        """Test creating context with provided content."""
        file_path = tmp_path / "test.py"

        context = create_context_for_file(file_path, content="test content")

        assert context.content == "test content"
        assert context.file_path == file_path
        assert context.language == "python"

    def test_create_context_reads_file(self, tmp_path):
        """Test creating context by reading file."""
        file_path = tmp_path / "test.py"
        file_path.write_text("file content")

        context = create_context_for_file(file_path)

        assert context.content == "file content"
        assert context.language == "python"

    def test_create_context_missing_file(self, tmp_path):
        """Test creating context for missing file."""
        file_path = tmp_path / "nonexistent.py"

        context = create_context_for_file(file_path)

        assert context.content == ""
        assert context.language == "python"

    def test_create_context_different_languages(self, tmp_path):
        """Test creating context for different file types."""
        js_file = tmp_path / "test.js"
        ts_file = tmp_path / "test.ts"

        js_context = create_context_for_file(js_file, content="")
        ts_context = create_context_for_file(ts_file, content="")

        assert js_context.language == "javascript"
        assert ts_context.language == "typescript"
