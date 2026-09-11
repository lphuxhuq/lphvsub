"""Tests for BrowserPool singleton and context lifecycle."""

from unittest.mock import MagicMock, patch

from autodub.media.download.browser_pool import BrowserPool, get_browser_pool


def test_browser_pool_singleton():
    pool1 = BrowserPool()
    pool2 = get_browser_pool()
    assert pool1 is pool2


def test_browser_pool_lifecycle_mocked():
    pool = BrowserPool()

    mock_playwright = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_playwright.chromium.launch.return_value = mock_browser
    mock_browser.is_connected.return_value = True
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = mock_playwright

        pool._browser = None
        pool._playwright = None

        with pool.borrow_page() as page:
            assert page is mock_page
            mock_browser.new_context.assert_called_once()
            mock_context.add_init_script.assert_called_once()

        mock_page.close.assert_called_once()
        mock_context.close.assert_called_once()

        pool.shutdown()
        mock_browser.close.assert_called_once()
        mock_playwright.stop.assert_called_once()


def test_browser_pool_reconnect_on_disconnect():
    pool = BrowserPool()

    mock_playwright = MagicMock()
    mock_browser_dead = MagicMock()
    mock_browser_dead.is_connected.return_value = False

    mock_browser_alive = MagicMock()
    mock_browser_alive.is_connected.return_value = True

    mock_playwright.chromium.launch.return_value = mock_browser_alive

    with patch("playwright.sync_api.sync_playwright") as mock_sync:
        mock_sync.return_value.start.return_value = mock_playwright

        pool._browser = mock_browser_dead
        pool._playwright = mock_playwright

        b = pool._ensure_browser()
        assert b is mock_browser_alive
        mock_browser_dead.close.assert_called()

        pool.shutdown()
