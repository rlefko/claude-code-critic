"""Runtime collector for Playwright-based UI analysis.

Crawls Storybook or application routes to capture computed styles,
screenshots, and element fingerprints from rendered UI.
"""

import asyncio
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        async_playwright,
    )

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Browser = None
    BrowserContext = None
    Page = None
    Playwright = None
    async_playwright = None

import aiohttp

from ..config import CrawlConfig, UIQualityConfig, ViewportConfig
from ..models import LayoutBox, RuntimeElementFingerprint


@dataclass
class CrawlTarget:
    """A page/story to crawl."""

    url: str
    page_id: str  # Unique identifier (route path or story ID)
    story_id: str | None = None  # Storybook story ID if applicable
    viewport: ViewportConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "page_id": self.page_id,
            "story_id": self.story_id,
            "viewport": self.viewport.to_dict() if self.viewport else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlTarget":
        """Create from dictionary."""
        viewport = None
        if data.get("viewport"):
            viewport = ViewportConfig.from_dict(data["viewport"])
        return cls(
            url=data["url"],
            page_id=data["page_id"],
            story_id=data.get("story_id"),
            viewport=viewport,
        )


@dataclass
class CrawlResult:
    """Result of crawling a single page/story."""

    target: CrawlTarget
    fingerprints: list[RuntimeElementFingerprint] = field(default_factory=list)
    screenshots_dir: Path | None = None
    errors: list[str] = field(default_factory=list)
    crawl_time_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "target": self.target.to_dict(),
            "fingerprints": [fp.to_dict() for fp in self.fingerprints],
            "screenshots_dir": str(self.screenshots_dir) if self.screenshots_dir else None,
            "errors": self.errors,
            "crawl_time_ms": self.crawl_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlResult":
        """Create from dictionary."""
        return cls(
            target=CrawlTarget.from_dict(data["target"]),
            fingerprints=[
                RuntimeElementFingerprint.from_dict(fp)
                for fp in data.get("fingerprints", [])
            ],
            screenshots_dir=Path(data["screenshots_dir"])
            if data.get("screenshots_dir")
            else None,
            errors=data.get("errors", []),
            crawl_time_ms=data.get("crawl_time_ms", 0.0),
        )

    @property
    def has_errors(self) -> bool:
        """Check if crawl had any errors."""
        return len(self.errors) > 0

    @property
    def element_count(self) -> int:
        """Number of elements captured."""
        return len(self.fingerprints)


