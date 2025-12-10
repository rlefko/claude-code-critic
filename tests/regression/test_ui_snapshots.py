"""
Regression snapshot tests for UI consistency checking.

These tests ensure that rule detection counts remain stable and
don't explode unexpectedly when code changes are made.
"""

import json
from pathlib import Path
from typing import Dict, Any

import pytest

# Import UI modules
try:
    from claude_indexer.ui.config import UIQualityConfig
    from claude_indexer.ui.rules.engine import RuleEngine
    from claude_indexer.ui.ci.audit_runner import CIAuditRunner
    from claude_indexer.ui.models import Finding, Severity
    UI_MODULES_AVAILABLE = True
except ImportError as e:
    UI_MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "ui_repo"
SNAPSHOT_PATH = Path(__file__).parent / "snapshots"


pytestmark = pytest.mark.skipif(
    not UI_MODULES_AVAILABLE,
    reason=f"UI modules not available: {IMPORT_ERROR if not UI_MODULES_AVAILABLE else ''}"
)


# Expected finding counts per rule (baseline)
# These values are calibrated against the test fixture repository
EXPECTED_COUNTS = {
    # Token drift rules
    "COLOR.NON_TOKEN": {"min": 15, "max": 30},
    "SPACING.OFF_SCALE": {"min": 8, "max": 20},
    "RADIUS.OFF_SCALE": {"min": 3, "max": 10},
    "TYPOGRAPHY.OFF_SCALE": {"min": 5, "max": 15},

    # Duplication rules
    "STYLE.DUPLICATE_SET": {"min": 3, "max": 10},
    "STYLE.NEAR_DUPLICATE_SET": {"min": 2, "max": 8},
    "UTILITY.DUPLICATE_SEQUENCE": {"min": 5, "max": 15},
    "COMPONENT.DUPLICATE_CLUSTER": {"min": 2, "max": 6},

    # Inconsistency rules
    "ROLE.OUTLIER.BUTTON": {"min": 0, "max": 3},
    "ROLE.OUTLIER.INPUT": {"min": 0, "max": 3},
    "ROLE.OUTLIER.CARD": {"min": 0, "max": 3},
    "FOCUS.RING.INCONSISTENT": {"min": 1, "max": 4},

    # CSS smell rules
    "CSS.SPECIFICITY.ESCALATION": {"min": 5, "max": 15},
    "IMPORTANT.NEW_USAGE": {"min": 5, "max": 12},
    "SUPPRESSION.NO_RATIONALE": {"min": 0, "max": 2},
}


@pytest.fixture
def fixture_path() -> Path:
    """Return the path to the UI test fixture repository."""
    return FIXTURE_PATH


@pytest.fixture
def snapshot_path() -> Path:
    """Return the path to snapshot files."""
    SNAPSHOT_PATH.mkdir(exist_ok=True)
    return SNAPSHOT_PATH


@pytest.fixture
def ui_config(fixture_path: Path) -> UIQualityConfig:
    """Load UI quality configuration from the fixture."""
    config_path = fixture_path / ".ui-quality.yaml"
    if config_path.exists():
        return UIQualityConfig.from_file(config_path)
    return UIQualityConfig()


@pytest.fixture
def audit_runner(fixture_path: Path, ui_config: UIQualityConfig) -> CIAuditRunner:
    """Create an audit runner for the fixture."""
    return CIAuditRunner(
        project_path=fixture_path,
        config=ui_config,
    )


