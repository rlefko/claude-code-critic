"""Unit tests for baseline management."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from claude_indexer.ui.ci.baseline import (
    BaselineEntry,
    BaselineManager,
    BaselineReport,
    CleanupItem,
    CleanupMap,
)
from claude_indexer.ui.config import UIQualityConfig
from claude_indexer.ui.models import (
    Evidence,
    EvidenceType,
    Finding,
    Severity,
    SymbolKind,
    SymbolRef,
)


class TestBaselineEntry:
    """Tests for BaselineEntry dataclass."""

    def test_create_baseline_entry(self):
        """Test basic BaselineEntry creation."""
        entry = BaselineEntry(
            finding_hash="abc123",
            rule_id="COLOR.NON_TOKEN",
            file_path="/src/Button.tsx",
            line_number=42,
            summary="Hardcoded color",
        )

        assert entry.finding_hash == "abc123"
        assert entry.rule_id == "COLOR.NON_TOKEN"
        assert entry.file_path == "/src/Button.tsx"
        assert entry.line_number == 42
        assert entry.suppressed is False

    def test_baseline_entry_with_suppression(self):
        """Test BaselineEntry with suppression."""
        entry = BaselineEntry(
            finding_hash="def456",
            rule_id="SPACING.OFF_SCALE",
            file_path="/src/Card.tsx",
            line_number=10,
            suppressed=True,
            suppression_reason="Legacy code, will fix in Q2",
            suppression_expiry="2024-06-01",
        )

        assert entry.suppressed is True
        assert entry.suppression_reason == "Legacy code, will fix in Q2"
        assert entry.suppression_expiry == "2024-06-01"

    def test_baseline_entry_round_trip(self):
        """Test BaselineEntry serialization round-trip."""
        entry = BaselineEntry(
            finding_hash="hash123",
            rule_id="COLOR.NON_TOKEN",
            file_path="/test.tsx",
            line_number=5,
            summary="Test",
            suppressed=True,
            suppression_reason="reason",
        )

        data = entry.to_dict()
        restored = BaselineEntry.from_dict(data)

        assert restored.finding_hash == "hash123"
        assert restored.suppressed is True
        assert restored.suppression_reason == "reason"


class TestBaselineReport:
    """Tests for BaselineReport dataclass."""

    def test_create_baseline_report(self):
        """Test basic BaselineReport creation."""
        report = BaselineReport()

        assert report.version == "1.0"
        assert report.entries == []
        assert report.total_entries == 0

    def test_baseline_report_with_entries(self):
        """Test BaselineReport with entries."""
        entries = [
            BaselineEntry(
                finding_hash="h1",
                rule_id="COLOR.NON_TOKEN",
                file_path="/a.tsx",
                line_number=1,
            ),
            BaselineEntry(
                finding_hash="h2",
                rule_id="COLOR.NON_TOKEN",
                file_path="/b.tsx",
                line_number=2,
            ),
            BaselineEntry(
                finding_hash="h3",
                rule_id="SPACING.OFF_SCALE",
                file_path="/c.tsx",
                line_number=3,
                suppressed=True,
            ),
        ]
        rule_counts = {"COLOR.NON_TOKEN": 2, "SPACING.OFF_SCALE": 1}

        report = BaselineReport(entries=entries, rule_counts=rule_counts)

        assert report.total_entries == 3
        assert report.suppressed_count == 1

    def test_baseline_report_get_entries_by_rule(self):
        """Test filtering entries by rule."""
        entries = [
            BaselineEntry("h1", "COLOR.NON_TOKEN", "/a.tsx", 1),
            BaselineEntry("h2", "COLOR.NON_TOKEN", "/b.tsx", 2),
            BaselineEntry("h3", "SPACING.OFF_SCALE", "/c.tsx", 3),
        ]
        report = BaselineReport(entries=entries)

        color_entries = report.get_entries_by_rule("COLOR.NON_TOKEN")

        assert len(color_entries) == 2

    def test_baseline_report_get_entry_by_hash(self):
        """Test getting entry by hash."""
        entries = [
            BaselineEntry("hash1", "RULE1", "/a.tsx", 1),
            BaselineEntry("hash2", "RULE2", "/b.tsx", 2),
        ]
        report = BaselineReport(entries=entries)

        entry = report.get_entry_by_hash("hash1")

        assert entry is not None
        assert entry.rule_id == "RULE1"

        # Non-existent hash
        assert report.get_entry_by_hash("nonexistent") is None

    def test_baseline_report_is_in_baseline(self):
        """Test checking if hash is in baseline."""
        entries = [BaselineEntry("hash1", "RULE1", "/a.tsx", 1)]
        report = BaselineReport(entries=entries)

        assert report.is_in_baseline("hash1") is True
        assert report.is_in_baseline("hash2") is False

    def test_baseline_report_round_trip(self):
        """Test BaselineReport serialization round-trip."""
        entries = [
            BaselineEntry("h1", "RULE1", "/a.tsx", 1),
        ]
        report = BaselineReport(
            entries=entries,
            rule_counts={"RULE1": 1},
        )

        data = report.to_dict()
        restored = BaselineReport.from_dict(data)

        assert len(restored.entries) == 1
        assert restored.rule_counts["RULE1"] == 1


class TestCleanupItem:
    """Tests for CleanupItem dataclass."""

    def test_create_cleanup_item(self):
        """Test basic CleanupItem creation."""
        item = CleanupItem(
            rule_id="COLOR.NON_TOKEN",
            count=15,
            estimated_effort="low",
            priority=1,
            sample_locations=["/a.tsx:10", "/b.tsx:20"],
            suggested_approach="Replace with tokens",
            impact_description="15 hardcoded colors",
        )

        assert item.rule_id == "COLOR.NON_TOKEN"
        assert item.count == 15
        assert item.priority == 1
        assert len(item.sample_locations) == 2

    def test_cleanup_item_round_trip(self):
        """Test CleanupItem serialization round-trip."""
        item = CleanupItem(
            rule_id="SPACING.OFF_SCALE",
            count=5,
            estimated_effort="medium",
            priority=2,
        )

        data = item.to_dict()
        restored = CleanupItem.from_dict(data)

        assert restored.rule_id == "SPACING.OFF_SCALE"
        assert restored.count == 5
        assert restored.priority == 2


class TestCleanupMap:
    """Tests for CleanupMap dataclass."""

    def test_create_cleanup_map(self):
        """Test basic CleanupMap creation."""
        items = [
            CleanupItem("RULE1", 10, "low", 1),
            CleanupItem("RULE2", 5, "high", 3),
        ]

        cleanup_map = CleanupMap(
            items=items,
            total_baseline_issues=15,
            estimated_total_effort="medium (a few days)",
        )

        assert len(cleanup_map.items) == 2
        assert cleanup_map.total_baseline_issues == 15

    def test_cleanup_map_get_by_priority(self):
        """Test filtering by priority."""
        items = [
            CleanupItem("RULE1", 10, "low", 1),
            CleanupItem("RULE2", 8, "medium", 2),
            CleanupItem("RULE3", 5, "high", 4),
        ]
        cleanup_map = CleanupMap(items=items)

        high_priority = cleanup_map.get_by_priority(2)

        assert len(high_priority) == 2  # Priority 1 and 2

    def test_cleanup_map_round_trip(self):
        """Test CleanupMap serialization round-trip."""
        items = [CleanupItem("RULE1", 5, "low", 2)]
        cleanup_map = CleanupMap(
            items=items,
            total_baseline_issues=5,
        )

        data = cleanup_map.to_dict()
        restored = CleanupMap.from_dict(data)

        assert len(restored.items) == 1
        assert restored.total_baseline_issues == 5


class TestBaselineManager:
    """Tests for BaselineManager class."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def config(self):
        """Create a test UI quality config."""
        return UIQualityConfig()

    @pytest.fixture
    def manager(self, temp_project, config):
        """Create a BaselineManager instance."""
        return BaselineManager(temp_project, config)

    @pytest.fixture
    def sample_finding(self):
        """Create a sample finding for testing."""
        return Finding(
            rule_id="COLOR.NON_TOKEN",
            severity=Severity.FAIL,
            confidence=0.95,
            summary="Hardcoded color #ff6b6b",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.STATIC,
                    description="Found in property",
                )
            ],
            source_ref=SymbolRef(
                file_path="src/Button.tsx",
                start_line=42,
                end_line=42,
                kind=SymbolKind.CSS,
            ),
        )

    def test_load_nonexistent_baseline(self, manager):
        """Test loading when no baseline exists."""
        baseline = manager.load()

        assert baseline is not None
        assert baseline.total_entries == 0

    def test_save_and_load_baseline(self, manager, temp_project):
        """Test saving and loading baseline."""
        # Create and save baseline
        entry = BaselineEntry(
            finding_hash="hash123",
            rule_id="COLOR.NON_TOKEN",
            file_path="/test.tsx",
            line_number=10,
        )
        baseline = BaselineReport(entries=[entry])
        manager.save(baseline)

        # Verify file exists
        baseline_path = temp_project / ".ui-quality/baseline.json"
        assert baseline_path.exists()

        # Load in new manager
        manager2 = BaselineManager(temp_project, manager.config)
        loaded = manager2.load()

        assert loaded.total_entries == 1
        assert loaded.entries[0].finding_hash == "hash123"

    def test_separate_findings_all_new(self, manager, sample_finding):
        """Test separating findings when all are new."""
        findings = [sample_finding]

        new, baseline = manager.separate_findings(findings)

        assert len(new) == 1
        assert len(baseline) == 0
        assert new[0].is_new is True

    def test_separate_findings_with_baseline(self, manager, sample_finding):
        """Test separating findings with existing baseline."""
        # Add finding to baseline
        manager.update_from_findings([sample_finding])

        # Create new findings
        new_finding = Finding(
            rule_id="SPACING.OFF_SCALE",
            severity=Severity.WARN,
            confidence=0.8,
            summary="Off-scale spacing",
            evidence=[
                Evidence(
                    evidence_type=EvidenceType.STATIC,
                    description="Found in property",
                )
            ],
            source_ref=SymbolRef(
                file_path="src/Card.tsx",
                start_line=20,
                end_line=20,
                kind=SymbolKind.CSS,
            ),
        )

        # Separate findings
        new, baseline = manager.separate_findings([sample_finding, new_finding])

        assert len(new) == 1
        assert len(baseline) == 1
        assert new[0].rule_id == "SPACING.OFF_SCALE"
        assert baseline[0].rule_id == "COLOR.NON_TOKEN"
        assert baseline[0].is_new is False

    def test_update_from_findings(self, manager, sample_finding):
        """Test updating baseline with findings."""
        baseline = manager.update_from_findings([sample_finding])

        assert baseline.total_entries == 1
        assert "COLOR.NON_TOKEN" in baseline.rule_counts
        assert baseline.rule_counts["COLOR.NON_TOKEN"] == 1

    def test_update_from_findings_existing(self, manager, sample_finding):
        """Test updating baseline with existing findings."""
        # First update
        manager.update_from_findings([sample_finding])

        # Second update with same finding
        baseline = manager.update_from_findings([sample_finding])

        # Should still be 1 entry, not 2
        assert baseline.total_entries == 1

    def test_generate_cleanup_map(self, manager):
        """Test generating cleanup map."""
        # Create baseline with various issues
        entries = [
            BaselineEntry("h1", "COLOR.NON_TOKEN", "/a.tsx", 1),
            BaselineEntry("h2", "COLOR.NON_TOKEN", "/b.tsx", 2),
            BaselineEntry("h3", "SPACING.OFF_SCALE", "/c.tsx", 3),
        ]
        baseline = BaselineReport(entries=entries)

        cleanup_map = manager.generate_cleanup_map(baseline)

        assert cleanup_map.total_baseline_issues == 3
        assert len(cleanup_map.items) == 2  # Two rule types

        # Check items have expected fields
        for item in cleanup_map.items:
            assert item.rule_id in ["COLOR.NON_TOKEN", "SPACING.OFF_SCALE"]
            assert item.suggested_approach != ""
            assert item.impact_description != ""

    def test_generate_cleanup_map_with_suppressed(self, manager):
        """Test cleanup map excludes suppressed entries."""
        entries = [
            BaselineEntry("h1", "COLOR.NON_TOKEN", "/a.tsx", 1),
            BaselineEntry(
                "h2", "COLOR.NON_TOKEN", "/b.tsx", 2,
                suppressed=True, suppression_reason="Legacy"
            ),
        ]
        baseline = BaselineReport(entries=entries)

        cleanup_map = manager.generate_cleanup_map(baseline)

        # Only 1 non-suppressed issue
        assert cleanup_map.total_baseline_issues == 1

    def test_cleanup_map_priority_calculation(self, manager):
        """Test cleanup map priority calculation."""
        # Create many entries of one type
        entries = [
            BaselineEntry(f"h{i}", "COLOR.NON_TOKEN", f"/file{i}.tsx", i)
            for i in range(25)  # High count
        ]
        entries.append(BaselineEntry("hx", "COMPONENT.DUPLICATE_CLUSTER", "/comp.tsx", 1))

        baseline = BaselineReport(entries=entries)
        cleanup_map = manager.generate_cleanup_map(baseline)

        # Items should be sorted by priority
        assert len(cleanup_map.items) >= 2
        # COLOR.NON_TOKEN should be high priority (low effort + high count)
        color_item = next(i for i in cleanup_map.items if i.rule_id == "COLOR.NON_TOKEN")
        assert color_item.priority <= 2

    def test_reset_baseline(self, manager, sample_finding, temp_project):
        """Test resetting baseline."""
        # Create baseline
        manager.update_from_findings([sample_finding])
        manager.save(manager.load())

        # Verify file exists
        baseline_path = temp_project / ".ui-quality/baseline.json"
        assert baseline_path.exists()

        # Reset
        manager.reset()

        # File should be gone
        assert not baseline_path.exists()

        # Loading should give empty baseline
        baseline = manager.load()
        assert baseline.total_entries == 0

    def test_compute_finding_hash(self, manager, sample_finding):
        """Test finding hash computation is stable."""
        hash1 = manager._compute_finding_hash(sample_finding)
        hash2 = manager._compute_finding_hash(sample_finding)

        assert hash1 == hash2
        assert len(hash1) == 16

    def test_compute_finding_hash_different_findings(self, manager):
        """Test different findings get different hashes."""
        finding1 = Finding(
            rule_id="RULE1",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=SymbolRef("file.tsx", 10, 10, SymbolKind.CSS),
        )
        finding2 = Finding(
            rule_id="RULE1",
            severity=Severity.FAIL,
            confidence=0.9,
            summary="test",
            evidence=[Evidence(EvidenceType.STATIC, "test")],
            source_ref=SymbolRef("file.tsx", 20, 20, SymbolKind.CSS),  # Different line
        )

        hash1 = manager._compute_finding_hash(finding1)
        hash2 = manager._compute_finding_hash(finding2)

        assert hash1 != hash2

    def test_calculate_priority(self, manager):
        """Test priority calculation."""
        # High count + low effort = high priority (low number)
        priority1 = manager._calculate_priority(25, "low", "COLOR.NON_TOKEN")
        # Low count + high effort = low priority (high number)
        priority2 = manager._calculate_priority(2, "high", "OTHER.RULE")

        assert priority1 < priority2

    def test_estimate_total_effort(self, manager):
        """Test total effort estimation."""
        small_items = [CleanupItem("R1", 5, "low", 1)]
        medium_items = [CleanupItem("R1", 30, "medium", 1)]
        large_items = [CleanupItem("R1", 100, "high", 1)]

        assert "hours" in manager._estimate_total_effort(small_items)
        assert "days" in manager._estimate_total_effort(medium_items)
        assert "sprint" in manager._estimate_total_effort(large_items)

    def test_generate_impact_description(self, manager):
        """Test impact description generation."""
        desc1 = manager._generate_impact_description("COLOR.NON_TOKEN", 10)
        desc2 = manager._generate_impact_description("COMPONENT.DUPLICATE_CLUSTER", 5)
        desc3 = manager._generate_impact_description("UNKNOWN.RULE", 3)

        assert "hardcoded colors" in desc1
        assert "duplicate" in desc2 or "consolidate" in desc2
        assert "UNKNOWN.RULE" in desc3
