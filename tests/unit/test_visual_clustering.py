"""Unit tests for screenshot capture and visual clustering."""

import tempfile
from pathlib import Path

import pytest


class TestElementScreenshot:
    """Tests for ElementScreenshot dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.screenshots import ElementScreenshot

        screenshot = ElementScreenshot(
            element_id="page1_button",
            screenshot_path=Path("/tmp/screenshots/button.png"),
            phash="abc123def456",
            width=100,
            height=40,
            role="button",
            selector='[data-testid="submit"]',
        )

        data = screenshot.to_dict()

        assert data["element_id"] == "page1_button"
        assert data["screenshot_path"] == "/tmp/screenshots/button.png"
        assert data["phash"] == "abc123def456"
        assert data["width"] == 100
        assert data["height"] == 40
        assert data["role"] == "button"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.screenshots import ElementScreenshot

        data = {
            "element_id": "card_1",
            "screenshot_path": "/tmp/card.png",
            "phash": "fedcba987654",
            "width": 300,
            "height": 200,
            "role": "card",
            "selector": ".card:first-child",
        }

        screenshot = ElementScreenshot.from_dict(data)

        assert screenshot.element_id == "card_1"
        assert screenshot.screenshot_path == Path("/tmp/card.png")
        assert screenshot.phash == "fedcba987654"
        assert screenshot.role == "card"

    def test_round_trip(self):
        """Test serialization round-trip."""
        from claude_indexer.ui.collectors.screenshots import ElementScreenshot

        original = ElementScreenshot(
            element_id="input_email",
            screenshot_path=Path("/screenshots/input.png"),
            phash="1234567890abcdef",
            width=200,
            height=32,
            role="input",
            selector='input[type="email"]',
        )

        data = original.to_dict()
        restored = ElementScreenshot.from_dict(data)

        assert restored.element_id == original.element_id
        assert restored.screenshot_path == original.screenshot_path
        assert restored.phash == original.phash


class TestVisualCluster:
    """Tests for VisualCluster dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.screenshots import (
            ElementScreenshot,
            VisualCluster,
        )

        elements = [
            ElementScreenshot(
                element_id=f"btn_{i}",
                screenshot_path=Path(f"/tmp/btn_{i}.png"),
                phash=f"hash{i}",
                width=80,
                height=32,
                role="button",
                selector=f"button:nth-child({i})",
            )
            for i in range(3)
        ]

        cluster = VisualCluster(
            cluster_id=0,
            elements=elements,
            representative=elements[0],
            avg_hamming_distance=0.05,
            is_consistent=True,
            variant_count=3,
        )

        data = cluster.to_dict()

        assert data["cluster_id"] == 0
        assert len(data["elements"]) == 3
        assert data["representative"]["element_id"] == "btn_0"
        assert data["is_consistent"] is True

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.screenshots import VisualCluster

        data = {
            "cluster_id": 1,
            "elements": [
                {
                    "element_id": "input_1",
                    "screenshot_path": "/tmp/input.png",
                    "phash": "abc",
                    "width": 100,
                    "height": 30,
                    "role": "input",
                    "selector": "input",
                }
            ],
            "representative": None,
            "avg_hamming_distance": 0.1,
            "is_consistent": False,
            "variant_count": 2,
        }

        cluster = VisualCluster.from_dict(data)

        assert cluster.cluster_id == 1
        assert len(cluster.elements) == 1
        assert cluster.is_consistent is False


