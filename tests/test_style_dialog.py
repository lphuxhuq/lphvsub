from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication
from autodub_gui.style_dialog import _FrameCanvas, StyleDialog


def test_frame_canvas_multiple_blur_regions_and_presets(qtbot):
    app = QApplication.instance() or QApplication([])
    pm = QPixmap(1280, 720)
    pm.fill()

    canvas = _FrameCanvas(pm, style={"margin_v": 40}, allow_regions=True)
    qtbot.addWidget(canvas)
    canvas.resize(640, 360)

    # 1. Ban đầu không có vùng nào
    assert len(canvas.normalized_regions()) == 0

    # 2. Thêm preset Dải đáy (Bottom band)
    canvas.add_preset_region("bottom_band")
    regs = canvas.normalized_regions()
    assert len(regs) == 1
    assert regs[0]["y"] >= 0.80
    assert regs[0]["w"] >= 0.95

    # 3. Thêm preset Góc trên phải (Logo top right)
    canvas.add_preset_region("top_right_logo")
    regs = canvas.normalized_regions()
    assert len(regs) == 2
    assert regs[1]["x"] >= 0.70
    assert regs[1]["y"] <= 0.05

    # 4. Thêm preset Dải đỉnh (Top band)
    canvas.add_preset_region("top_band")
    regs = canvas.normalized_regions()
    assert len(regs) == 3

    # 5. Chọn vùng thứ 2 (chỉ số 1)
    canvas.select_region(1)
    assert canvas._selected_index == 1

    # 6. Xóa vùng thứ 2
    canvas.remove_region(1)
    regs = canvas.normalized_regions()
    assert len(regs) == 2

    # 7. Xóa tất cả
    canvas.clear_all()
    assert len(canvas.normalized_regions()) == 0


def test_style_dialog_tabs_and_logo_watermark(qtbot):
    app = QApplication.instance() or QApplication([])
    style = {"font": "Arial", "font_size": 24, "margin_v": 40, "position": "bottom"}
    logo_opts = {"logo_path": "test_logo.png", "logo_position": "top_right", "logo_scale": 0.15, "logo_opacity": 0.9}
    wm_opts = {"watermark_text": "@MyChannel", "watermark_motion": "bounce", "watermark_opacity": 0.3}

    dialog = StyleDialog(
        video_path=None,
        style=style,
        regions=[],
        logo_options=logo_opts,
        watermark_options=wm_opts,
    )
    qtbot.addWidget(dialog)

    # 1. Kiểm tra có đủ 3 Tabs
    assert dialog.tabs.count() == 3
    assert dialog.tabs.tabText(0) == "Kiểu chữ"
    assert dialog.tabs.tabText(1) == "Vùng che (Blur)"
    assert dialog.tabs.tabText(2) == "Logo & Watermark"

    # 2. Kiểm tra dữ liệu nạp vào Logo controls
    assert dialog.chk_logo_enabled.isChecked() is True
    assert dialog.txt_logo_path.text() == "test_logo.png"
    assert dialog.sp_logo_scale.value() == 15
    assert dialog.sp_logo_opacity.value() == 90

    # 3. Kiểm tra dữ liệu nạp vào Watermark controls
    assert dialog.chk_wm_enabled.isChecked() is True
    assert dialog.txt_wm_text.text() == "@MyChannel"
    assert dialog.sp_wm_opacity.value() == 30

    # 4. Kiểm tra phương thức getter
    out_logo = dialog.logo_options()
    assert out_logo["logo_path"] == "test_logo.png"
    assert out_logo["logo_position"] == "top_right"
    assert out_logo["logo_scale"] == 0.15

    out_wm = dialog.watermark_options()
    assert out_wm["watermark_text"] == "@MyChannel"
    assert out_wm["watermark_motion"] == "bounce"
    assert out_wm["watermark_opacity"] == 0.3

    # 5. Kiểm tra vẽ preview trên canvas không ném lỗi
    dialog.canvas.repaint()

    # Thử đổi sang ảnh thật và repaint
    import tempfile, os
    tmp_logo = os.path.join(tempfile.gettempdir(), "test_logo_sample.png")
    pm = QPixmap(100, 100)
    pm.fill()
    pm.save(tmp_logo)
    dialog.txt_logo_path.setText(tmp_logo)
    dialog.canvas.repaint()
    try:
        os.remove(tmp_logo)
    except OSError:
        pass


