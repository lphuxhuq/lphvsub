"""Kiểm thử cho thanh công cụ Checkpoint và quy trình lưu/nạp cấu hình."""
import os
import json
import pytest
from PySide6.QtWidgets import QApplication
from autodub.config import Settings
from autodub.checkpoint_store import (
    save_checkpoint, load_checkpoint, delete_checkpoint,
    get_checkpoint_names, get_active_checkpoint_name,
)
from autodub_gui.pages.new_project_steps import VoiceStep
from autodub_gui.pages.new_project_page import NewProjectPage


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_voice_step_checkpoint_bar(qapp, tmp_path, monkeypatch):
    """Kiểm tra các thành phần thanh CheckpointBar trên VoiceStep."""
    monkeypatch.setattr("autodub.checkpoint_store.cache_dir", lambda: str(tmp_path))

    save_checkpoint("Kênh Shorts", {"logo": {"logo_path": "logo_shorts.png"}})
    save_checkpoint("Kênh Review", {"logo": {"logo_path": "logo_review.png"}})

    step = VoiceStep()
    assert hasattr(step, "cb_checkpoints")
    assert hasattr(step, "btn_load_checkpoint")
    assert hasattr(step, "btn_save_checkpoint")
    assert hasattr(step, "btn_delete_checkpoint")

    # Nạp danh sách checkpoint vào dropdown
    names = get_checkpoint_names()
    step.reload_checkpoints(names, "Kênh Shorts")
    assert step.cb_checkpoints.count() == 2
    assert step.current_checkpoint_name() == "Kênh Shorts"

    # Kiểm tra tín hiệu Nạp
    loaded = []
    step.checkpoint_load_requested.connect(lambda name: loaded.append(name))
    step.btn_load_checkpoint.click()
    assert loaded == ["Kênh Shorts"]

    # Kiểm tra tín hiệu Lưu
    saved = []
    step.checkpoint_save_requested.connect(lambda name: saved.append(name))
    step.cb_checkpoints.setEditText("Kênh Mới")
    from PySide6.QtWidgets import QInputDialog
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Kênh Mới", True))
    step.btn_save_checkpoint.click()
    assert saved == ["Kênh Mới"]

    # Kiểm tra tín hiệu Xóa
    deleted = []
    step.checkpoint_delete_requested.connect(lambda name: deleted.append(name))
    step.cb_checkpoints.setCurrentText("Kênh Shorts")
    from autodub_gui.ui.modal import ConfirmDialog
    monkeypatch.setattr(ConfirmDialog, "ask", lambda *args, **kwargs: (True, None))
    step.btn_delete_checkpoint.click()
    assert deleted == ["Kênh Shorts"]


def test_voice_step_set_and_load_options(qapp):
    """Kiểm tra cập nhật và khôi phục các nhóm tùy chọn trên VoiceStep."""
    step = VoiceStep()

    # 1. Logo
    step.set_logo_options({
        "logo_path": "d:/branding/watermark_logo.png",
        "logo_position": "bottom_left",
        "logo_scale": 0.20,
        "logo_opacity": 0.90,
        "logo_motion": "bounce",
    })
    vals = step.values()
    assert vals["logo_path"] == "d:/branding/watermark_logo.png"
    assert vals["logo_position"] == "bottom_left"
    assert pytest.approx(vals["logo_scale"], 0.01) == 0.20
    assert pytest.approx(vals["logo_opacity"], 0.01) == 0.90
    assert vals["logo_motion"] == "bounce"

    # 2. Watermark
    step.set_watermark_options({
        "watermark_text": "PHIM HAY 247",
        "watermark_motion": "bottom_right",
        "watermark_opacity": 0.50,
        "watermark_speed": 60,
    })
    vals = step.values()
    assert vals["watermark_text"] == "PHIM HAY 247"
    assert vals["watermark_motion"] == "bottom_right"
    assert pytest.approx(vals["watermark_opacity"], 0.01) == 0.50
    assert vals["watermark_speed"] == 60

    # 3. Anti-Content ID
    step.set_anti_id_options({
        "smart_flip": True,
        "micro_zoom": True,
        "color_filter": "cinematic_warm",
        "randomize_metadata": False,
    })
    vals = step.values()
    assert vals["smart_flip"] is True
    assert vals["micro_zoom"] is True
    assert vals["color_filter"] == "cinematic_warm"
    assert vals["randomize_metadata"] is False


