import numpy as np
import pytest

from autodub.media.hardsub_detector import (
    detect_text_regions_in_image,
    merge_similar_regions,
    detect_hardsub_regions,
)


def _generate_synthetic_frame_with_subtitles(w: int = 640, h: int = 360, has_sub: bool = True) -> np.ndarray:
    """Tạo frame ảnh xám giả lập: nửa dưới có dải văn bản phụ đề độ tương phản cao."""
    img = np.full((h, w), 50, dtype=np.uint8) # Nền tối
    if has_sub:
        # Giả lập dòng phụ đề ở vị trí y = 300..330 (đáy khung hình ~83% - 91%)
        y_start, y_end = int(h * 0.83), int(h * 0.92)
        x_start, x_end = int(w * 0.20), int(w * 0.80)
        # Các nét chữ tương phản cao xen kẽ
        for x in range(x_start, x_end, 6):
            img[y_start:y_end, x:x+3] = 240
    return img


def test_detect_text_regions_in_image_with_subtitles():
    frame = _generate_synthetic_frame_with_subtitles(640, 360, has_sub=True)
    regions = detect_text_regions_in_image(frame)
    assert len(regions) > 0
    sub_region = regions[0]
    # Kiểm tra toạ độ chuẩn hoá nằm ở dải đáy khung hình
    assert sub_region["y"] > 0.65
    assert sub_region["w"] > 0.4
    assert sub_region["h"] > 0.04


def test_detect_text_regions_in_image_clean():
    # Frame trơn không có chữ
    frame = np.full((360, 640), 100, dtype=np.uint8)
    regions = detect_text_regions_in_image(frame)
    assert len(regions) == 0


def test_merge_similar_regions():
    regions_list = [
        [{"x": 0.15, "y": 0.82, "w": 0.70, "h": 0.10}],
        [{"x": 0.16, "y": 0.83, "w": 0.68, "h": 0.09}],
        [{"x": 0.14, "y": 0.81, "w": 0.72, "h": 0.11}],
    ]
    merged = merge_similar_regions(regions_list, min_occurrence=0.5)
    assert len(merged) == 1
    m = merged[0]
    assert 0.10 <= m["x"] <= 0.20
    assert 0.75 <= m["y"] <= 0.85
    assert 0.60 <= m["w"] <= 0.80
    assert 0.05 <= m["h"] <= 0.15


def test_detect_hardsub_regions_mock(monkeypatch):
    def fake_extract_frames(video_path, max_frames=8):
        # Trả về 4 frame có sub, 2 frame không sub
        return [
            (0.0, _generate_synthetic_frame_with_subtitles(640, 360, True)),
            (1.0, _generate_synthetic_frame_with_subtitles(640, 360, True)),
            (2.0, _generate_synthetic_frame_with_subtitles(640, 360, True)),
            (3.0, _generate_synthetic_frame_with_subtitles(640, 360, False)),
        ]
    
    from autodub.media import hardsub_detector
    monkeypatch.setattr(hardsub_detector, "extract_video_sample_frames", fake_extract_frames)

    res = detect_hardsub_regions("dummy.mp4")
    assert len(res) >= 1
    assert res[0]["y"] > 0.65
    assert res[0]["h"] > 0.04
