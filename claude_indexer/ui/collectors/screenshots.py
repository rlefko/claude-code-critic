"""Screenshot capture and visual clustering.

Captures element screenshots and clusters by perceptual hash.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import ElementHandle

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    ElementHandle = None

try:
    import imagehash
    from PIL import Image

    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    imagehash = None
    Image = None


@dataclass
class ElementScreenshot:
    """Screenshot of a single element."""

    element_id: str
    screenshot_path: Path
    phash: str  # Perceptual hash as hex string
    width: int
    height: int
    role: str
    selector: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "element_id": self.element_id,
            "screenshot_path": str(self.screenshot_path),
            "phash": self.phash,
            "width": self.width,
            "height": self.height,
            "role": self.role,
            "selector": self.selector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ElementScreenshot":
        """Create from dictionary."""
        return cls(
            element_id=data["element_id"],
            screenshot_path=Path(data["screenshot_path"]),
            phash=data["phash"],
            width=data["width"],
            height=data["height"],
            role=data["role"],
            selector=data["selector"],
        )


@dataclass
class VisualCluster:
    """Cluster of visually similar elements."""

    cluster_id: int
    elements: list[ElementScreenshot] = field(default_factory=list)
    representative: ElementScreenshot | None = None
    avg_hamming_distance: float = 0.0

    # Classification
    is_consistent: bool = True  # All variants look similar
    variant_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "cluster_id": self.cluster_id,
            "elements": [e.to_dict() for e in self.elements],
            "representative": self.representative.to_dict() if self.representative else None,
            "avg_hamming_distance": self.avg_hamming_distance,
            "is_consistent": self.is_consistent,
            "variant_count": self.variant_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualCluster":
        """Create from dictionary."""
        return cls(
            cluster_id=data["cluster_id"],
            elements=[ElementScreenshot.from_dict(e) for e in data.get("elements", [])],
            representative=ElementScreenshot.from_dict(data["representative"])
            if data.get("representative")
            else None,
            avg_hamming_distance=data.get("avg_hamming_distance", 0.0),
            is_consistent=data.get("is_consistent", True),
            variant_count=data.get("variant_count", 1),
        )


@dataclass
class VisualClusteringResult:
    """Result of visual clustering analysis."""

    clusters: list[VisualCluster] = field(default_factory=list)

    # Findings
    identical_different_code: list[VisualCluster] = field(default_factory=list)
    inconsistent_variants: list[VisualCluster] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "clusters": [c.to_dict() for c in self.clusters],
            "identical_different_code": [c.to_dict() for c in self.identical_different_code],
            "inconsistent_variants": [c.to_dict() for c in self.inconsistent_variants],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisualClusteringResult":
        """Create from dictionary."""
        return cls(
            clusters=[VisualCluster.from_dict(c) for c in data.get("clusters", [])],
            identical_different_code=[
                VisualCluster.from_dict(c) for c in data.get("identical_different_code", [])
            ],
            inconsistent_variants=[
                VisualCluster.from_dict(c) for c in data.get("inconsistent_variants", [])
            ],
        )


class ScreenshotCapture:
    """Captures element screenshots and computes perceptual hashes.

    Uses pHash (perceptual hash) for visual similarity comparison.
    """

    def __init__(
        self,
        output_dir: Path | str,
        hash_size: int = 16,  # pHash resolution (16x16 = 256 bits)
    ):
        """Initialize screenshot capture.

        Args:
            output_dir: Directory to save screenshots.
            hash_size: Size of perceptual hash (larger = more precision).
        """
        if not IMAGEHASH_AVAILABLE:
            raise ImportError(
                "imagehash and Pillow are required for screenshot capture. "
                "Install with: pip install imagehash Pillow"
            )

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.hash_size = hash_size

    async def capture_element(
        self,
        element: "ElementHandle",
        element_id: str,
        role: str,
        selector: str,
    ) -> ElementScreenshot | None:
        """Capture screenshot of single element.

        Args:
            element: Playwright ElementHandle.
            element_id: Unique identifier for element.
            role: Element role (button, input, etc.).
            selector: CSS selector for element.

        Returns:
            ElementScreenshot or None if capture failed.
        """
        try:
            # Sanitize element_id for filename
            safe_id = self._sanitize_filename(element_id)
            screenshot_path = self.output_dir / f"{safe_id}.png"

            # Capture screenshot
            await element.screenshot(path=str(screenshot_path))

            # Get dimensions
            box = await element.bounding_box()
            width = int(box["width"]) if box else 0
            height = int(box["height"]) if box else 0

            # Compute perceptual hash
            phash = self.compute_phash(screenshot_path)

            return ElementScreenshot(
                element_id=element_id,
                screenshot_path=screenshot_path,
                phash=phash,
                width=width,
                height=height,
                role=role,
                selector=selector,
            )

        except Exception:
            return None

    async def capture_batch(
        self,
        elements: list[tuple["ElementHandle", str, str, str]],
    ) -> list[ElementScreenshot]:
        """Capture screenshots of multiple elements.

        Args:
            elements: List of (ElementHandle, element_id, role, selector) tuples.

        Returns:
            List of ElementScreenshot (excluding failures).
        """
        results = []
        for element, element_id, role, selector in elements:
            screenshot = await self.capture_element(element, element_id, role, selector)
            if screenshot:
                results.append(screenshot)
        return results

    def compute_phash(
        self,
        image_path: Path,
    ) -> str:
        """Compute perceptual hash from image file.

        Args:
            image_path: Path to image file.

        Returns:
            Perceptual hash as hex string.
        """
        image = Image.open(image_path)
        hash_value = imagehash.phash(image, hash_size=self.hash_size)
        return str(hash_value)

    def compare_hashes(
        self,
        hash1: str,
        hash2: str,
    ) -> float:
        """Compare two pHashes, return similarity (0-1).

        Args:
            hash1: First perceptual hash hex string.
            hash2: Second perceptual hash hex string.

        Returns:
            Similarity score from 0.0 (different) to 1.0 (identical).
        """
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)

        # Hamming distance (number of different bits)
        distance = h1 - h2

        # Max possible distance depends on hash size
        max_distance = self.hash_size * self.hash_size

        # Convert to similarity
        similarity = 1.0 - (distance / max_distance)
        return max(0.0, min(1.0, similarity))

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use as filename.

        Args:
            name: Original string.

        Returns:
            Sanitized filename-safe string.
        """
        # Replace problematic characters
        safe = name.replace("/", "_").replace("\\", "_")
        safe = safe.replace(":", "_").replace("*", "_")
        safe = safe.replace("?", "_").replace('"', "_")
        safe = safe.replace("<", "_").replace(">", "_")
        safe = safe.replace("|", "_").replace(" ", "_")

        # Truncate if too long
        if len(safe) > 200:
            safe = safe[:200]

        return safe