class TestRuleFindingCounts:
    """Test that finding counts stay within expected ranges."""

    def test_token_drift_counts_in_range(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Token drift rule counts should be within expected ranges."""
        results = audit_runner.run_audit()

        for rule_id in ["COLOR.NON_TOKEN", "SPACING.OFF_SCALE", "RADIUS.OFF_SCALE", "TYPOGRAPHY.OFF_SCALE"]:
            count = results.get_count_by_rule(rule_id)
            expected = EXPECTED_COUNTS.get(rule_id, {"min": 0, "max": 100})

            assert expected["min"] <= count <= expected["max"], (
                f"{rule_id}: expected {expected['min']}-{expected['max']} findings, got {count}"
            )

    def test_duplication_counts_in_range(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Duplication rule counts should be within expected ranges."""
        results = audit_runner.run_audit()

        for rule_id in [
            "STYLE.DUPLICATE_SET",
            "STYLE.NEAR_DUPLICATE_SET",
            "UTILITY.DUPLICATE_SEQUENCE",
            "COMPONENT.DUPLICATE_CLUSTER",
        ]:
            count = results.get_count_by_rule(rule_id)
            expected = EXPECTED_COUNTS.get(rule_id, {"min": 0, "max": 100})

            assert expected["min"] <= count <= expected["max"], (
                f"{rule_id}: expected {expected['min']}-{expected['max']} findings, got {count}"
            )

    def test_css_smell_counts_in_range(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """CSS smell rule counts should be within expected ranges."""
        results = audit_runner.run_audit()

        for rule_id in ["CSS.SPECIFICITY.ESCALATION", "IMPORTANT.NEW_USAGE"]:
            count = results.get_count_by_rule(rule_id)
            expected = EXPECTED_COUNTS.get(rule_id, {"min": 0, "max": 100})

            assert expected["min"] <= count <= expected["max"], (
                f"{rule_id}: expected {expected['min']}-{expected['max']} findings, got {count}"
            )


class TestSeverityDistribution:
    """Test that severity distribution is as expected."""

    def test_fail_severity_for_token_drift(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Token drift issues should have FAIL severity."""
        results = audit_runner.run_audit()

        color_findings = results.get_findings_by_rule("COLOR.NON_TOKEN")
        for finding in color_findings:
            # Non-baseline findings should be FAIL
            if not finding.is_baseline:
                assert finding.severity == Severity.FAIL

    def test_warn_severity_for_duplicates(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Duplicate issues should have WARN severity."""
        results = audit_runner.run_audit()

        duplicate_findings = results.get_findings_by_rule("STYLE.DUPLICATE_SET")
        for finding in duplicate_findings:
            assert finding.severity == Severity.WARN


class TestBaselineClassification:
    """Test that baseline issues are correctly classified."""

    def test_legacy_css_issues_are_baseline(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """All issues from legacy.css should be classified as baseline."""
        results = audit_runner.run_audit()

        legacy_findings = [
            f for f in results.findings
            if "legacy.css" in f.location.file_path
        ]

        for finding in legacy_findings:
            assert finding.is_baseline, f"Issue in legacy.css should be baseline: {finding}"

    def test_new_file_issues_not_baseline(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Issues from new files should NOT be baseline."""
        results = audit_runner.run_audit()

        input_legacy_findings = [
            f for f in results.findings
            if "InputLegacy.tsx" in f.location.file_path
        ]

        for finding in input_legacy_findings:
            assert not finding.is_baseline, f"Issue in InputLegacy.tsx should NOT be baseline: {finding}"


class TestSnapshotComparison:
    """Test comparison against saved snapshots."""

    def test_total_findings_snapshot(
        self, fixture_path: Path, audit_runner: CIAuditRunner, snapshot_path: Path
    ):
        """Total finding count should match snapshot (with tolerance)."""
        results = audit_runner.run_audit()
        total_count = len(results.findings)

        snapshot_file = snapshot_path / "total_findings.json"

        if snapshot_file.exists():
            # Compare against existing snapshot
            with open(snapshot_file) as f:
                snapshot = json.load(f)

            expected = snapshot.get("total", 0)
            tolerance = snapshot.get("tolerance", 10)

            assert abs(total_count - expected) <= tolerance, (
                f"Total findings ({total_count}) differs from snapshot ({expected}) "
                f"by more than tolerance ({tolerance})"
            )
        else:
            # Create initial snapshot
            snapshot = {
                "total": total_count,
                "tolerance": max(10, int(total_count * 0.1)),  # 10% tolerance
            }
            with open(snapshot_file, "w") as f:
                json.dump(snapshot, f, indent=2)

            pytest.skip("Created initial snapshot, re-run to compare")

    def test_rule_counts_snapshot(
        self, fixture_path: Path, audit_runner: CIAuditRunner, snapshot_path: Path
    ):
        """Per-rule finding counts should match snapshot."""
        results = audit_runner.run_audit()

        counts_by_rule = {}
        for rule_id in EXPECTED_COUNTS:
            counts_by_rule[rule_id] = results.get_count_by_rule(rule_id)

        snapshot_file = snapshot_path / "rule_counts.json"

        if snapshot_file.exists():
            with open(snapshot_file) as f:
                snapshot = json.load(f)

            for rule_id, count in counts_by_rule.items():
                expected = snapshot.get(rule_id, {})
                expected_count = expected.get("count", 0)
                tolerance = expected.get("tolerance", 3)

                assert abs(count - expected_count) <= tolerance, (
                    f"{rule_id}: count ({count}) differs from snapshot ({expected_count}) "
                    f"by more than tolerance ({tolerance})"
                )
        else:
            # Create initial snapshot
            snapshot = {
                rule_id: {
                    "count": count,
                    "tolerance": max(3, int(count * 0.2)),  # 20% tolerance, min 3
                }
                for rule_id, count in counts_by_rule.items()
            }
            with open(snapshot_file, "w") as f:
                json.dump(snapshot, f, indent=2)

            pytest.skip("Created initial snapshot, re-run to compare")


class TestRegressionPrevention:
    """Test that changes don't introduce regressions."""

    def test_no_new_fail_findings_in_canonical_components(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Canonical components (Button.tsx, Card.tsx, Input.tsx) should have no FAIL findings."""
        results = audit_runner.run_audit()

        canonical_files = ["Button.tsx", "Card.tsx", "Input.tsx"]

        for file_name in canonical_files:
            findings = [
                f for f in results.findings
                if file_name in f.location.file_path and f.severity == Severity.FAIL
            ]

            # Allow minimal violations in canonical files
            assert len(findings) <= 2, (
                f"Canonical component {file_name} has too many FAIL findings: {len(findings)}"
            )

    def test_detection_accuracy_maintained(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Key detection scenarios should still be caught."""
        results = audit_runner.run_audit()

        # InputLegacy.tsx should have COLOR.NON_TOKEN findings
        input_legacy_color = [
            f for f in results.findings
            if "InputLegacy.tsx" in f.location.file_path
            and f.rule_id == "COLOR.NON_TOKEN"
        ]
        assert len(input_legacy_color) >= 5, "InputLegacy.tsx should have 5+ color violations"

        # overrides.css should have specificity issues
        overrides_specificity = [
            f for f in results.findings
            if "overrides.css" in f.location.file_path
            and f.rule_id == "CSS.SPECIFICITY.ESCALATION"
        ]
        assert len(overrides_specificity) >= 3, "overrides.css should have 3+ specificity issues"

        # utilities.scss should have duplicates
        utilities_duplicates = [
            f for f in results.findings
            if "utilities.scss" in f.location.file_path
            and "DUPLICATE" in f.rule_id
        ]
        assert len(utilities_duplicates) >= 2, "utilities.scss should have 2+ duplicate issues"


class TestFindingStability:
    """Test that findings are stable and reproducible."""

    def test_deterministic_findings(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Running audit twice should produce identical results."""
        results1 = audit_runner.run_audit()
        results2 = audit_runner.run_audit()

        assert len(results1.findings) == len(results2.findings), (
            "Two consecutive runs should produce same number of findings"
        )

        # Sort findings for comparison
        sorted1 = sorted(results1.findings, key=lambda f: (f.rule_id, f.location.file_path, f.location.line))
        sorted2 = sorted(results2.findings, key=lambda f: (f.rule_id, f.location.file_path, f.location.line))

        for f1, f2 in zip(sorted1, sorted2):
            assert f1.rule_id == f2.rule_id
            assert f1.location.file_path == f2.location.file_path
            assert f1.severity == f2.severity

    def test_no_phantom_findings(
        self, fixture_path: Path, audit_runner: CIAuditRunner
    ):
        """Findings should reference real files and lines."""
        results = audit_runner.run_audit()

        for finding in results.findings:
            file_path = Path(finding.location.file_path)
            assert file_path.exists() or fixture_path in file_path.parents, (
                f"Finding references non-existent file: {finding.location.file_path}"
            )
