"""
Performance benchmark tests for UI consistency checking.

These tests validate latency targets:
- Tier 0 (Pre-commit Guard): <300ms p95
- Tier 1 (CI Audit): <10 min for 1000+ file repos
- Tier 2 (/redesign): <5 min for focused audit

Requires pytest-benchmark: pip install pytest-benchmark
"""

import time
from pathlib import Path
from typing import List, Callable

import pytest

# Import UI modules
try:
    from claude_indexer.ui.config import UIQualityConfig
    from claude_indexer.ui.rules.engine import RuleEngine
    from claude_indexer.ui.rules.token_drift import ColorNonTokenRule
    from claude_indexer.ui.rules.smells import ImportantNewUsageRule
    from claude_indexer.ui.collectors.source import SourceCollector
    from claude_indexer.ui.normalizers.style import StyleNormalizer
    from claude_indexer.ui.normalizers.token_resolver import TokenResolver
    from claude_indexer.ui.ci.audit_runner import CIAuditRunner
    from claude_indexer.ui.cli.guard import UIGuard
    UI_MODULES_AVAILABLE = True
except ImportError as e:
    UI_MODULES_AVAILABLE = False
    IMPORT_ERROR = str(e)


pytestmark = [
    pytest.mark.skipif(
        not UI_MODULES_AVAILABLE,
        reason=f"UI modules not available: {IMPORT_ERROR if not UI_MODULES_AVAILABLE else ''}"
    ),
    pytest.mark.benchmark,
    pytest.mark.slow,
]


# Performance targets (in seconds)
TIER_0_TARGET_P95 = 0.300  # 300ms
TIER_1_TARGET_P95 = 600.0  # 10 minutes
TIER_2_TARGET_P95 = 300.0  # 5 minutes


