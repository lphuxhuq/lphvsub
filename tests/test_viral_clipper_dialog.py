import pytest
from PySide6.QtWidgets import QLabel
from autodub.config import Settings
from autodub.editor import EditorState
from autodub.languages import get_target
from autodub_gui.viral_clipper_dialog import ClipCard, ViralClipperDialog


def test_clip_card_widget(qtbot):
    clip_data = {
        "id": 1,
        "title": "Khoảnh khắc sốc nhất",
        "hook_text": "Bí mật được tiết lộ",
        "start": 10.0,
        "end": 45.0,
        "duration": 35.0,
        "viral_score": 92,
        "reason": "Cú twist bất ngờ",
    }
    card = ClipCard(clip_data)
    qtbot.addWidget(card)

    labels = [lbl.text() for lbl in card.findChildren(QLabel)]
    assert any("92/100" in t for t in labels)
    assert any("Khoảnh khắc sốc nhất" in t for t in labels)
    assert card.clip_id == 1
    assert card.btn_export.text() == "Xuất Shorts 9:16"

    # Test state change
    card.set_exporting(True)
    assert not card.progress_bar.isHidden()
    assert card.btn_export.isEnabled() is False

    card.mark_completed("/tmp/out.mp4")
    assert card.progress_bar.isHidden()
    assert not card.btn_open.isHidden()
    assert card.out_path == "/tmp/out.mp4"


def test_viral_clipper_dialog(qtbot, tmp_path):
    d = tmp_path / "project_sample"
    d.mkdir()

    state = EditorState(
        work_dir=str(d),
        target=get_target("vi"),
        segments=[
            {"id": 1, "start": 0.0, "end": 10.0, "text": "Đoạn 1", "text_vi": "Đoạn 1"},
            {"id": 2, "start": 10.5, "end": 45.0, "text": "Đoạn 2 sốc kinh hoàng", "text_vi": "Đoạn 2 sốc kinh hoàng"},
        ],
    )
    dialog = ViralClipperDialog(None, state, settings=Settings())
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "AI Viral Shorts & Reels Clipper (9:16)"
    assert len(dialog._cards) >= 1
    assert dialog.btn_export_all is not None