class TestVisualClusteringResult:
    """Tests for VisualClusteringResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.screenshots import (
            VisualCluster,
            VisualClusteringResult,
        )

        result = VisualClusteringResult(
            clusters=[VisualCluster(cluster_id=0)],
            identical_different_code=[VisualCluster(cluster_id=1)],
            inconsistent_variants=[],
        )

        data = result.to_dict()

        assert len(data["clusters"]) == 1
        assert len(data["identical_different_code"]) == 1
        assert len(data["inconsistent_variants"]) == 0

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.screenshots import VisualClusteringResult

        data = {
            "clusters": [{"cluster_id": 0, "elements": [], "representative": None}],
            "identical_different_code": [],
            "inconsistent_variants": [],
        }

        result = VisualClusteringResult.from_dict(data)

        assert len(result.clusters) == 1
        assert result.clusters[0].cluster_id == 0


class TestScreenshotCapture:
    """Tests for ScreenshotCapture class."""

    def test_init(self):
        """Test initialization creates output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "screenshots"

            # Skip test if imagehash not available
            try:
                from claude_indexer.ui.collectors.screenshots import ScreenshotCapture

                capture = ScreenshotCapture(output_dir=output_dir, hash_size=8)

                assert capture.output_dir == output_dir
                assert capture.hash_size == 8
                assert output_dir.exists()
            except ImportError:
                pytest.skip("imagehash not installed")

    def test_sanitize_filename(self):
        """Test filename sanitization."""
        try:
            from claude_indexer.ui.collectors.screenshots import ScreenshotCapture

            with tempfile.TemporaryDirectory() as tmpdir:
                capture = ScreenshotCapture(output_dir=tmpdir)

                # Test various problematic characters
                assert "/" not in capture._sanitize_filename("path/to/element")
                assert "\\" not in capture._sanitize_filename("path\\to\\element")
                assert ":" not in capture._sanitize_filename("time:12:30")
                assert " " not in capture._sanitize_filename("element with spaces")

                # Test truncation
                long_name = "x" * 300
                sanitized = capture._sanitize_filename(long_name)
                assert len(sanitized) <= 200
        except ImportError:
            pytest.skip("imagehash not installed")

    @pytest.mark.skipif(
        not pytest.importorskip("imagehash", reason="imagehash not installed"),
        reason="imagehash not installed",
    )
    def test_compare_hashes_identical(self):
        """Test hash comparison for identical hashes."""
        from claude_indexer.ui.collectors.screenshots import ScreenshotCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = ScreenshotCapture(output_dir=tmpdir, hash_size=8)

            hash1 = "0000000000000000"
            hash2 = "0000000000000000"

            similarity = capture.compare_hashes(hash1, hash2)
            assert similarity == 1.0

    @pytest.mark.skipif(
        not pytest.importorskip("imagehash", reason="imagehash not installed"),
        reason="imagehash not installed",
    )
    def test_compare_hashes_different(self):
        """Test hash comparison for different hashes."""
        from claude_indexer.ui.collectors.screenshots import ScreenshotCapture

        with tempfile.TemporaryDirectory() as tmpdir:
            capture = ScreenshotCapture(output_dir=tmpdir, hash_size=8)

            hash1 = "0000000000000000"
            hash2 = "ffffffffffffffff"

            similarity = capture.compare_hashes(hash1, hash2)
            assert similarity < 1.0


