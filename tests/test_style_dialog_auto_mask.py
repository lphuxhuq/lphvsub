import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from autodub.config import Settings
from autodub.editor import auto_detect_hardsub_regions
from autodub_gui.style_dialog import StyleDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_auto_detect_hardsub_regions_in_editor(tmp_path, monkeypatch):
    work_dir = str(tmp_path / "proj")
    os.makedirs(work_dir, exist_ok=True)
    video_path = os.path.join(work_dir, "source.mp4")
    with open(video_path, "wb") as f:
        f.write(b"video content")

    from autodub.media import hardsub_detector
    monkeypatch.setattr(
        hardsub_detector, "detect_hardsub_regions",
        lambda p: [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}]
    )

    regions = auto_detect_hardsub_regions(work_dir)
    assert len(regions) == 1
    assert regions[0]["y"] == 0.8


def test_style_dialog_auto_detect_button(qapp, tmp_path, monkeypatch):
    video_path = str(tmp_path / "test.mp4")
    with open(video_path, "wb") as f:
        f.write(b"video content")

    from autodub.media import hardsub_detector
    monkeypatch.setattr(
        hardsub_detector, "detect_hardsub_regions",
        lambda p: [{"x": 0.15, "y": 0.82, "w": 0.70, "h": 0.10}]
    )

    dialog = StyleDialog(video_path, Settings().subtitle_style())
    dialog.btn_auto_detect.click()

    regions = dialog.regions()
    assert len(regions) >= 1
    dialog.close()
