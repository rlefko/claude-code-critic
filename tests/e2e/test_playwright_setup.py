"""E2E tests for Playwright setup and basic crawling.

These tests require Playwright to be installed:
    pip install playwright
    playwright install chromium
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile

# Skip all tests if Playwright is not available
pytest.importorskip("playwright", reason="Playwright not installed")


class TestRuntimeCollectorInit:
    """Tests for RuntimeCollector initialization."""

    def test_init_creates_screenshot_dir(self):
        """Test that initialization creates screenshot directory."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            config = UIQualityConfig()
            config.output.screenshot_dir = "screenshots"

            collector = RuntimeCollector(
                config=config,
                project_path=tmpdir,
            )

            expected_dir = Path(tmpdir) / "screenshots"
            assert collector.screenshot_dir == expected_dir
            assert expected_dir.exists()

    def test_init_with_custom_screenshot_dir(self):
        """Test initialization with custom screenshot directory."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / "custom_screenshots"

            collector = RuntimeCollector(screenshot_dir=custom_dir)

            assert collector.screenshot_dir == custom_dir
            assert custom_dir.exists()

    def test_crawl_config_property(self):
        """Test crawl config property returns correct config."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig

        config = UIQualityConfig()
        config.crawl.max_pages_per_run = 100
        config.crawl.max_elements_per_role = 25

        collector = RuntimeCollector(config=config)

        assert collector.crawl_config.max_pages_per_run == 100
        assert collector.crawl_config.max_elements_per_role == 25


class TestCrawlTarget:
    """Tests for CrawlTarget dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget
        from claude_indexer.ui.config import ViewportConfig

        target = CrawlTarget(
            url="http://localhost:6006/iframe.html?id=button--primary",
            page_id="button--primary@desktop",
            story_id="button--primary",
            viewport=ViewportConfig("desktop", 1440, 900),
        )

        data = target.to_dict()

        assert data["url"] == "http://localhost:6006/iframe.html?id=button--primary"
        assert data["page_id"] == "button--primary@desktop"
        assert data["story_id"] == "button--primary"
        assert data["viewport"]["name"] == "desktop"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        from claude_indexer.ui.collectors.runtime import CrawlTarget

        data = {
            "url": "http://localhost:3000/login",
            "page_id": "/login@mobile",
            "story_id": None,
            "viewport": {"name": "mobile", "width": 375, "height": 812},
        }

        target = CrawlTarget.from_dict(data)

        assert target.url == "http://localhost:3000/login"
        assert target.page_id == "/login@mobile"
        assert target.story_id is None
        assert target.viewport.name == "mobile"


class TestCrawlResult:
    """Tests for CrawlResult dataclass."""

    def test_has_errors(self):
        """Test error detection."""
        from claude_indexer.ui.collectors.runtime import CrawlResult, CrawlTarget

        target = CrawlTarget(url="http://example.com", page_id="test")

        # No errors
        result = CrawlResult(target=target, errors=[])
        assert result.has_errors is False

        # With errors
        result = CrawlResult(target=target, errors=["Connection failed"])
        assert result.has_errors is True

    def test_element_count(self):
        """Test element count property."""
        from claude_indexer.ui.collectors.runtime import CrawlResult, CrawlTarget
        from claude_indexer.ui.models import RuntimeElementFingerprint

        target = CrawlTarget(url="http://example.com", page_id="test")

        fingerprints = [
            RuntimeElementFingerprint(
                page_id="test",
                selector=f"button:nth({i})",
                role="button",
            )
            for i in range(5)
        ]

        result = CrawlResult(target=target, fingerprints=fingerprints)
        assert result.element_count == 5


class TestBuildTargetList:
    """Tests for target list building."""

    def test_build_from_routes(self):
        """Test building targets from routes."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig, ViewportConfig

        config = UIQualityConfig()
        config.crawl.routes = ["/login", "/signup", "/dashboard"]
        config.crawl.viewports = [ViewportConfig("desktop", 1440, 900)]
        config.crawl.storybook_url = "http://localhost:3000"

        collector = RuntimeCollector(config=config)
        targets = collector.build_target_list()

        assert len(targets) == 3
        assert any("/login" in t.url for t in targets)
        assert any("/signup" in t.url for t in targets)
        assert any("/dashboard" in t.url for t in targets)

    def test_build_with_focus_filter(self):
        """Test target filtering with focus parameter."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig, ViewportConfig

        config = UIQualityConfig()
        config.crawl.routes = ["/login", "/signup", "/dashboard"]
        config.crawl.viewports = [ViewportConfig("desktop", 1440, 900)]
        config.crawl.storybook_url = "http://localhost:3000"

        collector = RuntimeCollector(config=config)
        targets = collector.build_target_list(focus="login")

        assert len(targets) == 1
        assert "/login" in targets[0].url

    def test_build_with_max_pages_limit(self):
        """Test that max_pages_per_run limits targets."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig, ViewportConfig

        config = UIQualityConfig()
        config.crawl.routes = [f"/page{i}" for i in range(100)]
        config.crawl.viewports = [ViewportConfig("desktop", 1440, 900)]
        config.crawl.max_pages_per_run = 10

        collector = RuntimeCollector(config=config)
        targets = collector.build_target_list()

        assert len(targets) == 10

    def test_build_with_multiple_viewports(self):
        """Test building targets with multiple viewports."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector
        from claude_indexer.ui.config import UIQualityConfig, ViewportConfig

        config = UIQualityConfig()
        config.crawl.routes = ["/home"]
        config.crawl.viewports = [
            ViewportConfig("mobile", 375, 812),
            ViewportConfig("tablet", 768, 1024),
            ViewportConfig("desktop", 1440, 900),
        ]

        collector = RuntimeCollector(config=config)
        targets = collector.build_target_list()

        # 1 route × 3 viewports = 3 targets
        assert len(targets) == 3
        assert any("mobile" in t.page_id for t in targets)
        assert any("tablet" in t.page_id for t in targets)
        assert any("desktop" in t.page_id for t in targets)


class TestDisableAnimationsCSS:
    """Tests for animation disabling CSS."""

    def test_disable_animations_css_defined(self):
        """Test that animation disabling CSS is defined."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        css = RuntimeCollector.DISABLE_ANIMATIONS_CSS

        assert "animation-duration" in css
        assert "transition-duration" in css
        assert "!important" in css


