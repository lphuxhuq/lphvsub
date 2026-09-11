"""Regression tests for Phase 3: Centralized Video Odd Dimensions Normalization.

Guarantees:
- even width
- even height
- aspect ratio preserved
- no unexpected crop
- NVENC & CPU encoder compatible (YUV420p)
- Handles portrait, landscape, and mixed odd dimensions.
"""

import os
import shutil
import subprocess

import pytest

from autodub.media.dimension import (
    build_dimension_filter,
    is_even_dimension,
    make_even,
    normalize_dimensions,
)
from autodub.media.subtitle import build_filter_complex
from autodub.media.video import probe_dimensions


def test_make_even_math():
    """Verify make_even rounds odd numbers up to the next even integer."""
    assert make_even(1080) == 1080
    assert make_even(1079) == 1080
    assert make_even(720) == 720
    assert make_even(721) == 722
    assert make_even(1) == 2
    assert make_even(0) == 0


def test_normalize_dimensions_portrait_and_landscape():
    """Verify normalize_dimensions handles portrait, landscape, and square video."""
    # Landscape
    assert normalize_dimensions(1919, 1079) == (1920, 1080)
    assert normalize_dimensions(1920, 1079) == (1920, 1080)
    assert normalize_dimensions(1919, 1080) == (1920, 1080)
    assert normalize_dimensions(1920, 1080) == (1920, 1080)

    # Portrait
    assert normalize_dimensions(1079, 1920) == (1080, 1920)
    assert normalize_dimensions(1080, 1921) == (1080, 1922)
    assert normalize_dimensions(721, 1281) == (722, 1282)

    # Square
    assert normalize_dimensions(721, 721) == (722, 722)
    assert normalize_dimensions(720, 720) == (720, 720)


def test_is_even_dimension():
    assert is_even_dimension(1920, 1080) is True
    assert is_even_dimension(1080, 1920) is True
    assert is_even_dimension(1079, 1920) is False
    assert is_even_dimension(1920, 1079) is False
    assert is_even_dimension(721, 1281) is False


def test_build_filter_complex_enforces_even_dimensions_on_output():
    """Filtergraph must end with even dimension padding before [vout]."""
    flt = build_filter_complex(
        blur_regions=[{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}],
        video_w=1079,
        video_h=1920,
    )
    assert flt is not None
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2[vout]" in flt


def test_micro_zoom_uses_even_crop():
    """Micro zoom crop must truncate to even dimensions to avoid odd crop output."""
    flt = build_filter_complex(
        blur_regions=None,
        video_w=1920,
        video_h=1080,
        micro_zoom=True,
    )
    assert flt is not None
    assert "crop=trunc(iw/1.03/2)*2:trunc(ih/1.03/2)*2" in flt
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2[vout]" in flt


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required for real encoding test")
def test_real_ffmpeg_encodes_odd_dimensions_landscape(tmp_path):
    """Real FFmpeg test: landscape 321x241 -> encoded without error -> 322x242 output."""
    odd_video = str(tmp_path / "odd_landscape.mp4")
    # Tạo video mẫu 321x241 (odd width và odd height)
    cmd_gen = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=321x241:rate=1:duration=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",  # 444p hỗ trợ kích thước lẻ
        odd_video,
    ]
    res = subprocess.run(cmd_gen, capture_output=True, text=True)
    assert res.returncode == 0, f"Failed to create fixture: {res.stderr}"

    # Dựng filter complex có chuẩn hoá kích thước
    dim_flt = build_dimension_filter()
    out_video = str(tmp_path / "encoded_landscape.mp4")
    cmd_encode = [
        "ffmpeg",
        "-y",
        "-i",
        odd_video,
        "-vf",
        dim_flt,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        out_video,
    ]
    res_enc = subprocess.run(cmd_encode, capture_output=True, text=True)
    assert res_enc.returncode == 0, f"FFmpeg encode failed: {res_enc.stderr}"
    assert os.path.exists(out_video)

    # Đo kích thước video đầu ra bằng probe_dimensions
    w, h = probe_dimensions(out_video)
    assert w == 322
    assert h == 242
    assert is_even_dimension(w, h) is True


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required for real encoding test")
def test_real_ffmpeg_encodes_odd_dimensions_portrait(tmp_path):
    """Real FFmpeg test: portrait 241x321 -> encoded without error -> 242x322 output."""
    odd_video = str(tmp_path / "odd_portrait.mp4")
    # Tạo video mẫu 241x321 (portrait odd)
    cmd_gen = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "testsrc=size=241x321:rate=1:duration=1",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv444p",
        odd_video,
    ]
    res = subprocess.run(cmd_gen, capture_output=True, text=True)
    assert res.returncode == 0, f"Failed to create fixture: {res.stderr}"

    # Dựng filter complex có chuẩn hoá kích thước
    dim_flt = build_dimension_filter()
    out_video = str(tmp_path / "encoded_portrait.mp4")
    cmd_encode = [
        "ffmpeg",
        "-y",
        "-i",
        odd_video,
        "-vf",
        dim_flt,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        out_video,
    ]
    res_enc = subprocess.run(cmd_encode, capture_output=True, text=True)
    assert res_enc.returncode == 0, f"FFmpeg encode failed: {res_enc.stderr}"
    assert os.path.exists(out_video)

    w, h = probe_dimensions(out_video)
    assert w == 242
    assert h == 322
    assert is_even_dimension(w, h) is True