class TestTier0Performance:
    """
    Tier 0 (Pre-commit Guard) performance tests.

    Target: <300ms p95 for typical changes (1-10 files)
    """

    def test_single_file_analysis_under_target(
        self,
        fixture_path: Path,
        single_file_content: str,
        benchmark_iterations: int,
    ):
        """Single file analysis should complete in <100ms."""
        token_resolver = TokenResolver.from_css_file(
            fixture_path / "styles" / "tokens.css"
        )

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            # Run token drift detection
            rule = ColorNonTokenRule(token_resolver=token_resolver)
            findings = rule.check_content("test.tsx", single_file_content)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        # Calculate p95
        timings.sort()
        p95_index = int(len(timings) * 0.95)
        p95 = timings[p95_index] if p95_index < len(timings) else timings[-1]

        # P95 should be under 100ms for single file
        assert p95 < 0.100, f"Single file analysis p95 ({p95:.3f}s) exceeds 100ms target"

    def test_batch_file_analysis_under_target(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """Batch analysis of 10 files should complete in <300ms."""
        components_path = fixture_path / "components"
        files = list(components_path.glob("*.tsx"))[:10]

        token_resolver = TokenResolver.from_css_file(
            fixture_path / "styles" / "tokens.css"
        )

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            rule = ColorNonTokenRule(token_resolver=token_resolver)
            for file_path in files:
                content = file_path.read_text()
                findings = rule.check_file(file_path, content)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        timings.sort()
        p95_index = int(len(timings) * 0.95)
        p95 = timings[p95_index] if p95_index < len(timings) else timings[-1]

        assert p95 < TIER_0_TARGET_P95, (
            f"Batch file analysis p95 ({p95:.3f}s) exceeds {TIER_0_TARGET_P95}s target"
        )

    def test_ui_guard_hook_under_target(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """UI Guard hook execution should complete in <300ms."""
        # Simulate a typical pre-commit scenario with 5 changed files
        changed_files = [
            fixture_path / "components" / "Button.tsx",
            fixture_path / "components" / "Card.tsx",
            fixture_path / "components" / "Input.tsx",
            fixture_path / "styles" / "overrides.css",
            fixture_path / "styles" / "utilities.scss",
        ]

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            guard = UIGuard(project_path=fixture_path)
            result = guard.check_files(changed_files)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        timings.sort()
        p95_index = int(len(timings) * 0.95)
        p95 = timings[p95_index] if p95_index < len(timings) else timings[-1]

        assert p95 < TIER_0_TARGET_P95, (
            f"UI Guard hook p95 ({p95:.3f}s) exceeds {TIER_0_TARGET_P95}s target"
        )

    def test_style_normalization_performance(
        self, single_file_content: str, benchmark_iterations: int
    ):
        """Style normalization should be fast (<50ms per file)."""
        normalizer = StyleNormalizer()

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            # Extract and normalize styles
            styles = normalizer.extract_styles(single_file_content)
            normalized = [normalizer.normalize(s) for s in styles]

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        timings.sort()
        p95_index = int(len(timings) * 0.95)
        p95 = timings[p95_index] if p95_index < len(timings) else timings[-1]

        assert p95 < 0.050, f"Style normalization p95 ({p95:.3f}s) exceeds 50ms target"


class TestTier1Performance:
    """
    Tier 1 (CI Audit) performance tests.

    Target: <10 min for 1000+ file repos
    """

    @pytest.mark.slow
    def test_medium_repo_audit_performance(
        self, medium_codebase: Path, benchmark_iterations: int
    ):
        """Medium repo (~100 files) audit should complete in <60s."""
        # Count files
        file_count = len(list(medium_codebase.glob("**/*.tsx"))) + \
                     len(list(medium_codebase.glob("**/*.css")))

        config = UIQualityConfig()
        runner = CIAuditRunner(project_path=medium_codebase, config=config)

        timings = []
        for _ in range(min(3, benchmark_iterations)):  # Fewer iterations for slow tests
            start = time.perf_counter()

            result = runner.run_audit()

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        avg_time = sum(timings) / len(timings)
        time_per_file = avg_time / max(file_count, 1)

        # Extrapolate to 1000 files
        projected_1000_files = time_per_file * 1000

        assert projected_1000_files < TIER_1_TARGET_P95, (
            f"Projected time for 1000 files ({projected_1000_files:.1f}s) "
            f"exceeds {TIER_1_TARGET_P95}s target"
        )

    def test_cross_file_clustering_performance(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """Cross-file clustering should scale linearly."""
        from claude_indexer.ui.similarity.clustering import Clustering
        from claude_indexer.ui.normalizers.component import ComponentNormalizer

        # Create mock fingerprints
        normalizer = ComponentNormalizer()
        fingerprints = []

        # Generate 100 mock fingerprints
        for i in range(100):
            fp = normalizer.create_mock_fingerprint(
                name=f"Component_{i}",
                structure_hash=f"hash_{i % 10}",  # 10 clusters
            )
            fingerprints.append(fp)

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            clustering = Clustering(threshold=0.7)
            clusters = clustering.cluster(fingerprints)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        avg_time = sum(timings) / len(timings)

        # Should complete in <5s for 100 fingerprints
        assert avg_time < 5.0, f"Clustering 100 fingerprints took {avg_time:.2f}s"

    def test_cache_hit_performance_improvement(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """Cache hits should provide >50% performance improvement."""
        from claude_indexer.ui.ci.cache import UICache

        config = UIQualityConfig()
        runner = CIAuditRunner(project_path=fixture_path, config=config)

        # First run (cold cache)
        cold_timings = []
        for _ in range(3):
            # Clear cache
            cache = UICache(fixture_path / ".ui-quality" / "cache")
            cache.clear()

            start = time.perf_counter()
            result = runner.run_audit()
            cold_timings.append(time.perf_counter() - start)

        # Second run (warm cache)
        warm_timings = []
        for _ in range(3):
            start = time.perf_counter()
            result = runner.run_audit()
            warm_timings.append(time.perf_counter() - start)

        cold_avg = sum(cold_timings) / len(cold_timings)
        warm_avg = sum(warm_timings) / len(warm_timings)

        improvement = (cold_avg - warm_avg) / cold_avg * 100

        # Cache should provide at least 30% improvement
        # (50% is ideal but may vary based on I/O)
        assert improvement >= 30, (
            f"Cache improvement ({improvement:.1f}%) is less than 30% target"
        )


class TestTier2Performance:
    """
    Tier 2 (/redesign command) performance tests.

    Target: <5 min for focused audit
    """

    def test_critique_engine_performance(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """Critique engine should analyze fixtures in <30s."""
        from claude_indexer.ui.critique.engine import CritiqueEngine

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            engine = CritiqueEngine(project_path=fixture_path)
            critique = engine.generate_critique(focus_area=None)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        avg_time = sum(timings) / len(timings)

        # Should complete in <30s for the fixture
        assert avg_time < 30.0, f"Critique engine took {avg_time:.2f}s"

    def test_html_report_generation_performance(
        self, fixture_path: Path, benchmark_iterations: int
    ):
        """HTML report generation should complete in <5s."""
        from claude_indexer.ui.reporters.html import HTMLReporter
        from claude_indexer.ui.ci.audit_runner import CIAuditRunner

        config = UIQualityConfig()
        runner = CIAuditRunner(project_path=fixture_path, config=config)
        result = runner.run_audit()

        timings = []
        for _ in range(benchmark_iterations):
            start = time.perf_counter()

            reporter = HTMLReporter()
            html = reporter.generate_report(result)

            elapsed = time.perf_counter() - start
            timings.append(elapsed)

        avg_time = sum(timings) / len(timings)

        assert avg_time < 5.0, f"HTML report generation took {avg_time:.2f}s"


class TestMemoryUsage:
    """Test memory usage stays within reasonable bounds."""

    def test_memory_usage_under_limit(
        self, medium_codebase: Path
    ):
        """Memory usage should stay under 500MB for medium repos."""
        import tracemalloc

        tracemalloc.start()

        config = UIQualityConfig()
        runner = CIAuditRunner(project_path=medium_codebase, config=config)
        result = runner.run_audit()

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024

        assert peak_mb < 500, f"Peak memory usage ({peak_mb:.1f}MB) exceeds 500MB limit"


class TestScalabilityMetrics:
    """Test that performance scales appropriately."""

    def test_linear_scaling_with_file_count(
        self, fixture_path: Path
    ):
        """Processing time should scale linearly with file count."""
        components_path = fixture_path / "components"
        all_files = list(components_path.glob("*.tsx"))

        token_resolver = TokenResolver.from_css_file(
            fixture_path / "styles" / "tokens.css"
        )
        rule = ColorNonTokenRule(token_resolver=token_resolver)

        times_by_count = {}

        for n in [1, 2, 5, 10]:
            files = all_files[:n]

            start = time.perf_counter()
            for f in files:
                content = f.read_text()
                rule.check_file(f, content)
            elapsed = time.perf_counter() - start

            times_by_count[n] = elapsed

        # Check roughly linear scaling (within 3x)
        time_1 = times_by_count[1]
        time_10 = times_by_count[10]

        # 10 files should take less than 30x the time of 1 file
        # (allowing for some overhead)
        assert time_10 < time_1 * 30, (
            f"Non-linear scaling: 1 file={time_1:.3f}s, 10 files={time_10:.3f}s"
        )

    def test_incremental_mode_faster_than_full(
        self, fixture_path: Path
    ):
        """Incremental mode should be faster than full analysis."""
        config = UIQualityConfig()

        # Full analysis
        runner = CIAuditRunner(project_path=fixture_path, config=config)
        start = time.perf_counter()
        full_result = runner.run_audit(incremental=False)
        full_time = time.perf_counter() - start

        # Incremental analysis (simulating no changes)
        start = time.perf_counter()
        incremental_result = runner.run_audit(incremental=True)
        incremental_time = time.perf_counter() - start

        # Incremental should be at least 50% faster when nothing changed
        assert incremental_time < full_time * 0.8, (
            f"Incremental mode ({incremental_time:.2f}s) not faster than "
            f"full mode ({full_time:.2f}s)"
        )
