"""Unit test cho normalize/merge/join của selective OCR (TASK-3)."""
from autodub.media.ocr import (
    _has_cjk,
    join_frame_lines,
    merge_frame_texts,
    normalize_ocr_text,
    windows_from_suspects,
)


def test_normalize_keeps_cjk_and_cjk_punct():
    assert normalize_ocr_text("你为什么不告诉我？") == "你为什么不告诉我？"


def test_normalize_fullwidth_to_halfwidth():
    # ＡＢＣ１２３ full-width → half-width và được giữ (alnum)
    assert normalize_ocr_text("ＡＢＣ１２３") == "ABC123"


def test_normalize_strips_noise():
    # Khoảng trắng, xuống dòng, ký tự vẽ/rác — bỏ hết
    assert normalize_ocr_text("  你好\n\r 世界 ☆★@# ") == "你好世界"


def test_normalize_empty():
    assert normalize_ocr_text("") == ""
    assert normalize_ocr_text(None) == ""


def test_has_cjk():
    assert _has_cjk("你")
    assert not _has_cjk("ABC")
    assert not _has_cjk("")


def test_join_frame_lines_multi_line():
    # Multi-line subtitle: 2 dòng ghép 1 dòng (zh không cần space)
    lines = [{"text": "你到底", "score": 0.98, "top_y": 10},
             {"text": "在干什么", "score": 0.94, "top_y": 40}]
    text, score = join_frame_lines(lines)
    assert text == "你到底在干什么"
    assert abs(score - 0.96) < 0.01


def test_join_frame_lines_filters_low_score():
    lines = [{"text": "好", "score": 0.1},
             {"text": "你到底在干什么", "score": 0.9}]
    text, _ = join_frame_lines(lines)
    assert text == "你到底在干什么"


def test_join_frame_lines_empty():
    assert join_frame_lines([]) == ("", 0.0)


def test_merge_consecutive_duplicate_frames():
    # 5 frame @3fps: 4 frame giống nhau, 1 frame khác → 2 segment
    frames = [{"t": 0.0, "text": "你为什么不告诉我", "score": 0.9},
              {"t": 1 / 3, "text": "你为什么不告诉我", "score": 0.95},
              {"t": 2 / 3, "text": "你为什么不告诉我", "score": 0.92},
              {"t": 1.0, "text": "你为什么不告诉我", "score": 0.88},
              {"t": 4 / 3, "text": "好的知道了", "score": 0.97}]
    segs = merge_frame_texts(frames, fps=3, total_frames=5)
    assert len(segs) == 2
    assert segs[0]["text"] == "你为什么不告诉我"
    assert segs[0]["start_time"] == 0.0
    assert abs(segs[0]["end_time"] - (1.0 + 1 / 3)) < 0.01
    assert 0 < segs[0]["stability"] <= 1.0
    assert abs(segs[0]["stability"] - 0.8) < 0.01  # 4/5 frame
    assert segs[1]["text"] == "好的知道了"


def test_merge_tolerates_dropout_frame():
    # Phụ đề "mất" đúng 1 frame giữa hai frame giống nhau → coi là OCR
    # dropout, vẫn MỘT segment (chống nhấp nháy phụ đề lặp).
    frames = [{"t": 0.0, "text": "啊", "score": 0.9},
              {"t": 0.5, "text": "啊", "score": 0.9},
              {"t": 1.0, "text": "", "score": 0.0},
              {"t": 1.5, "text": "啊", "score": 0.9}]
    segs = merge_frame_texts(frames, fps=2, total_frames=4)
    assert len(segs) == 1
    assert segs[0]["start_time"] == 0.0
    assert abs(segs[0]["end_time"] - 2.0) < 0.01


def test_merge_empty_input():
    assert merge_frame_texts([], fps=3, total_frames=0) == []


def test_merge_tolerates_one_bad_frame_in_group():
    # 1 frame OCR lỗi nhẹ (thiếu 1 chữ) giữa các frame giống nhau → vẫn cùng
    # nhóm vì similarity ≥ 0.9
    frames = [{"t": 0.0, "text": "你为什么不告诉我", "score": 0.9},
              {"t": 1 / 3, "text": "你为什么不告诉", "score": 0.7},
              {"t": 2 / 3, "text": "你为什么不告诉我", "score": 0.95}]
    segs = merge_frame_texts(frames, fps=3, total_frames=3)
    assert len(segs) == 1
    # Text đại diện là frame score cao nhất (đầy đủ chữ)
    assert segs[0]["text"] == "你为什么不告诉我"


def test_windows_merge_overlap_and_clamp():
    suspects = [{"start": 2.0, "end": 4.0},   # window [1,5]
                {"start": 4.5, "end": 6.0},   # window [3.5,7] — giao [1,5]
                {"start": 10.0, "end": 11.0}]  # window [9,12]
    windows = windows_from_suspects(suspects, duration_s=11.5)
    assert windows == [(1.0, 7.0), (9.0, 11.5)]  # clamp cuối video


def test_windows_no_suspects():
    assert windows_from_suspects([], 100.0) == []