def test_voice_step_set_logo_and_watermark_signals(qtbot):
    from autodub_gui.pages.new_project_steps import VoiceStep

    step = VoiceStep()
    qtbot.addWidget(step)

    # Đảm bảo kết nối signal changed không bị TypeError khi nạp options
    changed_count = 0
    def on_changed():
        nonlocal changed_count
        changed_count += 1

    step.changed.connect(on_changed)

    step.set_logo_options({
        "logo_path": "my_logo.png",
        "logo_position": "top_left",
        "logo_scale": 0.20,
        "logo_opacity": 0.8,
        "logo_motion": "bounce",
    })
    vals = step.values()
    assert vals["logo_path"] == "my_logo.png"
    assert vals["logo_position"] == "top_left"
    assert vals["logo_motion"] == "bounce"

    step.set_watermark_options({
        "watermark_text": "@Antigravity",
        "watermark_motion": "bounce",
        "watermark_opacity": 0.45,
        "watermark_speed": 60,
    })
    vals = step.values()
    assert vals["watermark_text"] == "@Antigravity"
    assert vals["watermark_speed"] == 60
    assert changed_count > 0


def test_pipeline_stop_for_export_saves_logo_and_watermark_to_render_opts(tmp_path, monkeypatch):
    import os
    import json
    from autodub.config import Settings
    from autodub.pipeline import DubPipeline
    from autodub.editor import load_render_opts
    from autodub.text.translate_common import HOLD

    work_dir = str(tmp_path / "proj")
    os.makedirs(os.path.join(work_dir, "data"), exist_ok=True)
    merged_wav = str(tmp_path / "proj" / "data" / "merged.wav")
    with open(merged_wav, "wb") as f:
        f.write(b"RIFFmockwav")

    HOLD.set("test_hold_123", "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef")
    try:
        state = {
            "voice": "Phạm Tuyên",
            "subtitle_mode": "burn",
            "blur_regions": [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}],
            "subtitle_style": {"preset": "custom", "font_size": 24},
            "logo_path": "C:/path/my_logo.png",
            "logo_position": "top_left",
            "logo_scale": 0.18,
            "logo_opacity": 0.90,
            "logo_motion": "bounce",
            "watermark_text": "@TikTokChannel",
            "watermark_opacity": 0.35,
            "watermark_speed": 55,
            "watermark_motion": "bounce",
            "smart_flip": True,
            "micro_zoom": True,
            "color_filter": "cinematic_warm",
            "aspect_preset": "tiktok_9_16",
            "merged_audio_path": merged_wav,
            "segments": [{"id": 1, "end": 2.0}],
        }

        settings = Settings()
        pipeline = DubPipeline(settings)

        # Mock encrypt_file / add_locked_file / write_json_secure to avoid external dependencies
        from autodub import securestore
        monkeypatch.setattr(securestore, "encrypt_file", lambda f, k: None)
        monkeypatch.setattr(securestore, "add_locked_file", lambda w, h, f: None)
        monkeypatch.setattr(securestore, "write_json_secure", lambda d, p, k: None)

        pipeline._stop_for_export(state, work_dir)

        opts = load_render_opts(work_dir)
        assert opts["logo_path"] == "C:/path/my_logo.png"
        assert opts["logo_position"] == "top_left"
        assert opts["logo_scale"] == 0.18
        assert opts["logo_opacity"] == 0.90
        assert opts["logo_motion"] == "bounce"
        assert opts["watermark_text"] == "@TikTokChannel"
        assert opts["watermark_opacity"] == 0.35
        assert opts["watermark_speed"] == 55
        assert opts["watermark_motion"] == "bounce"
        assert opts["smart_flip"] is True
        assert opts["micro_zoom"] is True
        assert opts["color_filter"] == "cinematic_warm"
        assert opts["aspect_preset"] == "tiktok_9_16"
    finally:
        HOLD.clear()


