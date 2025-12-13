"""Unit tests for SARIF exporter."""

import json
import tempfile
from pathlib import Path

import pytest

from claude_indexer.ui.models import (
    Evidence,
    EvidenceType,
    Finding,
    Severity,
    SymbolKind,
    SymbolRef,
    UIAnalysisResult,
)
from claude_indexer.ui.reporters.sarif import SARIFConfig, SARIFExporter


class TestSARIFConfig:
    """Tests for SARIFConfig dataclass."""

    def test_default_config(self):
        """Test default SARIF config values."""
        config = SARIFConfig()

        assert config.tool_name == "ui-consistency-guard"
        assert config.tool_version == "1.0.0"
        assert config.include_baseline is False
        assert config.include_remediation is True

    def test_custom_config(self):
        """Test custom SARIF config values."""
        config = SARIFConfig(
            tool_name="custom-tool",
            tool_version="2.0.0",
            include_baseline=True,
        )

        assert config.tool_name == "custom-tool"
        assert config.tool_version == "2.0.0"
        assert config.include_baseline is True


class TestSARIFExporter:
    """Tests for SARIFExporter class."""

    @pytest.fixture
    def exporter(self):
        """Create a SARIFExporter instance."""
        return SARIFExporter()

    @pytest.fixture
    def sample_finding(self):
        """Create a sample finding for testing."""
        return Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.FAIL,
            confidence=0.95,
            summary="Hardcoded color #ff6b6b not in design tokens",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.STATIC,
                    description="Found in property 'background-color'",
                    data={"property": "background-color", "value": "#ff6b6b"},
                )
            ],
            remediation_hints=["Use token: --color-error-500 (#ef4444)"],
            source_ref=SymbolRef(
                file_path="src/Button.tsx",
                start_line=42,
                end_line=45,
                kind=SymbolKind.CSS,
            ),
        )

    def test_export_empty_result(self, exporter):
        """Test exporting empty result."""
        result = UIAnalysisResult(
            findings=[],
            files_analyzed=["test.tsx"],
            analysis_time_ms=50.0,
            tier=0,
        )

        sarif = exporter.export(result)

        assert sarif["$schema"] == "https://json.schemastore.org/sarif-2.1.0.json"
        assert sarif["version"] == "2.1.0"
        assert len(sarif["runs"]) == 1
        assert sarif["runs"][0]["results"] == []

    def test_export_with_finding(self, exporter, sample_finding):
        """Test exporting result with finding."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["src/Button.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)

        # Verify structure
        assert len(sarif["runs"]) == 1
        run = sarif["runs"][0]

        # Verify tool metadata
        assert run["tool"]["driver"]["name"] == "ui-consistency-guard"
        assert "rules" in run["tool"]["driver"]
        assert len(run["tool"]["driver"]["rules"]) == 1

        # Verify results
        assert len(run["results"]) == 1
        result_entry = run["results"][0]
        assert result_entry["ruleId"] == "COLOR.NON_TOKEN"
        assert result_entry["level"] == "error"

    def test_export_valid_json(self, exporter, sample_finding):
        """Test that export produces valid JSON."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        json_str = exporter.export_json(result)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert "$schema" in parsed
        assert "runs" in parsed

    def test_export_to_file(self, exporter, sample_finding):
        """Test exporting to file."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "results.sarif"
            exporter.export(result, output_path)

            # File should exist
            assert output_path.exists()

            # Should be valid JSON
            with open(output_path) as f:
                data = json.load(f)
                assert data["version"] == "2.1.0"

    def test_export_creates_parent_dirs(self, exporter, sample_finding):
        """Test that export creates parent directories."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "nested" / "dir" / "results.sarif"
            exporter.export(result, output_path)

            assert output_path.exists()

    def test_severity_mapping(self, exporter):
        """Test severity to SARIF level mapping."""
        # FAIL -> error
        fail_finding = Finding(
            rule_id="TEST",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
        )
        result1 = UIAnalysisResult(findings=[fail_finding])
        sarif1 = exporter.export(result1)
        assert sarif1["runs"][0]["results"][0]["level"] == "error"

        # WARN -> warning
        warn_finding = Finding(
            rule_id="TEST",
            severity=Severity.WARN,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
        )
        result2 = UIAnalysisResult(findings=[warn_finding])
        sarif2 = exporter.export(result2)
        assert sarif2["runs"][0]["results"][0]["level"] == "warning"

        # INFO -> note
        info_finding = Finding(
            rule_id="TEST",
            severity=Severity.INFO,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
        )
        result3 = UIAnalysisResult(findings=[info_finding])
        sarif3 = exporter.export(result3)
        assert sarif3["runs"][0]["results"][0]["level"] == "note"

    def test_rule_definitions(self, exporter, sample_finding):
        """Test rule definitions are included."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]

        assert len(rules) == 1
        rule = rules[0]
        assert rule["id"] == "COLOR.NON_TOKEN"
        assert "shortDescription" in rule
        assert "fullDescription" in rule
        assert "properties" in rule
        assert "tags" in rule["properties"]

    def test_location_info(self, exporter, sample_finding):
        """Test location information is included."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)
        result_entry = sarif["runs"][0]["results"][0]

        assert "locations" in result_entry
        location = result_entry["locations"][0]
        phys_loc = location["physicalLocation"]

        assert phys_loc["artifactLocation"]["uri"] == "src/Button.tsx"
        assert phys_loc["region"]["startLine"] == 42
        assert phys_loc["region"]["endLine"] == 45

    def test_location_single_line(self, exporter):
        """Test location for single-line finding."""
        finding = Finding(
            rule_id="TEST",
            severity=Severity.WARN,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=SymbolRef(
                file_path="test.tsx",
                start_line=10,
                end_line=10,  # Same line
                kind=SymbolKind.CSS,
            ),
        )

        result = UIAnalysisResult(findings=[finding])
        sarif = exporter.export(result)

        region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "region"
        ]

        # Should only have startLine when start == end
        assert region["startLine"] == 10
        assert "endLine" not in region

    def test_remediation_hints(self, exporter, sample_finding):
        """Test remediation hints are included."""
        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)
        result_entry = sarif["runs"][0]["results"][0]

        assert "fixes" in result_entry
        assert len(result_entry["fixes"]) == 1
        assert "Use token:" in result_entry["fixes"][0]["description"]["text"]

    def test_remediation_max_hints(self, exporter):
        """Test remediation hints are limited to 3."""
        finding = Finding(
            rule_id="TEST",
            severity=Severity.WARN,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            remediation_hints=[
                "Hint 1",
                "Hint 2",
                "Hint 3",
                "Hint 4",
                "Hint 5",
            ],
        )

        result = UIAnalysisResult(findings=[finding])
        sarif = exporter.export(result)

        fixes = sarif["runs"][0]["results"][0]["fixes"]
        assert len(fixes) == 3  # Max 3 hints

    def test_remediation_disabled(self, sample_finding):
        """Test remediation can be disabled."""
        config = SARIFConfig(include_remediation=False)
        exporter = SARIFExporter(config)

        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)
        result_entry = sarif["runs"][0]["results"][0]

        assert "fixes" not in result_entry

    def test_finding_properties(self, exporter, sample_finding):
        """Test finding properties are included."""
        sample_finding.is_new = True

        result = UIAnalysisResult(
            findings=[sample_finding],
            files_analyzed=["test.tsx"],
            analysis_time_ms=100.0,
            tier=0,
        )

        sarif = exporter.export(result)
        result_entry = sarif["runs"][0]["results"][0]

        assert "properties" in result_entry
        assert result_entry["properties"]["confidence"] == 0.95
        assert result_entry["properties"]["isNew"] is True

    def test_multiple_findings_same_rule(self, exporter):
        """Test multiple findings with same rule."""
        findings = [
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.FAIL,
                confidence=0.9,
                summary="Issue 1",
                evidence=[Evidence(EvidenceType.STATIC, "test")],
                source_ref=SymbolRef("a.tsx", 10, 10, SymbolKind.CSS),
            ),
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.FAIL,
                confidence=0.85,
                summary="Issue 2",
                evidence=[Evidence(EvidenceType.STATIC, "test")],
                source_ref=SymbolRef("b.tsx", 20, 20, SymbolKind.CSS),
            ),
        ]

        result = UIAnalysisResult(findings=findings)
        sarif = exporter.export(result)

        # Should have 1 rule definition but 2 results
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        results = sarif["runs"][0]["results"]

        assert len(rules) == 1
        assert len(results) == 2

    def test_multiple_findings_different_rules(self, exporter):
        """Test multiple findings with different rules."""
        findings = [
            Finding(
                rule_id="COLOR.NON_TOKEN",
                severity=Severity.FAIL,
                confidence=0.9,
                summary="Color issue",
                evidence=[Evidence(EvidenceType.STATIC, "test")],
            ),
            Finding(
                rule_id="SPACING.OFF_SCALE",
                severity=Severity.WARN,
                confidence=0.85,
                summary="Spacing issue",
                evidence=[Evidence(EvidenceType.STATIC, "test")],
            ),
        ]

        result = UIAnalysisResult(findings=findings)
        sarif = exporter.export(result)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        results = sarif["runs"][0]["results"]

        assert len(rules) == 2
        assert len(results) == 2

    def test_default_level_for_rules(self, exporter):
        """Test default SARIF level for rules."""
        # TOKEN rules should be error
        assert exporter._default_level_for_rule("COLOR.NON_TOKEN") == "error"
        assert exporter._default_level_for_rule("SPACING.OFF_SCALE") == "error"
        assert exporter._default_level_for_rule("IMPORTANT.NEW_USAGE") == "error"

        # Duplicate/outlier rules should be warning
        assert exporter._default_level_for_rule("STYLE.DUPLICATE_SET") == "warning"
        assert exporter._default_level_for_rule("ROLE.OUTLIER.BUTTON") == "warning"

    def test_unknown_rule_metadata(self, exporter):
        """Test handling of unknown rule ID."""
        finding = Finding(
            rule_id="CUSTOM.NEW_RULE",
            severity=Severity.WARN,
            confidence=0.8,
            summary="Custom rule violation",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
        )

        result = UIAnalysisResult(findings=[finding])
        sarif = exporter.export(result)

        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1

        rule = rules[0]
        assert rule["id"] == "CUSTOM.NEW_RULE"
        # Should have default name derived from rule ID (. replaced with space, title case)
        # "CUSTOM.NEW_RULE" -> "CUSTOM NEW_RULE" -> "Custom New_Rule"
        assert "Custom" in rule["name"]

    def test_finding_without_source_ref(self, exporter):
        """Test finding without source reference."""
        finding = Finding(
            rule_id="TEST",
            severity=Severity.INFO,
            confidence=0.7,
            summary="Global issue",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=None,  # No source ref
        )

        result = UIAnalysisResult(findings=[finding])
        sarif = exporter.export(result)

        result_entry = sarif["runs"][0]["results"][0]

        # Should not have locations
        assert "locations" not in result_entry

    def test_rule_index_assignment(self, exporter):
        """Test rule index is correctly assigned."""
        findings = [
            Finding(
                "RULE_A", Severity.FAIL, 0.9, "A", [Evidence(EvidenceType.STATIC, "")]
            ),
            Finding(
                "RULE_B", Severity.WARN, 0.8, "B", [Evidence(EvidenceType.STATIC, "")]
            ),
            Finding(
                "RULE_A", Severity.FAIL, 0.9, "A2", [Evidence(EvidenceType.STATIC, "")]
            ),
        ]

        result = UIAnalysisResult(findings=findings)
        sarif = exporter.export(result)

        results = sarif["runs"][0]["results"]

        # First and third should have same ruleIndex
        assert results[0]["ruleIndex"] == results[2]["ruleIndex"]
        # Second should be different
        assert results[1]["ruleIndex"] != results[0]["ruleIndex"]


