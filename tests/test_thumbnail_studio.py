import json
import os
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from autodub_gui.thumbnail_dialog import ThumbnailStudioDialog
from autodub_gui.pages.editor_panels import ExportPanel


@pytest.fixture(scope="session")
def qapp():
    """Khởi tạo QApplication cho toàn bộ test session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_thumbnail_studio_initialization(qapp, tmp_path):
    """Kiểm tra khởi tạo ThumbnailStudioDialog độc lập, không lỗi."""
    work_dir = str(tmp_path / "proj")
    os.makedirs(work_dir, exist_ok=True)

    dlg = ThumbnailStudioDialog(work_dir=work_dir, initial_title="Xuyên Không - Làm Giàu")
    assert dlg.input_top.text() == "Xuyên Không"
    assert dlg.input_bottom.text() == "Làm Giàu"
    assert dlg.input_badge.text() == "1-100"
    assert dlg.combo_preset.count() == 3
    assert dlg.combo_aspect.count() == 2
    dlg.close()


def test_thumbnail_studio_metadata_single_source_of_truth(qapp, tmp_path):
    """Kiểm tra Single Source of Truth metadata JSON."""
    work_dir = str(tmp_path / "proj_meta")
    yt_dir = os.path.join(work_dir, "youtube")
    os.makedirs(yt_dir, exist_ok=True)

    # Ghi metadata trước
    meta_path = os.path.join(yt_dir, "youtube_metadata.json")
    saved_meta = {
        "title": "Quân Sư - Đại Chiến",
        "top_title": "SIÊU CẤP QUÂN SƯ",
        "bottom_title": "ĐẠI CHIẾN QUÂN PHIỆT",
        "badge_text": "TẬP 50",
        "preset": "quan_su",
        "timestamp_sec": 12.5,
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(saved_meta, f, ensure_ascii=False, indent=2)

    # Khởi tạo dialog, kiểm tra dialog đọc đúng metadata đã lưu
    dlg = ThumbnailStudioDialog(work_dir=work_dir)
    assert dlg.input_top.text() == "SIÊU CẤP QUÂN SƯ"
    assert dlg.input_bottom.text() == "ĐẠI CHIẾN QUÂN PHIỆT"
    assert dlg.input_badge.text() == "TẬP 50"
    assert dlg.combo_preset.currentData() == "quan_su"
    dlg.close()


def test_thumbnail_studio_save_both_aspects(qapp, tmp_path):
    """Kiểm tra chức năng lưu Thumbnail xuất đủ 16:9 và 9:16 và metadata JSON."""
    work_dir = str(tmp_path / "proj_save")
    yt_dir = os.path.join(work_dir, "youtube")
    os.makedirs(yt_dir, exist_ok=True)

    # Tạo một frame giả lập
    frame_path = os.path.join(yt_dir, "thumbnail_original.jpg")
    img = Image.new("RGB", (1280, 720), color=(50, 40, 80))
    img.save(frame_path)

    dlg = ThumbnailStudioDialog(work_dir=work_dir, initial_title="Xuyên Không Cổ Đại")
    dlg.input_top.setText("XUYÊN KHÔNG CỔ ĐẠI")
    dlg.input_bottom.setText("TƯ DUY LÀM GIÀU")
    dlg.input_badge.setText("FULL 1-100")
    dlg.combo_preset.setCurrentIndex(0)  # co_dai

    saved_signal_paths = []
    dlg.thumbnail_saved.connect(saved_signal_paths.append)

    # Kích hoạt lưu
    dlg._save_thumbnail()

    out_16_9 = os.path.join(yt_dir, "thumbnail_landscape.jpg")
    out_9_16 = os.path.join(yt_dir, "thumbnail_portrait.jpg")
    meta_path = os.path.join(yt_dir, "youtube_metadata.json")

    assert os.path.exists(out_16_9)
    assert os.path.exists(out_9_16)
    assert os.path.exists(meta_path)
    assert len(saved_signal_paths) == 1
    assert saved_signal_paths[0] == out_16_9

    with Image.open(out_16_9) as im16:
        assert im16.size == (1280, 720)
    with Image.open(out_9_16) as im9:
        assert im9.size == (720, 1280)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta_data = json.load(f)
    assert meta_data["top_title"] == "XUYÊN KHÔNG CỔ ĐẠI"
    assert meta_data["bottom_title"] == "TƯ DUY LÀM GIÀU"
    assert meta_data["badge_text"] == "FULL 1-100"
    dlg.close()


def test_export_panel_metadata_and_thumb_preview(qapp, tmp_path):
    """Kiểm tra ExportPanel hiển thị thumbnail preview thu nhỏ và thông tin metadata."""
    panel = ExportPanel()

    # Tạo ảnh thumbnail mẫu
    thumb_path = str(tmp_path / "thumb_preview.jpg")
    img = Image.new("RGB", (640, 360), color=(80, 50, 120))
    img.save(thumb_path)

    meta = {
        "title": "TẬP 1: SIÊU PHẨM XUYÊN KHÔNG",
        "hashtags": ["#shorts", "#reviewphim", "#manhwa"],
        "description": "Tóm tắt truyện tranh siêu phẩm hấp dẫn nhất hiện nay.",
    }

    panel.set_social_metadata(meta, video_name="output_video.mp4", thumb_path=thumb_path)

    assert not panel.thumb_preview.isHidden()
    assert not panel.video_meta_info.isHidden()
    text = panel.video_meta_info.text()
    assert "output_video.mp4" in text
    assert "TẬP 1: SIÊU PHẨM XUYÊN KHÔNG" in text
    assert "#reviewphim" in text


def test_thumbnail_studio_episode_stepping(qapp, tmp_path):
    """Kiểm tra tăng / giảm số tập thông minh cho cả tập lẻ và dải tập."""
    work_dir = str(tmp_path / "proj_step")
    os.makedirs(work_dir, exist_ok=True)
    dlg = ThumbnailStudioDialog(work_dir=work_dir)

    # 1. Tập lẻ
    dlg.input_badge.setText("TẬP 12")
    dlg._step_episode(+1)
    assert dlg.input_badge.text() == "TẬP 13"
    dlg._step_episode(-1)
    assert dlg.input_badge.text() == "TẬP 12"

    # 2. Dải tập
    dlg.input_badge.setText("1-100")
    dlg._step_episode(+1)
    assert dlg.input_badge.text() == "101-200"
    dlg._step_episode(-1)
    assert dlg.input_badge.text() == "1-100"

    dlg.close()


def test_thumbnail_studio_detect_from_link_meta(qapp, tmp_path):
    """Kiểm tra tự động phát hiện số tập từ source_url của link Bilibili/YouTube lưu trong video_meta."""
    work_dir = str(tmp_path / "proj_detect_link")
    data_d = os.path.join(work_dir, "data")
    os.makedirs(data_d, exist_ok=True)

    # Giả lập video_meta.json chứa link Bilibili có ?p=17
    with open(os.path.join(data_d, "video_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "source_url": "https://www.bilibili.com/video/BV1xx411c7mD?p=17",
            "title": "Đấu Phá Thương Khung Phần 5",
        }, f)

    dlg = ThumbnailStudioDialog(work_dir=work_dir)
    dlg._detect_badge_now()
    assert dlg.input_badge.text() == "TẬP 17"
    dlg.close()

