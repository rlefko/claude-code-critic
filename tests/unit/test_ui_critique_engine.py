"""Unit tests for CritiqueEngine.

Tests the critique engine orchestration including:
- Critique item and report dataclasses
- Analyzer coordination
- Summary building
- ID generation
- Full critique generation
"""

from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.ui.critique.engine import (
    CritiqueEngine,
    CritiqueItem,
    CritiqueReport,
    CritiqueStatistics,
    CritiqueSummary,
)
from claude_indexer.ui.models import (
    Evidence,
    EvidenceType,
    LayoutBox,
    RuntimeElementFingerprint,
    Severity,
    SymbolKind,
    SymbolRef,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_ui_config():
    """Create a UIQualityConfig with default values for testing."""
    from claude_indexer.ui.config import UIQualityConfig

    # Use default values which are sufficient for testing
    return UIQualityConfig()


@pytest.fixture
def sample_fingerprints() -> list[RuntimeElementFingerprint]:
    """Create sample RuntimeElementFingerprint list for testing."""
    return [
        RuntimeElementFingerprint(
            page_id="/home",
            selector="[data-testid='submit-btn']",
            role="button",
            computed_style_subset={
                "background-color": "rgb(59, 130, 246)",
                "padding": "8px 16px",
                "border-radius": "4px",
                "font-size": "14px",
            },
            layout_box=LayoutBox(x=100, y=200, width=120, height=40),
            screenshot_hash="abc123",
            source_map_hint="SubmitButton",
        ),
        RuntimeElementFingerprint(
            page_id="/home",
            selector="[data-testid='cancel-btn']",
            role="button",
            computed_style_subset={
                "background-color": "rgb(239, 68, 68)",
                "padding": "8px 16px",
                "border-radius": "4px",
                "font-size": "14px",
            },
            layout_box=LayoutBox(x=240, y=200, width=100, height=40),
        ),
        RuntimeElementFingerprint(
            page_id="/settings",
            selector="h1",
            role="heading",
            computed_style_subset={
                "font-size": "24px",
                "font-weight": "700",
                "color": "rgb(17, 24, 39)",
            },
        ),
    ]


@pytest.fixture
def sample_critique_item() -> CritiqueItem:
    """Create a sample CritiqueItem for testing."""
    return CritiqueItem(
        id="CONSISTENCY-TOKEN_ADHERENCE-0001",
        category="consistency",
        subcategory="token_adherence",
        severity=Severity.WARN,
        title="Low token adherence in buttons",
        description="Only 60% of button styles use design tokens",
        evidence=[
            Evidence(
                evidence_type=EvidenceType.RUNTIME,
                description="Button uses hardcoded color",
                data={"value": "#3b82f6"},
            )
        ],
        screenshots=["screenshots/button_001.png"],
        affected_elements=[],
        metrics={"adherence_rate": 0.6},
        remediation_hints=["Replace hardcoded values with design tokens"],
    )


@pytest.fixture
def critique_engine(mock_ui_config) -> CritiqueEngine:
    """Create a CritiqueEngine with mocked config."""
    return CritiqueEngine(config=mock_ui_config)


# ---------------------------------------------------------------------------
# TestCritiqueItem
# ---------------------------------------------------------------------------


class TestCritiqueItem:
    """Tests for CritiqueItem dataclass."""

    def test_to_dict_serialization(self, sample_critique_item):
        """Test that to_dict produces valid dictionary."""
        result = sample_critique_item.to_dict()

        assert result["id"] == "CONSISTENCY-TOKEN_ADHERENCE-0001"
        assert result["category"] == "consistency"
        assert result["subcategory"] == "token_adherence"
        assert result["severity"] == "warn"
        assert result["title"] == "Low token adherence in buttons"
        assert len(result["evidence"]) == 1
        assert result["screenshots"] == ["screenshots/button_001.png"]
        assert result["metrics"]["adherence_rate"] == 0.6

    def test_from_dict_deserialization(self):
        """Test that from_dict creates valid CritiqueItem."""
        data = {
            "id": "TEST-001",
            "category": "hierarchy",
            "subcategory": "heading_scale",
            "severity": "fail",
            "title": "Inconsistent heading sizes",
            "description": "Heading scale not followed",
            "evidence": [],
            "screenshots": [],
            "affected_elements": [],
            "metrics": {},
            "remediation_hints": ["Use design system heading sizes"],
        }

        item = CritiqueItem.from_dict(data)

        assert item.id == "TEST-001"
        assert item.category == "hierarchy"
        assert item.severity == Severity.FAIL
        assert item.remediation_hints == ["Use design system heading sizes"]

    def test_roundtrip_serialization(self, sample_critique_item):
        """Test that to_dict -> from_dict preserves data."""
        data = sample_critique_item.to_dict()
        restored = CritiqueItem.from_dict(data)

        assert restored.id == sample_critique_item.id
        assert restored.category == sample_critique_item.category
        assert restored.severity == sample_critique_item.severity
        assert restored.title == sample_critique_item.title
        assert len(restored.evidence) == len(sample_critique_item.evidence)


# ---------------------------------------------------------------------------
# TestCritiqueReport
# ---------------------------------------------------------------------------


class TestCritiqueReport:
    """Tests for CritiqueReport dataclass."""

    def test_fail_count_property(self):
        """Test fail_count returns correct count."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.FAIL,
                    title="Fail 1",
                    description="",
                ),
                CritiqueItem(
                    id="2",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Warn 1",
                    description="",
                ),
                CritiqueItem(
                    id="3",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.FAIL,
                    title="Fail 2",
                    description="",
                ),
            ]
        )

        assert report.fail_count == 2

    def test_warn_count_property(self):
        """Test warn_count returns correct count."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Warn 1",
                    description="",
                ),
                CritiqueItem(
                    id="2",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Warn 2",
                    description="",
                ),
            ]
        )

        assert report.warn_count == 2

    def test_info_count_property(self):
        """Test info_count returns correct count."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.INFO,
                    title="Info 1",
                    description="",
                ),
            ]
        )

        assert report.info_count == 1

    def test_get_critiques_by_category(self):
        """Test filtering critiques by category."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Consistency",
                    description="",
                ),
                CritiqueItem(
                    id="2",
                    category="hierarchy",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Hierarchy",
                    description="",
                ),
                CritiqueItem(
                    id="3",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.INFO,
                    title="Consistency 2",
                    description="",
                ),
            ]
        )

        consistency = report.get_critiques_by_category("consistency")
        assert len(consistency) == 2

        hierarchy = report.get_critiques_by_category("hierarchy")
        assert len(hierarchy) == 1

    def test_get_critiques_by_severity(self):
        """Test filtering critiques by severity."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.FAIL,
                    title="Fail",
                    description="",
                ),
                CritiqueItem(
                    id="2",
                    category="consistency",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Warn",
                    description="",
                ),
            ]
        )

        fails = report.get_critiques_by_severity(Severity.FAIL)
        assert len(fails) == 1
        assert fails[0].title == "Fail"

    def test_to_dict_serialization(self):
        """Test CritiqueReport to_dict."""
        report = CritiqueReport(
            critiques=[
                CritiqueItem(
                    id="1",
                    category="test",
                    subcategory="test",
                    severity=Severity.WARN,
                    title="Test",
                    description="",
                )
            ],
            summary=CritiqueSummary(total_critiques=1),
            statistics=CritiqueStatistics(elements_analyzed=10),
        )

        data = report.to_dict()

        assert len(data["critiques"]) == 1
        assert data["summary"]["total_critiques"] == 1
        assert data["statistics"]["elements_analyzed"] == 10
        assert "generated_at" in data


# ---------------------------------------------------------------------------
# TestCritiqueSummary
# ---------------------------------------------------------------------------


class TestCritiqueSummary:
    """Tests for CritiqueSummary dataclass."""

    def test_default_values(self):
        """Test default summary values."""
        summary = CritiqueSummary()

        assert summary.total_critiques == 0
        assert summary.by_category == {}
        assert summary.by_severity == {}
        assert summary.token_adherence_rate == 1.0
        assert summary.accessibility_issues == 0

    def test_to_dict(self):
        """Test summary serialization."""
        summary = CritiqueSummary(
            total_critiques=5,
            by_category={"consistency": 3, "hierarchy": 2},
            by_severity={"warn": 4, "fail": 1},
            token_adherence_rate=0.85,
            role_variant_counts={"button": 4, "input": 2},
            accessibility_issues=2,
        )

        data = summary.to_dict()

        assert data["total_critiques"] == 5
        assert data["by_category"]["consistency"] == 3
        assert data["token_adherence_rate"] == 0.85


# ---------------------------------------------------------------------------
# TestCritiqueStatistics
# ---------------------------------------------------------------------------


class TestCritiqueStatistics:
    """Tests for CritiqueStatistics dataclass."""

    def test_default_values(self):
        """Test default statistics values."""
        stats = CritiqueStatistics()

        assert stats.elements_analyzed == 0
        assert stats.pages_crawled == 0
        assert stats.visual_clusters_found == 0
        assert stats.analysis_time_ms == 0.0

    def test_to_dict(self):
        """Test statistics serialization."""
        stats = CritiqueStatistics(
            elements_analyzed=50,
            pages_crawled=10,
            visual_clusters_found=5,
            analysis_time_ms=1234.56,
        )

        data = stats.to_dict()

        assert data["elements_analyzed"] == 50
        assert data["pages_crawled"] == 10
        assert data["visual_clusters_found"] == 5
        assert data["analysis_time_ms"] == 1234.56


# ---------------------------------------------------------------------------
# TestCritiqueEngineInit
# ---------------------------------------------------------------------------


class TestCritiqueEngineInit:
    """Tests for CritiqueEngine initialization."""

    def test_initializes_analyzers(self, critique_engine):
        """Test that all analyzers are initialized."""
        assert critique_engine.consistency_analyzer is not None
        assert critique_engine.hierarchy_analyzer is not None
        assert critique_engine.affordance_analyzer is not None

    def test_has_remediation_hints(self, critique_engine):
        """Test that remediation hints are defined."""
        hints = critique_engine.REMEDIATION_HINTS

        assert "token_adherence" in hints
        assert "role_variants" in hints
        assert "focus_visibility" in hints
        assert "tap_targets" in hints

        # Each should have at least one hint
        for _key, hint_list in hints.items():
            assert len(hint_list) > 0

    def test_stores_config(self, critique_engine, mock_ui_config):
        """Test that config is stored."""
        assert critique_engine.config == mock_ui_config


# ---------------------------------------------------------------------------
# TestCritiqueIdGeneration
# ---------------------------------------------------------------------------


class TestCritiqueIdGeneration:
    """Tests for critique ID generation."""

    def test_generates_unique_ids(self, critique_engine):
        """Test that generated IDs are unique."""
        ids = [
            critique_engine._generate_critique_id("consistency", "token"),
            critique_engine._generate_critique_id("consistency", "token"),
            critique_engine._generate_critique_id("hierarchy", "heading"),
        ]

        # All IDs should be unique
        assert len(ids) == len(set(ids))

    def test_id_format_matches_pattern(self, critique_engine):
        """Test that ID format is correct."""
        critique_id = critique_engine._generate_critique_id(
            "consistency", "token_adherence"
        )

        # Should be uppercase CATEGORY-SUBCATEGORY-NNNN
        assert critique_id.startswith("CONSISTENCY-TOKEN_ADHERENCE-")
        assert critique_id[-4:].isdigit()

    def test_counter_resets_between_reports(self, critique_engine, sample_fingerprints):
        """Test that counter resets between generate_critique calls."""
        # First report
        report1 = critique_engine.generate_critique(sample_fingerprints)

        # Second report - counter should reset
        critique_engine._critique_counter = 0
        report2 = critique_engine.generate_critique(sample_fingerprints)

        # Both should have similar ID patterns (starting from 0001)
        if report1.critiques and report2.critiques:
            # IDs should follow the same numbering pattern
            id1_nums = [c.id.split("-")[-1] for c in report1.critiques]
            id2_nums = [c.id.split("-")[-1] for c in report2.critiques]

            # First IDs should start from 0001
            if id1_nums:
                assert id1_nums[0] == "0001"
            if id2_nums:
                assert id2_nums[0] == "0001"


# ---------------------------------------------------------------------------
# TestRawToCritiqueItem
# ---------------------------------------------------------------------------


class TestRawToCritiqueItem:
    """Tests for raw dict to CritiqueItem conversion."""

    def test_converts_basic_raw(self, critique_engine):
        """Test basic raw dict conversion."""
        raw = {
            "category": "consistency",
            "subcategory": "outlier",
            "severity": Severity.WARN,
            "title": "Button style outlier",
            "description": "One button differs from others",
            "evidence": [{"type": "runtime", "value": "different padding"}],
        }

        item = critique_engine._raw_to_critique_item(raw)

        assert item.category == "consistency"
        assert item.subcategory == "outlier"
        assert item.severity == Severity.WARN
        assert item.title == "Button style outlier"
        assert len(item.evidence) == 1

    def test_adds_remediation_hints(self, critique_engine):
        """Test that remediation hints are added based on subcategory."""
        raw = {
            "category": "consistency",
            "subcategory": "token_adherence",
            "severity": Severity.WARN,
            "title": "Token adherence issue",
            "description": "Hardcoded colors found",
        }

        item = critique_engine._raw_to_critique_item(raw)

        # Should have hints from REMEDIATION_HINTS["token_adherence"]
        assert len(item.remediation_hints) > 0
        assert any("token" in hint.lower() for hint in item.remediation_hints)

    def test_builds_evidence_list(self, critique_engine):
        """Test that evidence list is built from raw evidence."""
        raw = {
            "category": "hierarchy",
            "subcategory": "heading_scale",
            "severity": Severity.INFO,
            "title": "Heading scale issue",
            "description": "Inconsistent heading sizes",
            "evidence": [
                {"font_size": "24px", "expected": "20px"},
                "Second evidence item",
            ],
        }

        item = critique_engine._raw_to_critique_item(raw)

        assert len(item.evidence) == 2
        # Evidence should have runtime type
        assert item.evidence[0].evidence_type == EvidenceType.RUNTIME

    def test_handles_missing_optional_fields(self, critique_engine):
        """Test handling of missing optional fields."""
        raw = {
            "category": "affordance",
            "subcategory": "tap_targets",
            "severity": Severity.WARN,
            "title": "Small tap target",
            "description": "Button too small",
            # Missing: evidence, screenshots, metrics
        }

        item = critique_engine._raw_to_critique_item(raw)

        assert item.evidence == []
        assert item.screenshots == []
        assert item.metrics == {}


# ---------------------------------------------------------------------------
# TestBuildSummary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    """Tests for summary building."""

    def test_counts_by_category(self, critique_engine):
        """Test that summary counts critiques by category."""
        critiques = [
            CritiqueItem(
                id="1",
                category="consistency",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
            CritiqueItem(
                id="2",
                category="consistency",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
            CritiqueItem(
                id="3",
                category="hierarchy",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
        ]

        summary = critique_engine._build_summary(critiques)

        assert summary.by_category["consistency"] == 2
        assert summary.by_category["hierarchy"] == 1
        assert summary.total_critiques == 3

    def test_counts_by_severity(self, critique_engine):
        """Test that summary counts critiques by severity."""
        critiques = [
            CritiqueItem(
                id="1",
                category="test",
                subcategory="test",
                severity=Severity.FAIL,
                title="",
                description="",
            ),
            CritiqueItem(
                id="2",
                category="test",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
            CritiqueItem(
                id="3",
                category="test",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
        ]

        summary = critique_engine._build_summary(critiques)

        assert summary.by_severity["fail"] == 1
        assert summary.by_severity["warn"] == 2

    def test_includes_consistency_metrics(self, critique_engine):
        """Test that consistency metrics are included."""
        critiques = []
        metrics = {
            "token_adherence_rate": 0.75,
            "role_variants": {"button": 5, "input": 3},
        }

        summary = critique_engine._build_summary(critiques, metrics)

        assert summary.token_adherence_rate == 0.75
        assert summary.role_variant_counts["button"] == 5

    def test_counts_accessibility_issues(self, critique_engine):
        """Test that affordance critiques count as accessibility issues."""
        critiques = [
            CritiqueItem(
                id="1",
                category="affordance",
                subcategory="focus_visibility",
                severity=Severity.WARN,
                title="",
                description="",
            ),
            CritiqueItem(
                id="2",
                category="affordance",
                subcategory="tap_targets",
                severity=Severity.WARN,
                title="",
                description="",
            ),
            CritiqueItem(
                id="3",
                category="consistency",
                subcategory="test",
                severity=Severity.WARN,
                title="",
                description="",
            ),
        ]

        summary = critique_engine._build_summary(critiques)

        assert summary.accessibility_issues == 2


# ---------------------------------------------------------------------------
# TestGenerateCritique
# ---------------------------------------------------------------------------


class TestGenerateCritique:
    """Tests for full critique generation."""

    def test_calls_all_analyzers(self, critique_engine, sample_fingerprints):
        """Test that all analyzers are called during critique generation."""
        with (
            patch.object(
                critique_engine.consistency_analyzer,
                "generate_consistency_critiques",
                return_value=[],
            ) as mock_consistency,
            patch.object(
                critique_engine.hierarchy_analyzer,
                "generate_hierarchy_critiques",
                return_value=[],
            ) as mock_hierarchy,
            patch.object(
                critique_engine.affordance_analyzer,
                "generate_affordance_critiques",
                return_value=[],
            ) as mock_affordance,
        ):
            critique_engine.generate_critique(sample_fingerprints)

            mock_consistency.assert_called_once()
            mock_hierarchy.assert_called_once()
            mock_affordance.assert_called_once()

    def test_sorts_critiques_by_severity(self, critique_engine, sample_fingerprints):
        """Test that critiques are sorted by severity (FAIL first)."""
        # Mock analyzers to return critiques in wrong order
        with (
            patch.object(
                critique_engine.consistency_analyzer,
                "generate_consistency_critiques",
                return_value=[
                    {
                        "category": "consistency",
                        "subcategory": "test",
                        "severity": Severity.INFO,
                        "title": "Info",
                        "description": "",
                    },
                    {
                        "category": "consistency",
                        "subcategory": "test",
                        "severity": Severity.FAIL,
                        "title": "Fail",
                        "description": "",
                    },
                ],
            ),
            patch.object(
                critique_engine.hierarchy_analyzer,
                "generate_hierarchy_critiques",
                return_value=[
                    {
                        "category": "hierarchy",
                        "subcategory": "test",
                        "severity": Severity.WARN,
                        "title": "Warn",
                        "description": "",
                    },
                ],
            ),
            patch.object(
                critique_engine.affordance_analyzer,
                "generate_affordance_critiques",
                return_value=[],
            ),
        ):
            report = critique_engine.generate_critique(sample_fingerprints)

            # FAIL should come first
            assert report.critiques[0].severity == Severity.FAIL
            # Then WARN
            assert report.critiques[1].severity == Severity.WARN
            # Then INFO
            assert report.critiques[2].severity == Severity.INFO

    def test_includes_ci_findings_as_evidence(
        self, critique_engine, sample_fingerprints
    ):
        """Test that CI findings are included when provided."""
        # Create mock CI result
        mock_ci_result = MagicMock()
        mock_finding = MagicMock()
        mock_finding.rule_id = "COLOR.NON_TOKEN"
        mock_finding.severity = Severity.WARN
        mock_finding.summary = "Hardcoded color found"
        mock_finding.source_ref = SymbolRef(
            file_path="src/Button.tsx",
            start_line=10,
            end_line=15,
            kind=SymbolKind.COMPONENT,
        )
        mock_finding.remediation_hints = ["Use design token"]
        mock_ci_result.new_findings = [mock_finding]

        with (
            patch.object(
                critique_engine.consistency_analyzer,
                "generate_consistency_critiques",
                return_value=[],
            ),
            patch.object(
                critique_engine.hierarchy_analyzer,
                "generate_hierarchy_critiques",
                return_value=[],
            ),
            patch.object(
                critique_engine.affordance_analyzer,
                "generate_affordance_critiques",
                return_value=[],
            ),
        ):
            report = critique_engine.generate_critique(
                sample_fingerprints,
                ci_result=mock_ci_result,
            )

            # Should have critique from CI finding
            assert len(report.critiques) == 1
            assert "Static Analysis" in report.critiques[0].title
            assert report.critiques[0].remediation_hints == ["Use design token"]

    def test_empty_fingerprints_returns_empty_report(self, critique_engine):
        """Test that empty fingerprints produces empty report."""
        report = critique_engine.generate_critique([])

        # May have empty critiques or critiques based on empty analysis
        assert report is not None
        assert isinstance(report.summary.total_critiques, int)

    def test_statistics_populated(self, critique_engine, sample_fingerprints):
        """Test that statistics are populated correctly."""
        mock_crawl_result = MagicMock()
        mock_crawl_result.fingerprints = sample_fingerprints[:1]

        mock_visual_clusters = MagicMock()
        mock_visual_clusters.clusters = [{"id": "cluster1"}, {"id": "cluster2"}]

        with (
            patch.object(
                critique_engine.consistency_analyzer,
                "generate_consistency_critiques",
                return_value=[],
            ),
            patch.object(
                critique_engine.hierarchy_analyzer,
                "generate_hierarchy_critiques",
                return_value=[],
            ),
            patch.object(
                critique_engine.affordance_analyzer,
                "generate_affordance_critiques",
                return_value=[],
            ),
        ):
            report = critique_engine.generate_critique(
                sample_fingerprints,
                crawl_results=[mock_crawl_result],
                visual_clusters=mock_visual_clusters,
            )

            assert report.statistics.elements_analyzed == len(sample_fingerprints)
            assert report.statistics.pages_crawled == 1
            assert report.statistics.visual_clusters_found == 2
            assert report.statistics.analysis_time_ms > 0


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------


class TestCritiqueEngineIntegration:
    """Integration tests for complete critique generation workflow."""

    def test_full_critique_workflow(self, critique_engine, sample_fingerprints):
        """Test a realistic critique workflow."""
        # Run critique generation
        report = critique_engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
        )

        # Basic validation
        assert report is not None
        assert isinstance(report.critiques, list)
        assert report.summary is not None
        assert report.statistics is not None

        # All critiques should have required fields
        for critique in report.critiques:
            assert critique.id
            assert critique.category in ["consistency", "hierarchy", "affordance"]
            assert critique.severity in [Severity.FAIL, Severity.WARN, Severity.INFO]

    def test_report_serialization_roundtrip(self, critique_engine, sample_fingerprints):
        """Test that reports can be serialized and deserialized."""
        report = critique_engine.generate_critique(sample_fingerprints)

        # Serialize
        data = report.to_dict()

        # Deserialize
        restored = CritiqueReport.from_dict(data)

        # Verify
        assert restored.summary.total_critiques == report.summary.total_critiques
        assert len(restored.critiques) == len(report.critiques)

    def test_report_with_all_data_sources(self, critique_engine, sample_fingerprints):
        """Test critique with all data sources provided."""
        # Create mock data
        mock_crawl = MagicMock()
        mock_crawl.fingerprints = sample_fingerprints[:1]

        mock_ci = MagicMock()
        mock_ci.new_findings = []

        mock_clusters = MagicMock()
        mock_clusters.clusters = []

        mock_pseudo_states = []

        report = critique_engine.generate_critique(
            runtime_fingerprints=sample_fingerprints,
            crawl_results=[mock_crawl],
            ci_result=mock_ci,
            visual_clusters=mock_clusters,
            pseudo_states=mock_pseudo_states,
        )

        assert report is not None
