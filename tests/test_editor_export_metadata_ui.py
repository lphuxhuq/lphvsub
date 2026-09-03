"""Kiểm thử tính năng hiển thị metadata và các nút sao chép trên ExportPanel."""
import pytest
from PySide6.QtWidgets import QApplication
from autodub_gui.pages.editor_panels import ExportPanel


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_export_panel_social_metadata_rendering(qapp):
    panel = ExportPanel()
    assert panel.video_meta_info is not None
    assert panel.video_meta_info.isHidden()

    meta = {
        "title": "Tóm Tắt Phim Mới Nhất",
        "hashtags": ["#reviewphim", "#shorts", "#trending"]
    }
    panel.set_social_metadata(meta, "video_tap_1.mp4")

    assert not panel.video_meta_info.isHidden()
    html_text = panel.video_meta_info.text()
    assert "video_tap_1.mp4" in html_text
    assert "Tóm Tắt Phim Mới Nhất" in html_text
    assert "#reviewphim #shorts #trending" in html_text


def test_export_panel_copy_buttons_exist(qapp):
    panel = ExportPanel()
    assert hasattr(panel, "btn_copy_title")
    assert hasattr(panel, "btn_copy_tags")
    assert hasattr(panel, "btn_copy_desc")
    assert hasattr(panel, "btn_copy_all")
    assert hasattr(panel, "btn_open_thumb")