class TestSARIFExporterWithCIResult:
    """Tests for SARIFExporter with CIAuditResult."""

    @pytest.fixture
    def exporter(self):
        """Create a SARIFExporter instance."""
        return SARIFExporter()

    @pytest.fixture
    def new_finding(self):
        """Create a new finding."""
        return Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.FAIL,
            confidence=0.95,
            summary="New hardcoded color",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=SymbolRef("new.tsx", 10, 10, SymbolKind.CSS),
            is_new=True,
        )

    @pytest.fixture
    def baseline_finding(self):
        """Create a baseline finding."""
        return Finding(
            rule_id="SPACING.OFF_SCALE",
            severity=Severity.WARN,
            confidence=0.8,
            summary="Existing spacing issue",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=SymbolRef("old.tsx", 20, 20, SymbolKind.CSS),
            is_new=False,
        )

    def test_export_excludes_baseline_by_default(
        self, exporter, new_finding, baseline_finding
    ):
        """Test that baseline findings are excluded by default."""
        # Use UIAnalysisResult for simplicity
        result = UIAnalysisResult(
            findings=[new_finding],
            baseline_findings=[baseline_finding],
        )

        sarif = exporter.export(result)

        # Should only have the new finding
        results = sarif["runs"][0]["results"]
        assert len(results) == 1
        assert results[0]["ruleId"] == "COLOR.NON_TOKEN"

    def test_export_includes_baseline_when_configured(
        self, new_finding, baseline_finding
    ):
        """Test that baseline findings can be included."""
        config = SARIFConfig(include_baseline=True)
        exporter = SARIFExporter(config)

        # This test would need CIAuditResult, but we can simulate with
        # a mock object that has new_findings and baseline_findings
        class MockCIResult:
            def __init__(self):
                self.new_findings = [new_finding]
                self.baseline_findings = [baseline_finding]

        result = MockCIResult()
        sarif = exporter.export(result)

        results = sarif["runs"][0]["results"]
        assert len(results) == 2

    def test_custom_tool_info(self, new_finding):
        """Test custom tool information."""
        config = SARIFConfig(
            tool_name="my-ui-checker",
            tool_version="3.0.0",
            tool_information_uri="https://example.com",
            tool_organization="My Org",
        )
        exporter = SARIFExporter(config)

        result = UIAnalysisResult(findings=[new_finding])
        sarif = exporter.export(result)

        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "my-ui-checker"
        assert driver["version"] == "3.0.0"
        assert driver["informationUri"] == "https://example.com"
        assert driver["organization"] == "My Org"
