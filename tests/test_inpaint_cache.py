import os
import tempfile
import numpy as np
import pytest

from autodub.media.inpaint.base import (
    convert_normalized_regions_to_mask,
    get_bounding_box_for_regions,
    BaseInpaintEngine,
)
from autodub.media.inpaint.cache import (
    compute_inpaint_hash,
    get_inpaint_cache_dir,
    get_inpaint_cache_target,
    get_cached_clean_video,
)
from autodub.media.inpaint import inpaint_video_with_cache


def test_convert_normalized_regions_to_mask():
    regions = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15}]
    mask = convert_normalized_regions_to_mask(regions, width=100, height=100)

    assert mask.shape == (100, 100)
    assert mask.dtype == np.uint8
    # Vùng ngoài phải bằng 0
    assert mask[10, 50] == 0
    # Vùng trong ROI phải bằng 255
    assert mask[85, 50] == 255


def test_get_bounding_box_for_regions():
    regions = [
        {"x": 0.2, "y": 0.8, "w": 0.3, "h": 0.1},
        {"x": 0.4, "y": 0.85, "w": 0.4, "h": 0.1},
    ]
    x, y, w, h = get_bounding_box_for_regions(regions, width=1000, height=1000, padding=10)

    assert x <= 200
    assert y <= 800
    assert (x + w) >= 800
    assert (y + h) >= 950
    assert w % 2 == 0
    assert h % 2 == 0


def test_compute_inpaint_hash_deterministic(tmp_path):
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"dummy video content" * 100)

    regions1 = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}]
    regions2 = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.1}]  # same
    regions3 = [{"x": 0.1, "y": 0.7, "w": 0.8, "h": 0.1}]  # different y

    h1 = compute_inpaint_hash(str(video_file), regions1, "lama_onnx")
    h2 = compute_inpaint_hash(str(video_file), regions2, "lama_onnx")
    h3 = compute_inpaint_hash(str(video_file), regions3, "lama_onnx")
    h4 = compute_inpaint_hash(str(video_file), regions1, "vsr_cli")

    assert h1 == h2
    assert h1 != h3
    assert h1 != h4


def test_get_cached_clean_video(tmp_path):
    cache_dir = str(tmp_path / "cache")
    key = "test_key_123"
    target = get_inpaint_cache_target(key, cache_dir=cache_dir)

    # Chưa tạo file -> None
    assert get_cached_clean_video(key, cache_dir=cache_dir) is None

    # Tạo file rỗng (0 byte) -> None
    with open(target, "wb") as f:
        f.write(b"")
    assert get_cached_clean_video(key, cache_dir=cache_dir) is None

    # Tạo file dung lượng hợp lệ (> 1KB) -> trả về target
    with open(target, "wb") as f:
        f.write(b"x" * 2048)
    assert get_cached_clean_video(key, cache_dir=cache_dir) == target


def test_inpaint_video_with_cache_empty_regions(tmp_path):
    dummy_video = tmp_path / "orig.mp4"
    dummy_video.write_bytes(b"content")

    # Không có regions -> trả về video gốc
    res = inpaint_video_with_cache(str(dummy_video), regions=[])
    assert res == str(dummy_video)


def test_inpaint_video_with_cache_hit(tmp_path, monkeypatch):
    video_file = tmp_path / "input.mp4"
    video_file.write_bytes(b"dummy video data" * 200)

    regions = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15}]
    cache_dir = str(tmp_path / "cache")
    os.makedirs(cache_dir, exist_ok=True)

    cache_key = compute_inpaint_hash(str(video_file), regions, "lama_onnx")
    cached_file = get_inpaint_cache_target(cache_key, cache_dir=cache_dir)
    with open(cached_file, "wb") as f:
        f.write(b"precomputed clean video data" * 100)

    # Khi hit cache, không được gọi get_inpaint_engine
    def mock_get_engine(*args, **kwargs):
        raise AssertionError("Should not instantiate engine on cache hit")

    monkeypatch.setattr("autodub.media.inpaint.get_inpaint_engine", mock_get_engine)

    res = inpaint_video_with_cache(
        str(video_file),
        regions=regions,
        cache_dir=cache_dir,
        engine_type="lama_onnx",
    )
    assert res == cached_file