class TestVisualClusteringEngine:
    """Tests for VisualClusteringEngine class."""

    def test_init(self):
        """Test initialization with thresholds."""
        try:
            from claude_indexer.ui.collectors.screenshots import VisualClusteringEngine

            engine = VisualClusteringEngine(
                identical_threshold=0.98,
                similar_threshold=0.85,
            )

            assert engine.identical_threshold == 0.98
            assert engine.similar_threshold == 0.85
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_cluster_empty(self):
        """Test clustering empty list."""
        try:
            from claude_indexer.ui.collectors.screenshots import VisualClusteringEngine

            engine = VisualClusteringEngine()
            result = engine.cluster_screenshots([])

            assert len(result.clusters) == 0
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_cluster_single_element(self):
        """Test clustering single element (no clusters possible)."""
        try:
            from claude_indexer.ui.collectors.screenshots import (
                ElementScreenshot,
                VisualClusteringEngine,
            )

            engine = VisualClusteringEngine()

            screenshots = [
                ElementScreenshot(
                    element_id="btn_1",
                    screenshot_path=Path("/tmp/btn.png"),
                    phash="0000000000000000",
                    width=100,
                    height=40,
                    role="button",
                    selector="button",
                )
            ]

            result = engine.cluster_screenshots(screenshots)

            # Single element can't form a cluster
            assert len(result.clusters) == 0
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_group_by_role(self):
        """Test grouping screenshots by role."""
        try:
            from claude_indexer.ui.collectors.screenshots import (
                ElementScreenshot,
                VisualClusteringEngine,
            )

            engine = VisualClusteringEngine()

            screenshots = [
                ElementScreenshot(
                    element_id="btn_1",
                    screenshot_path=Path("/tmp/btn1.png"),
                    phash="abc",
                    width=100,
                    height=40,
                    role="button",
                    selector="button:first",
                ),
                ElementScreenshot(
                    element_id="btn_2",
                    screenshot_path=Path("/tmp/btn2.png"),
                    phash="def",
                    width=100,
                    height=40,
                    role="button",
                    selector="button:last",
                ),
                ElementScreenshot(
                    element_id="input_1",
                    screenshot_path=Path("/tmp/input.png"),
                    phash="ghi",
                    width=200,
                    height=32,
                    role="input",
                    selector="input",
                ),
            ]

            groups = engine._group_by_role(screenshots)

            assert "button" in groups
            assert "input" in groups
            assert len(groups["button"]) == 2
            assert len(groups["input"]) == 1
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_compute_avg_similarity(self):
        """Test average similarity computation."""
        try:
            from claude_indexer.ui.collectors.screenshots import VisualClusteringEngine

            engine = VisualClusteringEngine()

            # Perfect similarity matrix
            distance_matrix = [
                [1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0],
                [1.0, 1.0, 1.0],
            ]

            avg = engine._compute_avg_similarity([0, 1, 2], distance_matrix)
            assert avg == 1.0

            # Mixed similarity
            distance_matrix = [
                [1.0, 0.5, 0.5],
                [0.5, 1.0, 0.5],
                [0.5, 0.5, 1.0],
            ]

            avg = engine._compute_avg_similarity([0, 1, 2], distance_matrix)
            assert avg == 0.5
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_find_representative(self):
        """Test finding cluster representative."""
        try:
            from claude_indexer.ui.collectors.screenshots import VisualClusteringEngine

            engine = VisualClusteringEngine()

            # Element 1 has highest average similarity
            distance_matrix = [
                [1.0, 0.3, 0.3],
                [0.3, 1.0, 0.9],
                [0.3, 0.9, 1.0],
            ]

            rep = engine._find_representative([0, 1, 2], distance_matrix)
            # Element 1 or 2 should be representative (highest avg with others)
            assert rep in [1, 2]
        except ImportError:
            pytest.skip("imagehash not installed")


class TestVisualClusteringIntegration:
    """Integration tests for visual clustering."""

    def test_cluster_identical_elements(self):
        """Test clustering visually identical elements."""
        try:
            from claude_indexer.ui.collectors.screenshots import (
                ElementScreenshot,
                VisualClusteringEngine,
            )

            engine = VisualClusteringEngine(
                identical_threshold=0.95,
                similar_threshold=0.80,
            )

            # Create screenshots with identical hashes
            screenshots = [
                ElementScreenshot(
                    element_id=f"btn_{i}",
                    screenshot_path=Path(f"/tmp/btn_{i}.png"),
                    phash="0000000000000000",  # Same hash
                    width=100,
                    height=40,
                    role="button",
                    selector=f"button:nth-child({i})",
                )
                for i in range(4)
            ]

            result = engine.cluster_screenshots(screenshots)

            # Should form one cluster
            assert len(result.clusters) >= 1
            # All should be in same cluster
            if result.clusters:
                assert len(result.clusters[0].elements) == 4
        except ImportError:
            pytest.skip("imagehash not installed")

    def test_find_identical_different_code(self):
        """Test finding visually identical but code-different components."""
        try:
            from claude_indexer.ui.collectors.screenshots import (
                ElementScreenshot,
                VisualClusteringEngine,
            )

            engine = VisualClusteringEngine(identical_threshold=0.95)

            # Same visual appearance (hash), different selectors
            screenshots = [
                ElementScreenshot(
                    element_id="btn_primary",
                    screenshot_path=Path("/tmp/btn1.png"),
                    phash="0000000000000000",
                    width=100,
                    height=40,
                    role="button",
                    selector=".btn-primary",
                ),
                ElementScreenshot(
                    element_id="btn_submit",
                    screenshot_path=Path("/tmp/btn2.png"),
                    phash="0000000000000000",  # Same hash
                    width=100,
                    height=40,
                    role="button",
                    selector=".btn-submit",  # Different selector
                ),
            ]

            result = engine.cluster_screenshots(screenshots)

            # Should identify these as identical but different code
            assert len(result.identical_different_code) >= 1
        except ImportError:
            pytest.skip("imagehash not installed")
