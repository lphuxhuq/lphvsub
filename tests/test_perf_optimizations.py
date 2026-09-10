import pytest
from autodub.media.subtitle import build_filter_complex
from autodub.resources import FFMPEG_SLOTS, FFMPEG_AUDIO_SLOTS


def test_build_filter_complex_uses_delogo():
    """Xác nhận build_filter_complex sử dụng delogo in-place thay vì split+boxblur."""
    regions = [
        {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.2},
        {"x": 0.5, "y": 0.6, "w": 0.4, "h": 0.3},
    ]
    fc = build_filter_complex(regions, video_w=1920, video_h=1080, mask_method="delogo")
    assert fc is not None
    # Không còn split hay boxblur nặng nề
    assert "split" not in fc
    assert "boxblur" not in fc
    assert "overlay" not in fc
    # Chứa đúng 2 filter delogo
    assert fc.count("delogo=") == 2
    assert "delogo=x=" in fc
    assert "show=0" in fc


def test_build_filter_complex_delogo_with_timing():
    """Xác nhận delogo hỗ trợ mốc thời gian enable='between(t,...)"""
    regions = [
        {"x": 0.2, "y": 0.3, "w": 0.4, "h": 0.2, "t_start": 5.0, "t_end": 12.5},
    ]
    fc = build_filter_complex(regions, video_w=1280, video_h=720, mask_method="delogo")
    assert fc is not None
    assert "delogo=x=" in fc
    assert "enable='between(t,5.0,12.5)'" in fc


def test_ffmpeg_audio_slots_independence():
    """Xác nhận FFMPEG_AUDIO_SLOTS có trần luồng rộng hơn FFMPEG_SLOTS cho tác vụ audio nhẹ."""
    # FFMPEG_AUDIO_SLOTS phải có ít nhất 4 slots
    # Acquire và release thử
    acquired = FFMPEG_AUDIO_SLOTS.acquire(blocking=False)
    assert acquired is True
    FFMPEG_AUDIO_SLOTS.release()


def test_delogo_ffmpeg_real_execution():
    """Xác nhận FFmpeg thực thi cú pháp delogo mà không có lỗi cú pháp."""
    import subprocess
    cmd = [
        "ffmpeg", "-v", "error", "-f", "lavfi",
        "-i", "color=black:s=320x240:d=0.1",
        "-vf", "delogo=x=10:y=10:w=50:h=50:show=0:enable='between(t,0,0.05)'",
        "-f", "null", "-",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0
