"""BrowserPool singleton for reusing Chromium instances and contexts in Playwright."""

from __future__ import annotations

import atexit
import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-features=IsolateOrigins,site-per-process",
]

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
)


class BrowserPool:
    """Singleton pool managing a persistent Playwright Chromium browser."""

    _instance: BrowserPool | None = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, headless: bool = True):
        if getattr(self, "_initialized", False):
            return

        self._headless = headless
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._active_contexts_count = 0
        self._initialized = True
        atexit.register(self.shutdown)

    def is_available(self) -> bool:
        """Checks if Playwright is installed and importable."""
        try:
            import playwright  # noqa: F401 — import probe

            return True
        except ImportError:
            return False

    def _ensure_browser(self):
        """Ensures the browser instance is running and healthy."""
        if self._browser is not None:
            try:
                if self._browser.is_connected():
                    return self._browser
            except Exception:
                logger.debug("Bỏ qua lỗi Exception trong browser_pool.py", exc_info=True)
            logger.warning("Browser instance disconnected or unhealthy, recycling...")
            self._close_browser_quietly()

        from playwright.sync_api import sync_playwright

        if self._playwright is None:
            self._playwright = sync_playwright().start()

        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=_DEFAULT_LAUNCH_ARGS,
        )
        logger.info("BrowserPool: Chromium launched and ready for reuse.")
        return self._browser

    def _close_browser_quietly(self):
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                logger.debug("Bỏ qua lỗi Exception trong browser_pool.py", exc_info=True)
            self._browser = None

    def acquire_context(
        self,
        user_agent: str = _DEFAULT_UA,
        locale: str = "zh-CN",
        viewport: dict | None = None,
    ):
        """Acquires a new, isolated browser context from the pool."""
        with self._lock:
            browser = self._ensure_browser()
            vp = viewport or {"width": 1280, "height": 800}
            context = browser.new_context(
                user_agent=user_agent,
                viewport=vp,
                locale=locale,
            )
            context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            self._active_contexts_count += 1
            return context

    def release_context(self, context):
        """Safely closes a context and updates count."""
        if context is None:
            return
        with self._lock:
            try:
                context.close()
            except Exception as e:
                logger.debug(f"Error closing browser context: {e}")
            finally:
                self._active_contexts_count = max(0, self._active_contexts_count - 1)

    @contextmanager
    def borrow_context(
        self,
        user_agent: str = _DEFAULT_UA,
        locale: str = "zh-CN",
        viewport: dict | None = None,
    ) -> Generator[Any, None, None]:
        """Context manager for acquiring and safely releasing a browser context."""
        ctx = self.acquire_context(user_agent=user_agent, locale=locale, viewport=viewport)
        try:
            yield ctx
        finally:
            self.release_context(ctx)

    @contextmanager
    def borrow_page(
        self,
        user_agent: str = _DEFAULT_UA,
        locale: str = "zh-CN",
        viewport: dict | None = None,
    ) -> Generator[Any, None, None]:
        """Context manager for acquiring a page in an isolated context and safely cleaning up."""
        with self.borrow_context(user_agent=user_agent, locale=locale, viewport=viewport) as ctx:
            page = ctx.new_page()
            try:
                yield page
            finally:
                try:
                    page.close()
                except Exception:
                    logger.debug("Bỏ qua lỗi Exception trong browser_pool.py", exc_info=True)

    def shutdown(self):
        """Gracefully shuts down the browser and stops Playwright."""
        with self._lock:
            self._close_browser_quietly()
            if self._playwright is not None:
                try:
                    self._playwright.stop()
                except Exception:
                    logger.debug("Bỏ qua lỗi Exception trong browser_pool.py", exc_info=True)
                self._playwright = None
            self._active_contexts_count = 0
            logger.info("BrowserPool: Chromium and Playwright cleanly shut down.")


def get_browser_pool() -> BrowserPool:
    return BrowserPool()
