"""Unit test cho detect_suspect_segments — 4 heuristic của TASK-2."""
from autodub.text.fusion import (
    REASON_EMPTY_CHUNK,
    REASON_GAP_ANOMALY,
    REASON_OCR_NO_ASR,
    REASON_TEXT_TOO_SHORT,
    detect_suspect_segments,
)


def _seg(i, start, end, text):
    return {"id": i, "text": text, "start": start, "end": end,
            "duration": round(end - start, 3)}


def _normal_transcript():
    """6 câu đều đặn ~4 ký tự CJK / giây — làm nền cho median."""
    return [_seg(i, i * 2.0, i * 2.0 + 1.0, "你好世界你好") for i in range(6)]


def test_all_normal_no_suspect():
    res = detect_suspect_segments(_normal_transcript())
    assert res.suspect == []
    assert len(res.normal) == 6
    assert res.stats["suspect"] == 0


def test_text_too_short_flagged():
    segs = _normal_transcript()
    # Câu 3 dài 6 giây nhưng chỉ 1 ký tự → rate thấp hơn 0.4× median
    segs[3] = _seg(4, 6.0, 12.0, "好")
    res = detect_suspect_segments(segs)
    reasons = {s["id"]: s["suspect_reasons"] for s in res.suspect}
    assert REASON_TEXT_TOO_SHORT in reasons[4]


def test_text_too_dense_flagged():
    segs = _normal_transcript()
    # 20 ký tự trong 0.5 giây → rate cao hơn 3× median
    segs[2] = _seg(3, 4.0, 4.5, "一二三四五六七八九十一二三四五六七八九十")
    res = detect_suspect_segments(segs)
    ids = {s["id"] for s in res.suspect}
    assert 3 in ids


def test_char_rate_heuristic_off_below_min_samples():
    # 4 câu < CHAR_RATE_MIN_SAMPLES(5) → không flag dù rate lệch
    segs = [_seg(i, i * 2.0, i * 2.0 + 1.0, "你") for i in range(4)]
    res = detect_suspect_segments(segs)
    assert res.suspect == []
    assert res.stats["median_char_rate"] is None


def test_gap_anomaly_flags_both_neighbours():
    segs = _normal_transcript()
    # Kéo câu cuối (id 5) ra xa tạo gap 7s (median gap = 1s → ngưỡng 3s)
    segs[5] = _seg(5, 16.0, 17.0, "你好世界你好")
    res = detect_suspect_segments(segs)
    reasons = {s["id"]: set(s["suspect_reasons"]) for s in res.suspect}
    assert REASON_GAP_ANOMALY in reasons[4]
    assert REASON_GAP_ANOMALY in reasons[5]


def test_empty_chunk_in_gap_flags_nearest():
    segs = _normal_transcript()
    # Chunk rỗng nằm trọn trong khoảng lặng 1s giữa câu 2 và 3
    res = detect_suspect_segments(
        segs, empty_chunks=[{"start": 3.0, "end": 3.9}])
    ids = {s["id"] for s in res.suspect}
    assert ids  # câu gần nhất (2 hoặc 3) bị flag


def test_empty_chunk_covered_by_segment_not_flagged():
    segs = _normal_transcript()
    # Chunk rỗng nằm YÊN TRONG câu 1 (bị phủ 100%) → không flag empty
    res = detect_suspect_segments(
        segs, empty_chunks=[{"start": 0.2, "end": 0.8}])
    for s in res.suspect:
        assert REASON_EMPTY_CHUNK not in s["suspect_reasons"]


def test_ocr_unmatched_flags_nearest_and_counts():
    segs = _normal_transcript()
    # OCR nằm trong khoảng lặng 1s giữa câu 1 [0,1] và câu 2 [2,3]
    ocr = [{"text": "你到底在干什么", "start_time": 1.1, "end_time": 1.8,
            "confidence": 0.95}]
    res = detect_suspect_segments(segs, ocr_segments=ocr)
    assert res.stats["ocr_unmatched"] == 1
    flagged = [s for s in res.suspect
               if REASON_OCR_NO_ASR in s["suspect_reasons"]]
    assert flagged  # câu kề bên (id 1 hoặc 2) bị flag


def test_ocr_matched_no_flag():
    segs = _normal_transcript()
    ocr = [{"text": "你好世界你好", "start_time": 0.0, "end_time": 1.0,
            "confidence": 0.9}]
    res = detect_suspect_segments(segs, ocr_segments=ocr)
    assert res.stats["ocr_unmatched"] == 0


def test_input_not_mutated():
    segs = _normal_transcript()
    segs[3] = _seg(4, 6.0, 12.0, "好")
    before = [dict(s) for s in segs]
    detect_suspect_segments(segs, empty_chunks=[{"start": 3.0, "end": 3.9}])
    assert segs == before  # không key suspect_reasons nào dính vào input


def test_empty_input():
    res = detect_suspect_segments([], [])
    assert res.normal == [] and res.suspect == []
    assert res.stats["total"] == 0


def test_partition_preserves_all_segments():
    segs = _normal_transcript()
    segs[3] = _seg(4, 6.0, 12.0, "好")
    res = detect_suspect_segments(
        segs, empty_chunks=[{"start": 3.0, "end": 3.9}])
    assert len(res.normal) + len(res.suspect) == len(segs)
    ids = sorted([s["id"] for s in res.normal + res.suspect])
    assert ids == sorted(s["id"] for s in segs)
