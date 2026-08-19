import time
import requests
import pytest
from autodub.tools.gemini_srt_ui.server_manager import GeminiSrtServerManager

def test_server_manager_lifecycle():
    manager = GeminiSrtServerManager()
    assert not manager.is_running()

    url = manager.start(port=5991, open_browser=False)
    try:
        assert manager.is_running()
        assert "5991" in url
        assert manager.get_url() == url

        time.sleep(0.5)
        resp = requests.get(url + "/", timeout=3)
        assert resp.status_code == 200
        assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower()

        # Test sync endpoint
        resp_sync = requests.get(url + "/api/voxdub/config", timeout=3)
        assert resp_sync.status_code == 200
        data = resp_sync.json()
        assert data.get("ok") is True
        assert "config" in data
    finally:
        manager.stop()
        time.sleep(0.5)
        assert not manager.is_running()
