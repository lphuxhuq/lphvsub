"""Tests cho voice-sync scheduler (autodub.media.timing).

Nguyên tắc mới (thay shift→compress→overlap cũ):
- onset giữ mốc speech — drift mỗi câu ≤ timing_max_start_drift_s (0.15s),
  KHÔNG cộng dồn;
- slot = speech_duration/duration; câu không có info slot → natural;
- per-segment tempo trần voice_fit_max_speed, không stretch;
- silence trước câu kế được mượn, không ăn vào speech kế.
"""
import math
import os
import struct
import wave

import pytest

from autodub.config import Settings
from autodub.media.timing import apply_soft_timing, plan_voice_placements


def _segs(*starts, dur=None):
    return [{"id": i + 1, "start": float(s),
             **({"end": float(s) + dur, "duration": float(dur)}
                if dur else {})}
            for i, s in enumerate(starts)]


def test_no_intervention_when_everything_fits():
    # Không info slot → natural, không tempo, không shift.
    p, r = plan_voice_placements(_segs(0, 5, 10), [4.0, 4.0, 4.0])
    assert [x["start"] for x in p] == [0.0, 5.0, 10.0]
    assert all(x["atempo"] == 1.0 for x in p)
    assert r.segments_shifted == 0
    assert r.segments_overlapped == 0