class RuntimeCollector:
    """Playwright-based runtime UI element collector.

    Crawls Storybook stories or application routes to capture:
    - Computed styles from rendered elements
    - Element screenshots for visual clustering
    - Pseudo-state styles (hover, focus, disabled)
    """

    # CSS to disable animations for consistent screenshots
    DISABLE_ANIMATIONS_CSS = """
        *, *::before, *::after {
            animation-duration: 0.001s !important;
            animation-delay: 0s !important;
            transition-duration: 0.001s !important;
            transition-delay: 0s !important;
            scroll-behavior: auto !important;
        }
    """

    def __init__(
        self,
        config: UIQualityConfig | None = None,
        project_path: Path | str | None = None,
        screenshot_dir: Path | str | None = None,
    ):
        """Initialize the runtime collector.

        Args:
            config: UI quality configuration.
            project_path: Project root path.
            screenshot_dir: Directory for screenshots (overrides config).
        """
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is required for runtime collection. "
                "Install with: pip install playwright && playwright install chromium"
            )

        self.config = config or UIQualityConfig()
        self.project_path = Path(project_path) if project_path else Path.cwd()

        # Set up screenshot directory
        if screenshot_dir:
            self.screenshot_dir = Path(screenshot_dir)
        else:
            self.screenshot_dir = self.project_path / self.config.output.screenshot_dir

        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # Server management
        self._server_process: subprocess.Popen | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None

    @property
    def crawl_config(self) -> CrawlConfig:
        """Get the crawl configuration."""
        return self.config.crawl

    async def __aenter__(self) -> "RuntimeCollector":
        """Async context manager entry."""
        await self._start_playwright()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self._stop_playwright()
        self._stop_server()

    async def _start_playwright(self) -> None:
        """Start Playwright browser."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)

    async def _stop_playwright(self) -> None:
        """Stop Playwright browser."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _stop_server(self) -> None:
        """Stop any started server process."""
        if self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
            self._server_process = None

    async def start_storybook(self) -> subprocess.Popen | None:
        """Start Storybook server if configured.

        Returns:
            Subprocess handle if server was started, None otherwise.
        """
        cmd = self.crawl_config.storybook_start_command
        if not cmd:
            return None

        # Start the server process
        self._server_process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=self.project_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        url = self.crawl_config.storybook_url or "http://localhost:6006"
        if await self.wait_for_server(url, timeout=60):
            return self._server_process

        # Server failed to start
        self._stop_server()
        return None

    async def wait_for_server(self, url: str, timeout: int = 30) -> bool:
        """Wait for server to be available.

        Args:
            url: URL to check.
            timeout: Maximum seconds to wait.

        Returns:
            True if server became available, False otherwise.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                        if response.status < 500:
                            return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    def build_target_list(
        self,
        focus: str | None = None,
        story_filter: list[str] | None = None,
    ) -> list[CrawlTarget]:
        """Build list of pages/stories to crawl.

        Args:
            focus: Optional focus string to filter targets.
            story_filter: Optional list of story IDs to include.

        Returns:
            List of CrawlTarget instances.
        """
        targets: list[CrawlTarget] = []
        base_url = self.crawl_config.storybook_url or ""

        # Add routes
        for route in self.crawl_config.routes:
            # Apply focus filter
            if focus and focus.lower() not in route.lower():
                continue

            for viewport in self.crawl_config.viewports:
                targets.append(
                    CrawlTarget(
                        url=f"{base_url.rstrip('/')}{route}",
                        page_id=f"{route}@{viewport.name}",
                        viewport=viewport,
                    )
                )

        # Apply story filter if provided
        if story_filter:
            for story_id in story_filter:
                # Apply focus filter
                if focus and focus.lower() not in story_id.lower():
                    continue

                iframe_url = f"{base_url}/iframe.html?id={story_id}&viewMode=story"
                for viewport in self.crawl_config.viewports:
                    targets.append(
                        CrawlTarget(
                            url=iframe_url,
                            page_id=f"{story_id}@{viewport.name}",
                            story_id=story_id,
                            viewport=viewport,
                        )
                    )

        # Limit targets
        max_pages = self.crawl_config.max_pages_per_run
        if len(targets) > max_pages:
            targets = targets[:max_pages]

        return targets

    async def crawl(
        self,
        targets: list[CrawlTarget] | None = None,
        headless: bool = True,
    ) -> list[CrawlResult]:
        """Crawl all targets and collect fingerprints.

        Args:
            targets: List of targets to crawl (built automatically if None).
            headless: Whether to run browser in headless mode.

        Returns:
            List of CrawlResult for each target.
        """
        # Import here to avoid circular imports
        from .element_targeting import ElementTargetingStrategy
        from .pseudo_states import PseudoStateCapture
        from .screenshots import ScreenshotCapture
        from .style_capture import ComputedStyleCapture

        if targets is None:
            targets = self.build_target_list()

        results: list[CrawlResult] = []

        # Initialize collectors
        style_capture = ComputedStyleCapture()
        pseudo_capture = PseudoStateCapture(style_capture=style_capture)
        screenshot_capture = ScreenshotCapture(output_dir=self.screenshot_dir)
        targeting = ElementTargetingStrategy(
            roles=self.crawl_config.element_targeting.roles,
            test_id_patterns=self.crawl_config.element_targeting.test_id_patterns,
            max_elements_per_role=self.crawl_config.max_elements_per_role,
        )

        # Ensure playwright is started
        if not self._browser:
            await self._start_playwright()

        for target in targets:
            result = await self._crawl_single_target(
                target=target,
                targeting=targeting,
                style_capture=style_capture,
                pseudo_capture=pseudo_capture,
                screenshot_capture=screenshot_capture,
            )
            results.append(result)

        return results

    async def _crawl_single_target(
        self,
        target: CrawlTarget,
        targeting: "ElementTargetingStrategy",
        style_capture: "ComputedStyleCapture",
        pseudo_capture: "PseudoStateCapture",
        screenshot_capture: "ScreenshotCapture",
    ) -> CrawlResult:
        """Crawl a single target and collect element fingerprints.

        Args:
            target: The target to crawl.
            targeting: Element targeting strategy.
            style_capture: Computed style capture.
            pseudo_capture: Pseudo-state capture.
            screenshot_capture: Screenshot capture.

        Returns:
            CrawlResult with captured fingerprints.
        """
        start_time = time.time()
        errors: list[str] = []
        fingerprints: list[RuntimeElementFingerprint] = []

        try:
            # Create browser context with viewport
            viewport = target.viewport or self.crawl_config.viewports[0]
            context = await self._browser.new_context(
                viewport={"width": viewport.width, "height": viewport.height}
            )
            page = await context.new_page()

            try:
                # Setup page
                await self._setup_page(page)

                # Navigate to target
                await page.goto(target.url, wait_until="networkidle", timeout=30000)

                # Wait for stable layout
                if self.crawl_config.wait_for_stable_layout:
                    await self._wait_for_stable_layout(
                        page, self.crawl_config.stable_layout_timeout
                    )

                # Discover elements
                from .element_targeting import DiscoveredElement

                elements = await targeting.discover_elements(page)

                # Capture fingerprints for each element
                for elem in elements:
                    try:
                        fp = await self._capture_element_fingerprint(
                            page=page,
                            element=elem,
                            target=target,
                            style_capture=style_capture,
                            screenshot_capture=screenshot_capture,
                        )
                        if fp:
                            fingerprints.append(fp)
                    except Exception as e:
                        errors.append(f"Element capture failed ({elem.selector}): {e}")

            finally:
                await context.close()

        except Exception as e:
            errors.append(f"Page crawl failed: {e}")

        crawl_time_ms = (time.time() - start_time) * 1000

        return CrawlResult(
            target=target,
            fingerprints=fingerprints,
            screenshots_dir=self.screenshot_dir,
            errors=errors,
            crawl_time_ms=crawl_time_ms,
        )

    async def _capture_element_fingerprint(
        self,
        page: "Page",
        element: "DiscoveredElement",
        target: CrawlTarget,
        style_capture: "ComputedStyleCapture",
        screenshot_capture: "ScreenshotCapture",
    ) -> RuntimeElementFingerprint | None:
        """Capture fingerprint for a single element.

        Args:
            page: Playwright page.
            element: Discovered element.
            target: Crawl target.
            style_capture: Style capture instance.
            screenshot_capture: Screenshot capture instance.

        Returns:
            RuntimeElementFingerprint or None if capture failed.
        """
        try:
            # Get element handle
            locator = page.locator(element.selector).first
            handle = await locator.element_handle()
            if not handle:
                return None

            # Capture computed styles
            styles = await style_capture.capture(handle, page)

            # Get bounding box for layout
            box = await handle.bounding_box()
            layout_box = None
            if box:
                layout_box = LayoutBox(
                    x=box["x"],
                    y=box["y"],
                    width=box["width"],
                    height=box["height"],
                )

            # Capture screenshot and compute hash
            screenshot_hash = None
            if self.config.output.include_screenshots:
                screenshot = await screenshot_capture.capture_element(
                    element=handle,
                    element_id=f"{target.page_id}_{element.selector[:50]}",
                    role=element.role.value,
                    selector=element.selector,
                )
                if screenshot:
                    screenshot_hash = screenshot.phash

            return RuntimeElementFingerprint(
                page_id=target.page_id,
                selector=element.selector,
                role=element.role.value,
                computed_style_subset=styles.to_flat_dict(),
                layout_box=layout_box,
                screenshot_hash=screenshot_hash,
                source_map_hint=element.component_name,
            )

        except Exception:
            return None

    async def _setup_page(self, page: "Page") -> None:
        """Setup page with animation disabling.

        Args:
            page: Playwright page instance.
        """
        # Inject CSS to disable animations
        if self.crawl_config.disable_animations:
            await self._inject_disable_animations(page)

    async def _wait_for_stable_layout(
        self,
        page: "Page",
        timeout_ms: int = 3000,
    ) -> bool:
        """Wait for layout to stabilize (no size changes).

        Args:
            page: Playwright page instance.
            timeout_ms: Maximum time to wait in milliseconds.

        Returns:
            True if layout stabilized, False if timeout.
        """
        stability_check_interval = 100  # ms
        stability_threshold = 3  # consecutive stable checks
        stable_count = 0
        last_dimensions = None

        start_time = time.time()
        while (time.time() - start_time) * 1000 < timeout_ms:
            # Get current page dimensions
            dimensions = await page.evaluate(
                """() => ({
                    scrollHeight: document.documentElement.scrollHeight,
                    scrollWidth: document.documentElement.scrollWidth,
                    bodyHeight: document.body ? document.body.scrollHeight : 0,
                    bodyWidth: document.body ? document.body.scrollWidth : 0,
                })"""
            )

            if last_dimensions == dimensions:
                stable_count += 1
                if stable_count >= stability_threshold:
                    return True
            else:
                stable_count = 0
                last_dimensions = dimensions

            await asyncio.sleep(stability_check_interval / 1000)

        return False

    async def _inject_disable_animations(self, page: "Page") -> None:
        """Inject CSS to disable all animations.

        Args:
            page: Playwright page instance.
        """
        await page.add_style_tag(content=self.DISABLE_ANIMATIONS_CSS)


__all__ = [
    "CrawlTarget",
    "CrawlResult",
    "RuntimeCollector",
]
