import pytest
from PySide6.QtWidgets import QApplication
from autodub_gui.pages.gemini_srt_page import GeminiSrtPage
from autodub.config import Settings

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_gemini_srt_page_construct(qapp):
    page = GeminiSrtPage(Settings.load)
    assert page is not None
    assert hasattr(page, "server_manager")
    assert hasattr(page, "cleanup")
    assert hasattr(page, "shutdown")
    assert hasattr(page, "on_shown")
    page.cleanup()