def test_onset_kept_when_tts_longer():
    """Case 1/2: TTS 2.2s vào slot 2.0s, câu kế sát ngay (2.12s) → tempo 1.1,
    onset KHÔNG trượt."""
    segs = [{"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0},
            {"id": 2, "start": 2.12, "end": 4.12, "duration": 2.0}]
    p, r = plan_voice_placements(segs, [2.2, 2.0])
    assert p[0]["start"] == 0.0            # dub_start ≈ speech_start
    assert abs(p[0]["atempo"] - 1.1) < 1e-3  # fit nhẹ trong trần 1.15
    assert p[0]["adjustment"] == "tempo"
    assert p[1]["start"] == 2.12           # câu sau KHÔNG bị đẩy
    assert r.segments_overlapped == 0


def test_silence_to_next_speech_is_borrowed_first():
    """TTS 2.2s, slot 2.0s nhưng câu kế ở 4.0s (lặng 2s) → mượn silence,
    KHÔNG tempo."""
    segs = [{"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0},
            {"id": 2, "start": 4.0, "end": 6.0, "duration": 2.0}]
    p, r = plan_voice_placements(segs, [2.2, 2.0])
    assert p[0]["atempo"] == 1.0
    assert p[0]["adjustment"] == "silence"
    assert p[1]["start"] == 4.0


def test_case3_huge_overflow_uses_silence_then_caps_tempo():
    """Case 3: TTS 3.0s vào slot 2.0s, câu kế ở 5.0s (silence 3s)."""
    segs = [{"id": 1, "start": 0.0, "end": 2.0, "duration": 2.0},
            {"id": 2, "start": 5.0, "end": 7.0, "duration": 2.0}]
    p, r = plan_voice_placements(segs, [3.0, 2.0])
    # available = 5.0 - gap 0.12 = 4.88 → 3.0 vừa → KHÔNG ép 1.5x
    assert p[0]["atempo"] == 1.0
    assert p[0]["adjustment"] == "silence"
    assert p[1]["start"] == 5.0


def test_case6_consecutive_long_no_cumulative_drift():
    """Case 6: A=2.5 B=2.8 C=3.0 sát nhau → drift câu sau KHÔNG = A+B+C."""
    segs = [{"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0},
            {"id": 2, "start": 1.2, "end": 2.2, "duration": 1.0},
            {"id": 3, "start": 2.4, "end": 3.4, "duration": 1.0}]
    p, r = plan_voice_placements(segs, [2.5, 2.8, 3.0])
    for seg, placed in zip(segs, p):
        assert placed["drift"] <= 0.15 + 1e-9   # trần từng câu
    # Drift câu 3 không phải tổng tràn của 1+2
    assert p[2]["drift"] <= 0.15 + 1e-9
    assert r.max_shift_s <= 0.15 + 1e-9


def test_case7_silence_gap_utilised():
    """Case 7: A end=10.0, B start=11.0 → scheduler mượn 1s silence."""
    segs = [{"id": 1, "start": 8.0, "end": 10.0, "duration": 2.0},
            {"id": 2, "start": 11.0, "end": 12.0, "duration": 1.0}]
    p, _ = plan_voice_placements(segs, [2.8, 1.0])
    # A dài 2.8: slot 2.0 + silence tới 11.0-gap → vừa, không tempo
    assert p[0]["atempo"] == 1.0
    assert p[0]["adjustment"] == "silence"
    assert p[1]["start"] == 11.0  # B không bị đẩy


def test_drift_capped_and_tempo_bounded():
    # 5 câu, mỗi câu TTS 3.5s trong slot 2s, cách 2s — quá tải thật sự.
    segs = _segs(2, 4, 6, 8, 10, dur=2.0)
    p, r = plan_voice_placements(segs, [3.5] * 5, max_start_drift_s=0.15,
                                 max_speed=1.15)
    for seg, placed in zip(segs, p):
        assert placed["start"] - seg["start"] <= 0.15 + 1e-9  # onset giữ
        assert placed["atempo"] <= 1.15 + 1e-9                 # trần tempo
    # Quá tải → phải GHI NHẬN (overlap hoặc needs_compaction), không giấu.
    assert (r.segments_overlapped > 0
            or any(pl["reason"] == "needs_compaction" for pl in p))


def test_missing_duration_keeps_natural_start():
    p, _ = plan_voice_placements(_segs(0, 2), [None, 3.0])
    assert p[0]["start"] == 0.0
    assert p[1]["start"] == 2.0


def test_min_gap_yields_to_onset_priority():
    """Semantic mới: drift-cap (onset) ưu tiên hơn min-gap — clip trước nói
    tới 4.0s, câu sau tự nhiên 4.0s: scheduler giữ start ≤ 4.15 (chấp nhận
    overlap 50ms với gap 0.2) thay vì đẩy start trôi xa."""
    p, r = plan_voice_placements(_segs(0, 4), [4.0, 2.0], min_gap_s=0.2)
    assert p[1]["start"] == pytest.approx(4.15, abs=1e-6)
    assert p[1]["drift"] == pytest.approx(0.15, abs=1e-6)
    assert r.segments_overlapped == 1  # overlap 0.05s được ghi nhận


def test_never_stretches():
    segs = [{"id": 1, "start": 0.0, "end": 4.0, "duration": 4.0}]
    p, _ = plan_voice_placements(segs, [1.0], min_speed=0.5)
    assert p[0]["atempo"] == 1.0  # TTS ngắn → giữ natural, không kéo dài


def _write_tone(path, dur, rate=24000):
    import numpy as np
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        t = np.arange(n) / rate
        arr = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
        w.writeframes(arr.tobytes())


def test_apply_soft_timing_mutates_timeline(tmp_path):
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    _write_tone(str(seg_dir / "seg_00001.wav"), 4.0)
    _write_tone(str(seg_dir / "seg_00002.wav"), 2.0)
    segments = [
        {"id": 1, "start": 0.0, "end": 3.0, "duration": 3.0},
        {"id": 2, "start": 3.0, "end": 5.0, "duration": 2.0},
    ]
    settings = Settings()
    out_dir, report = apply_soft_timing(
        segments, str(seg_dir), str(tmp_path / "timed"), settings)
    # Câu 1 (4.0s, slot 3.0, next 3.0) → tempo 1.15 → PHẢI render.
    assert segments[0]["tempo_factor"] == pytest.approx(1.15, abs=1e-3)
    assert report.segments_compressed == 1
    # Onset câu 2 giữ ≤ 3.15 (không còn dồn 1.1s như scheduler cũ).
    assert segments[1]["start"] <= 3.0 + settings.timing_max_start_drift_s \
        + 1e-6
    # end = vị trí đặt + thời lượng clip thật sau tempo.
    from autodub.media.audio import wav_duration_s
    from autodub.utils import seg_wav_path
    d1 = wav_duration_s(seg_wav_path(out_dir, 1))
    assert segments[0]["end"] == pytest.approx(d1, abs=0.05)
    # duration giữ giá trị GỐC cho báo cáo; field dub_* được gán.
    assert segments[0]["duration"] == 3.0
    assert segments[0]["dub_start"] == 0.0
    assert segments[0]["dub_duration"] == pytest.approx(d1, abs=0.05)
    assert "timing_adjustment" in segments[0]
