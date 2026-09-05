"""Kiểm thử cho module autodub/checkpoint_store.py."""
import os
import pytest
from autodub import checkpoint_store


@pytest.fixture
def mock_cache_dir(tmp_path, monkeypatch):
    cache = tmp_path / "voxdub_cache"
    cache.mkdir()
    monkeypatch.setattr(checkpoint_store, "cache_dir", lambda: str(cache))
    return cache


def test_checkpoint_store_crud(mock_cache_dir):
    # Chưa có checkpoint nào
    assert checkpoint_store.load_checkpoints() == {}
    assert checkpoint_store.get_checkpoint_names() == []

    # Lưu checkpoint 1
    data1 = {
        "logo": {"logo_path": "D:/logo1.png", "logo_position": "top_right"},
        "watermark": {"watermark_text": "@Review1"},
    }
    checkpoint_store.save_checkpoint("Kênh 1", data1)

    # Đọc lại
    names = checkpoint_store.get_checkpoint_names()
    assert "Kênh 1" in names
    ckpt = checkpoint_store.get_checkpoint("Kênh 1")
    assert ckpt is not None
    assert ckpt["logo"]["logo_path"] == "D:/logo1.png"
    assert ckpt["watermark"]["watermark_text"] == "@Review1"
    assert "updated_at" in ckpt

    # Lưu checkpoint 2
    data2 = {
        "logo": {"logo_path": "D:/logo2.png", "logo_position": "bottom_left"},
        "watermark": {"watermark_text": "@Review2"},
    }
    checkpoint_store.save_checkpoint("Kênh 2", data2)
    assert len(checkpoint_store.get_checkpoint_names()) == 2

    # Active checkpoint
    checkpoint_store.set_active_checkpoint_name("Kênh 2")
    assert checkpoint_store.get_active_checkpoint_name() == "Kênh 2"

    # Xóa checkpoint 1
    deleted = checkpoint_store.delete_checkpoint("Kênh 1")
    assert deleted is True
    assert "Kênh 1" not in checkpoint_store.get_checkpoint_names()
    assert len(checkpoint_store.get_checkpoint_names()) == 1


def test_bundle_checkpoint_data():
    values = {
        "logo_path": "D:/assets/logo.png",
        "logo_position": "top_left",
        "logo_scale": 0.15,
        "watermark_text": "@MyChannel",
        "watermark_motion": "bounce",
        "smart_flip": True,
        "micro_zoom": False,
        "color_filter": "cinematic_warm",
        "subtitle_mode": "burn",
        "subtitle_preset": "custom",
    }
    style = {"font": "Roboto", "font_size": 24, "position": "bottom"}
    blur_regions = [{"x": 10, "y": 20, "w": 100, "h": 50}]
    mask_opts = {"mask_method": "ai_inpaint", "inpaint_engine": "lama_onnx"}
    banner_opts = {"frame_banner_enabled": True, "frame_header_text": "TẬP 1"}
    reframe_opts = {"aspect_preset": "16:9", "reframe_mode": "blur"}

    bundle = checkpoint_store.bundle_checkpoint_data(
        values=values,
        subtitle_style=style,
        blur_regions=blur_regions,
        mask_opts=mask_opts,
        banner_opts=banner_opts,
        reframe_opts=reframe_opts,
    )

    assert bundle["logo"]["logo_path"] == "D:/assets/logo.png"
    assert bundle["logo"]["logo_position"] == "top_left"
    assert bundle["watermark"]["watermark_text"] == "@MyChannel"
    assert bundle["anti_id"]["smart_flip"] is True
    assert bundle["anti_id"]["color_filter"] == "cinematic_warm"
    assert bundle["mask"]["mask_method"] == "ai_inpaint"
    assert len(bundle["mask"]["blur_regions"]) == 1
    assert bundle["banner"]["frame_banner_enabled"] is True
    assert bundle["banner"]["frame_header_text"] == "TẬP 1"
    assert bundle["reframe"]["aspect_preset"] == "16:9"
    assert bundle["subtitle"]["subtitle_style"]["font"] == "Roboto"


def test_apply_checkpoint_to_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OLD_KEY=val\n", encoding="utf-8")
    from autodub_gui import env_store
    monkeypatch.setattr(env_store, "ENV_PATH", str(env_file))

    ckpt = {
        "logo": {"logo_path": "D:/test_logo.png", "logo_position": "bottom_right"},
        "watermark": {"watermark_text": "@EnvTest"},
        "anti_id": {"smart_flip": True},
        "mask": {"mask_method": "blur", "blur_regions": [{"x": 0, "y": 0}]},
        "subtitle": {"subtitle_mode": "burn", "subtitle_style": {"font": "Inter", "font_size": 28}},
    }

    checkpoint_store.apply_checkpoint_to_env(ckpt)
    content = env_file.read_text(encoding="utf-8")
    assert "LOGO_PATH=D:/test_logo.png" in content
    assert "LOGO_POSITION=bottom_right" in content
    assert "WATERMARK_TEXT=@EnvTest" in content
    assert "SMART_FLIP=true" in content
    assert "SUBTITLE_FONT=Inter" in content
    assert "SUBTITLE_FONT_SIZE=28" in content