def test_new_project_page_checkpoint_workflow(qapp, tmp_path, monkeypatch):
    """Kiểm tra quy trình Lưu Checkpoint -> Sửa thông số -> Nạp Checkpoint trên NewProjectPage."""
    monkeypatch.setattr("autodub.checkpoint_store.cache_dir", lambda: str(tmp_path))
    env_file = tmp_path / ".env"
    monkeypatch.setattr("autodub_gui.env_store.ENV_PATH", str(env_file))

    settings = Settings(
        logo_path="default_logo.png",
        watermark_text="DEFAULT_WM",
        smart_flip=False,
        video_aspect_preset="original",
    )
    page = NewProjectPage(settings_provider=lambda: settings)

    # 1. Giả lập người dùng chỉnh sửa thiết lập
    page.step_voice.set_logo_options({"logo_path": "custom_logo.png", "logo_position": "top_left"})
    page.step_voice.set_watermark_options({"watermark_text": "VIP SUB", "watermark_motion": "bounce"})
    page.step_voice.set_anti_id_options({"smart_flip": True, "micro_zoom": True, "color_filter": "vintage"})
    page._aspect_preset = "9:16"
    page._reframe_mode = "blur"
    page._banner_opts = {
        "frame_banner_enabled": True,
        "frame_banner_color": "#111111",
        "frame_header_text": "HOT MOVIE",
        "frame_banner_height_ratio": 0.22,
    }
    page._blur_regions = [{"x": 10, "y": 80, "w": 80, "h": 15}]

    # 2. Lưu checkpoint "Kênh TikTok"
    page._on_save_checkpoint("Kênh TikTok")
    names = get_checkpoint_names()
    assert "Kênh TikTok" in names
    assert get_active_checkpoint_name() == "Kênh TikTok"

    # 3. Thay đổi các giá trị trên giao diện sang giá trị khác
    page.step_voice.set_logo_options({"logo_path": ""})
    page.step_voice.set_watermark_options({"watermark_text": ""})
    page.step_voice.set_anti_id_options({"smart_flip": False, "micro_zoom": False, "color_filter": "none"})
    page._aspect_preset = "16:9"
    page._banner_opts = {}
    page._blur_regions = []

    vals_changed = page.values()
    assert vals_changed["logo_path"] == ""
    assert vals_changed["watermark_text"] == ""
    assert vals_changed["smart_flip"] is False
    assert vals_changed["aspect_preset"] == "16:9"
    assert len(vals_changed["blur_regions"]) == 0

    # 4. Nạp lại checkpoint "Kênh TikTok"
    page._on_load_checkpoint("Kênh TikTok")

    vals_restored = page.values()
    assert vals_restored["logo_path"] == "custom_logo.png"
    assert vals_restored["logo_position"] == "top_left"
    assert vals_restored["watermark_text"] == "VIP SUB"
    assert vals_restored["smart_flip"] is True
    assert vals_restored["micro_zoom"] is True
    assert vals_restored["color_filter"] == "vintage"
    assert vals_restored["aspect_preset"] == "9:16"
    assert vals_restored["reframe_mode"] == "blur"
    assert page._banner_opts["frame_banner_enabled"] is True
    assert page._banner_opts["frame_header_text"] == "HOT MOVIE"
    assert page._banner_opts["frame_banner_height_ratio"] == 0.22
    assert len(vals_restored["blur_regions"]) == 1


def test_reset_session_preserves_defaults(qapp, tmp_path, monkeypatch):
    """Kiểm tra khi kết thúc phiên xuất video (_reset_session), thiết lập không bị xóa trắng."""
    monkeypatch.setattr("autodub.checkpoint_store.cache_dir", lambda: str(tmp_path))
    env_file = tmp_path / ".env"
    monkeypatch.setattr("autodub_gui.env_store.ENV_PATH", str(env_file))

    # Cấu hình người dùng có sẵn Logo và Watermark
    settings = Settings(
        logo_path="my_permanent_logo.png",
        logo_position="bottom_right",
        watermark_text="MY_CHANNEL",
        smart_flip=True,
    )
    page = NewProjectPage(settings_provider=lambda: settings)

    # Khởi tạo form ban đầu
    page._apply_defaults_from_settings()
    assert page.values()["logo_path"] == "my_permanent_logo.png"
    assert page.values()["watermark_text"] == "MY_CHANNEL"
    assert page.values()["smart_flip"] is True

    # Giả lập reset_session sau khi xuất video hoàn tất
    page._reset_session()

    # Kiểm tra thiết lập sau reset: LOGO và WATERMARK vẫn được giữ nguyên từ settings!
    vals = page.values()
    assert vals["logo_path"] == "my_permanent_logo.png"
    assert vals["logo_position"] == "bottom_right"
    assert vals["watermark_text"] == "MY_CHANNEL"
    assert vals["smart_flip"] is True