class TestServerManagement:
    """Tests for server lifecycle management."""

    @pytest.mark.asyncio
    async def test_wait_for_server_success(self):
        """Test successful server wait."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock()

            mock_session = MagicMock()
            mock_session.get = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock()

            mock_session_class.return_value = mock_session

            collector = RuntimeCollector()
            result = await collector.wait_for_server("http://localhost:6006", timeout=1)

            # Should succeed with 200 response
            assert result is True


class TestPlaywrightIntegration:
    """Integration tests that require actual Playwright."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager usage."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        collector = RuntimeCollector()

        # Mock playwright
        with patch.object(collector, "_start_playwright", new_callable=AsyncMock):
            with patch.object(collector, "_stop_playwright", new_callable=AsyncMock):
                async with collector:
                    # Inside context, should have called start
                    collector._start_playwright.assert_called_once()

                # After context, should have called stop
                collector._stop_playwright.assert_called_once()

    @pytest.mark.asyncio
    async def test_inject_disable_animations(self):
        """Test animation disabling injection."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        collector = RuntimeCollector()

        mock_page = AsyncMock()
        mock_page.add_style_tag = AsyncMock()

        await collector._inject_disable_animations(mock_page)

        mock_page.add_style_tag.assert_called_once()
        call_args = mock_page.add_style_tag.call_args
        assert "animation-duration" in call_args.kwargs["content"]

    @pytest.mark.asyncio
    async def test_wait_for_stable_layout(self):
        """Test layout stability detection."""
        from claude_indexer.ui.collectors.runtime import RuntimeCollector

        collector = RuntimeCollector()

        # Mock page that returns stable dimensions
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(
            return_value={
                "scrollHeight": 1000,
                "scrollWidth": 1200,
                "bodyHeight": 1000,
                "bodyWidth": 1200,
            }
        )

        result = await collector._wait_for_stable_layout(mock_page, timeout_ms=500)

        # Should return True after dimensions stabilize
        assert result is True
        mock_page.evaluate.assert_called()


class TestCrawlSingleTarget:
    """Tests for single target crawling."""

    @pytest.mark.asyncio
    async def test_crawl_handles_navigation_error(self):
        """Test that navigation errors are handled gracefully."""
        from claude_indexer.ui.collectors.runtime import (
            CrawlResult,
            CrawlTarget,
            RuntimeCollector,
        )

        collector = RuntimeCollector()
        collector._browser = MagicMock()

        # Mock context that fails on navigation
        mock_context = MagicMock()
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_context.close = AsyncMock()
        collector._browser.new_context = AsyncMock(return_value=mock_context)

        target = CrawlTarget(
            url="http://invalid-url.local",
            page_id="test",
        )

        # Mock dependencies
        with patch(
            "claude_indexer.ui.collectors.runtime.ElementTargetingStrategy"
        ), patch(
            "claude_indexer.ui.collectors.runtime.ComputedStyleCapture"
        ), patch(
            "claude_indexer.ui.collectors.runtime.PseudoStateCapture"
        ), patch(
            "claude_indexer.ui.collectors.runtime.ScreenshotCapture"
        ):
            result = await collector._crawl_single_target(
                target=target,
                targeting=MagicMock(),
                style_capture=MagicMock(),
                pseudo_capture=MagicMock(),
                screenshot_capture=MagicMock(),
            )

        assert result.has_errors
        assert any("failed" in err.lower() for err in result.errors)
