import numpy as np
import pytest

from autodub.media.hardsub_detector import (
    detect_text_candidates_in_frame,
    spatial_merge_candidates,
    track_temporal_regions,
    detect_hardsub_regions,
    FrameSample,
)


def _generate_synthetic_frame(w: int = 640, h: int = 360, has_sub: bool = True, sub_pos: str = "bottom") -> np.ndarray:
    """Tạo frame ảnh xám giả lập có phụ đề ở đáy hoặc đỉnh."""
    img = np.full((h, w), 40, dtype=np.uint8) # Nền tối
    if has_sub:
        if sub_pos == "bottom":
            y_start, y_end = int(h * 0.82), int(h * 0.91)
        elif sub_pos == "top":
            y_start, y_end = int(h * 0.08), int(h * 0.17)
        else:
            y_start, y_end = int(h * 0.45), int(h * 0.54)

        x_start, x_end = int(w * 0.20), int(w * 0.80)
        # Các nét chữ tương phản cao xen kẽ
        for x in range(x_start, x_end, 5):
            img[y_start:y_end, x:x+3] = 245
    return img


def test_detect_text_candidates_bottom_subtitles():
    frame = _generate_synthetic_frame(640, 360, has_sub=True, sub_pos="bottom")
    cands = detect_text_candidates_in_frame(frame)
    assert len(cands) > 0
    c = cands[0]
    assert c.y / 360.0 > 0.60
    assert c.confidence >= 0.45


def test_detect_text_candidates_top_subtitles():
    frame = _generate_synthetic_frame(640, 360, has_sub=True, sub_pos="top")
    cands = detect_text_candidates_in_frame(frame)
    assert len(cands) > 0
    c = cands[0]
    assert c.y / 360.0 < 0.30


def test_detect_text_candidates_clean_frame():
    frame = np.full((360, 640), 100, dtype=np.uint8)
    cands = detect_text_candidates_in_frame(frame)
    assert len(cands) == 0


def test_spatial_merge_candidates():
    frame = _generate_synthetic_frame(640, 360, has_sub=True, sub_pos="bottom")
    cands = detect_text_candidates_in_frame(frame)
    merged = spatial_merge_candidates(cands, 640, 360)
    assert len(merged) >= 1
    m = merged[0]
    assert m["y"] > 0.60
    assert m["w"] > 0.30
