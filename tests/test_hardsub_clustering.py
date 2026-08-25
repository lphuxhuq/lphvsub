import numpy as np
import pytest

from autodub.media.hardsub_detector import (
    HardsubRegion,
    FrameSample,
    track_temporal_regions,
    merge_blur_regions_with_manual,
    detect_text_candidates_in_frame,
)
from tests.test_hardsub_detector import _generate_synthetic_frame


def test_track_temporal_regions_stable_bottom_sub():
    # Tạo chuỗi 5 frame có phụ đề ở đáy
    samples = [
        FrameSample(timestamp=0.0, frame_index=0, image=_generate_synthetic_frame(640, 360, True, "bottom")),
        FrameSample(timestamp=2.0, frame_index=1, image=_generate_synthetic_frame(640, 360, True, "bottom")),
        FrameSample(timestamp=4.0, frame_index=2, image=_generate_synthetic_frame(640, 360, True, "bottom")),
        FrameSample(timestamp=6.0, frame_index=3, image=_generate_synthetic_frame(640, 360, True, "bottom")),
        FrameSample(timestamp=8.0, frame_index=4, image=_generate_synthetic_frame(640, 360, False)),
    ]

    regions = track_temporal_regions(samples, min_occurrence=0.25)
    assert len(regions) >= 1
    r = regions[0]
    assert r.y > 0.60
    assert r.width > 0.30
    assert r.confidence > 0.50
    # Đã có padding an toàn
    assert 0.0 <= r.x <= 1.0
    assert 0.0 <= r.y <= 1.0


def test_corner_watermark_rejection():
    # Giả lập frame trơn có một logo nhỏ xíu ở góc trên cùng bên trái
    frame = np.full((360, 640), 40, dtype=np.uint8)
    frame[10:30, 10:40] = 250 # Logo nhỏ góc (x=10..40, y=10..30)
    cands = detect_text_candidates_in_frame(frame)
    # Phải bị loại trừ khỏi candidate phụ đề
    assert len(cands) == 0


def test_merge_blur_regions_with_manual_deduplication():
    manual = [{"x": 0.10, "y": 0.80, "w": 0.80, "h": 0.12}]
    # Auto region trùng vị trí
    auto_same = [{"x": 0.11, "y": 0.81, "w": 0.78, "h": 0.11}]
    # Auto region ở đỉnh khác vị trí
    auto_top = [{"x": 0.15, "y": 0.10, "w": 0.70, "h": 0.10}]

    merged = merge_blur_regions_with_manual(manual, auto_same + auto_top)
    assert len(merged) == 2 # 1 manual (giữ nguyên) + 1 auto_top (mới)
    assert merged[0] == manual[0]
    assert merged[1] == auto_top[0]