class VisualClusteringEngine:
    """Clusters elements by visual similarity using pHash.

    Identifies:
    - Visually identical but code-different components
    - Inconsistent variants (same role, different appearance)
    """

    def __init__(
        self,
        identical_threshold: float = 0.95,  # pHash similarity for "identical"
        similar_threshold: float = 0.80,  # pHash similarity for clustering
    ):
        """Initialize visual clustering.

        Args:
            identical_threshold: Similarity threshold for "identical".
            similar_threshold: Similarity threshold for clustering.
        """
        if not IMAGEHASH_AVAILABLE:
            raise ImportError(
                "imagehash is required for visual clustering. "
                "Install with: pip install imagehash"
            )

        self.identical_threshold = identical_threshold
        self.similar_threshold = similar_threshold

    def cluster_screenshots(
        self,
        screenshots: list[ElementScreenshot],
    ) -> VisualClusteringResult:
        """Cluster screenshots by visual similarity.

        Args:
            screenshots: List of ElementScreenshot to cluster.

        Returns:
            VisualClusteringResult with clusters and findings.
        """
        if len(screenshots) < 2:
            return VisualClusteringResult()

        # Build distance matrix
        distance_matrix = self._build_distance_matrix(screenshots)

        # Run simple clustering (union-find based on threshold)
        clusters = self._cluster_by_similarity(screenshots, distance_matrix)

        # Identify findings
        identical_different_code = self._find_identical_different_code(
            screenshots, distance_matrix
        )
        inconsistent_variants = self._find_inconsistent_variants(screenshots, distance_matrix)

        return VisualClusteringResult(
            clusters=clusters,
            identical_different_code=identical_different_code,
            inconsistent_variants=inconsistent_variants,
        )

    def _build_distance_matrix(
        self,
        screenshots: list[ElementScreenshot],
    ) -> list[list[float]]:
        """Build pairwise distance matrix from pHashes.

        Args:
            screenshots: List of ElementScreenshot.

        Returns:
            2D list of similarity scores (0 to 1).
        """
        n = len(screenshots)
        matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            matrix[i][i] = 1.0  # Self-similarity
            for j in range(i + 1, n):
                similarity = self._compute_similarity(
                    screenshots[i].phash, screenshots[j].phash
                )
                matrix[i][j] = similarity
                matrix[j][i] = similarity

        return matrix

    def _compute_similarity(self, hash1: str, hash2: str) -> float:
        """Compute similarity between two pHashes.

        Args:
            hash1: First perceptual hash.
            hash2: Second perceptual hash.

        Returns:
            Similarity score from 0.0 to 1.0.
        """
        try:
            h1 = imagehash.hex_to_hash(hash1)
            h2 = imagehash.hex_to_hash(hash2)
            distance = h1 - h2
            max_distance = len(h1.hash.flatten())
            return 1.0 - (distance / max_distance)
        except Exception:
            return 0.0

    def _cluster_by_similarity(
        self,
        screenshots: list[ElementScreenshot],
        distance_matrix: list[list[float]],
    ) -> list[VisualCluster]:
        """Cluster screenshots using union-find algorithm.

        Args:
            screenshots: List of ElementScreenshot.
            distance_matrix: Pairwise similarity matrix.

        Returns:
            List of VisualCluster.
        """
        n = len(screenshots)

        # Union-find parent array
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union elements above similarity threshold
        for i in range(n):
            for j in range(i + 1, n):
                if distance_matrix[i][j] >= self.similar_threshold:
                    union(i, j)

        # Group by cluster
        clusters_dict: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in clusters_dict:
                clusters_dict[root] = []
            clusters_dict[root].append(i)

        # Build VisualCluster objects
        clusters = []
        for cluster_id, (_, indices) in enumerate(clusters_dict.items()):
            if len(indices) < 2:
                continue  # Skip singleton clusters

            elements = [screenshots[i] for i in indices]

            # Find representative (most central element)
            representative_idx = self._find_representative(indices, distance_matrix)
            representative = screenshots[representative_idx]

            # Compute average internal similarity
            avg_sim = self._compute_avg_similarity(indices, distance_matrix)

            clusters.append(
                VisualCluster(
                    cluster_id=cluster_id,
                    elements=elements,
                    representative=representative,
                    avg_hamming_distance=1.0 - avg_sim,
                    is_consistent=avg_sim >= self.similar_threshold,
                    variant_count=len(set(e.selector for e in elements)),
                )
            )

        return clusters

    def _find_identical_different_code(
        self,
        screenshots: list[ElementScreenshot],
        distance_matrix: list[list[float]],
    ) -> list[VisualCluster]:
        """Find visually identical elements with different selectors/code.

        Args:
            screenshots: List of ElementScreenshot.
            distance_matrix: Pairwise similarity matrix.

        Returns:
            List of clusters with visually identical but code-different elements.
        """
        findings = []
        n = len(screenshots)
        seen = set()

        for i in range(n):
            if i in seen:
                continue

            identical_indices = [i]
            for j in range(i + 1, n):
                if j in seen:
                    continue

                # Check for high visual similarity but different selectors
                if distance_matrix[i][j] >= self.identical_threshold:
                    if screenshots[i].selector != screenshots[j].selector:
                        identical_indices.append(j)
                        seen.add(j)

            if len(identical_indices) >= 2:
                seen.add(i)
                elements = [screenshots[idx] for idx in identical_indices]
                findings.append(
                    VisualCluster(
                        cluster_id=len(findings),
                        elements=elements,
                        representative=elements[0],
                        avg_hamming_distance=1.0
                        - self._compute_avg_similarity(identical_indices, distance_matrix),
                        is_consistent=True,
                        variant_count=len(set(e.selector for e in elements)),
                    )
                )

        return findings

    def _find_inconsistent_variants(
        self,
        screenshots: list[ElementScreenshot],
        distance_matrix: list[list[float]],
    ) -> list[VisualCluster]:
        """Find same-role elements with inconsistent visual appearance.

        Args:
            screenshots: List of ElementScreenshot.
            distance_matrix: Pairwise similarity matrix.

        Returns:
            List of clusters with inconsistent role variants.
        """
        # Group by role
        by_role = self._group_by_role(screenshots)

        findings = []
        for role, role_screenshots in by_role.items():
            if len(role_screenshots) < 3:
                continue

            # Get indices in original list
            indices = [screenshots.index(s) for s in role_screenshots]

            # Check if there's significant variance within role
            avg_sim = self._compute_avg_similarity(indices, distance_matrix)

            # If similarity is below threshold, this role has inconsistent variants
            if avg_sim < self.similar_threshold:
                findings.append(
                    VisualCluster(
                        cluster_id=len(findings),
                        elements=role_screenshots,
                        representative=role_screenshots[0],
                        avg_hamming_distance=1.0 - avg_sim,
                        is_consistent=False,
                        variant_count=len(set(s.selector for s in role_screenshots)),
                    )
                )

        return findings

    def _group_by_role(
        self,
        screenshots: list[ElementScreenshot],
    ) -> dict[str, list[ElementScreenshot]]:
        """Group screenshots by element role.

        Args:
            screenshots: List of ElementScreenshot.

        Returns:
            Dict of role -> list of screenshots.
        """
        groups: dict[str, list[ElementScreenshot]] = {}
        for screenshot in screenshots:
            if screenshot.role not in groups:
                groups[screenshot.role] = []
            groups[screenshot.role].append(screenshot)
        return groups

    def _compute_avg_similarity(
        self,
        indices: list[int],
        distance_matrix: list[list[float]],
    ) -> float:
        """Compute average pairwise similarity within indices.

        Args:
            indices: List of indices in distance matrix.
            distance_matrix: Pairwise similarity matrix.

        Returns:
            Average similarity score.
        """
        if len(indices) < 2:
            return 1.0

        total = 0.0
        count = 0
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                total += distance_matrix[indices[i]][indices[j]]
                count += 1

        return total / count if count > 0 else 1.0

    def _find_representative(
        self,
        indices: list[int],
        distance_matrix: list[list[float]],
    ) -> int:
        """Find the most representative element (highest avg similarity).

        Args:
            indices: List of indices in distance matrix.
            distance_matrix: Pairwise similarity matrix.

        Returns:
            Index of representative element.
        """
        if len(indices) == 1:
            return indices[0]

        best_idx = indices[0]
        best_avg = 0.0

        for i in indices:
            avg = sum(distance_matrix[i][j] for j in indices if j != i)
            avg /= len(indices) - 1

            if avg > best_avg:
                best_avg = avg
                best_idx = i

        return best_idx


__all__ = [
    "ElementScreenshot",
    "VisualCluster",
    "VisualClusteringResult",
    "ScreenshotCapture",
    "VisualClusteringEngine",
]
