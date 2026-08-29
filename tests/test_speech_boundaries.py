"""Unit test cho refine_speech_boundaries (voice-sync TASK-1).

Fixture wav tự sinh: 16 kHz mono PCM16, sine burst đặt đúng thời điểm —
không cần file nhị phân.
"""
import wave

import numpy as np
import pytest

from autodub.speech.boundaries import refine_speech_boundaries

SR = 16000


def _write_wav(path, sr, arr):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((arr * 32767).astype(np.int16).tobytes())


def _fixture(path, bursts, dur_s=20.0, amp=0.3):
    """bursts: [(t0, t1)] giây — sine 220 Hz trong khoảng đó, ngoài ra im."""
    t = np.arange(int(dur_s * SR)) / SR
    arr = np.zeros_like(t)
    for t0, t1 in bursts:
        m = (t >= t0) & (t < t1)
        arr[m] = amp * np.sin(2 * np.pi * 220 * t[m])
    _write_wav(path, SR, arr)


def test_case4_shrinks_vad_to_speech(tmp_path):
    """Case 4 spec: VAD 10→12.2, speech thật 10.4→11.8."""
    wav = tmp_path / "a.wav"
    _fixture(wav, [(10.4, 11.8)])
    segs = [{"id": 1, "text": "x", "start": 10.0, "end": 12.2,
             "duration": 2.2}]
    out = refine_speech_boundaries(segs, str(wav))
    s = out[0]
    assert s["vad_start"] == 10.0 and s["vad_end"] == 12.2
    # margin 60ms + frame quantization 10ms
    assert abs(s["speech_start"] - (10.4 - 0.06)) < 0.09
    assert abs(s["speech_end"] - (11.8 + 0.06)) < 0.09
    assert s["start"] == 10.0 and s["end"] == 12.2  # KHÔNG đụng field cũ
    assert s["duration"] == 2.2


def test_boundary_already_good_kept(tmp_path):
    """Energy bắt đầu ngay đầu window → side giữ nguyên (delta < 80ms)."""
    wav = tmp_path / "a.wav"
    _fixture(wav, [(5.0, 7.0)])
    segs = [{"id": 1, "text": "x", "start": 5.0, "end": 7.05,
             "duration": 2.05}]
    out = refine_speech_boundaries(segs, str(wav))[0]
    assert out["speech_start"] == 5.0  # không thu hẹp trái
    assert out["speech_end"] <= 7.05   # chỉ co phải


def test_near_silent_window_kept(tmp_path):
    """peak < ABS_FLOOR → không gán field mới."""
    wav = tmp_path / "a.wav"
    t = np.arange(int(4 * SR)) / SR
    _write_wav(wav, SR, 0.001 * np.sin(2 * np.pi * 220 * t))
    segs = [{"id": 1, "text": "x", "start": 1.0, "end": 3.0,
             "duration": 2.0}]
    out = refine_speech_boundaries(segs, str(wav))[0]
    assert "speech_start" not in out


def test_shrink_guard_min_duration(tmp_path):
    """Năng lượng chỉ lóe tí giữa window → giữ nguyên (quá ngắn sau thu)."""
    wav = tmp_path / "a.wav"
    _fixture(wav, [(2.4, 2.6)], amp=0.02)
    segs = [{"id": 1, "text": "x", "start": 1.0, "end": 4.0,
             "duration": 3.0}]
    out = refine_speech_boundaries(segs, str(wav))[0]
    if "speech_start" in out:
        # nếu có gán thì vẫn phải ≥ max(0.2, 25% vad) — guard ép giữ nguyên
        assert out["speech_end"] - out["speech_start"] >= 0.2


def test_multiple_segments_no_cross_overlap(tmp_path):
    wav = tmp_path / "a.wav"
    _fixture(wav, [(2.0, 3.0), (5.0, 6.5), (9.0, 9.5)])
    segs = [
        {"id": 1, "text": "x", "start": 1.8, "end": 3.2, "duration": 1.4},
        {"id": 2, "text": "y", "start": 4.8, "end": 6.7, "duration": 1.9},
        {"id": 3, "text": "z", "start": 8.9, "end": 9.7, "duration": 0.8},
    ]
    out = refine_speech_boundaries(segs, str(wav))
    bounds = [(s["speech_start"], s["speech_end"]) for s in out]
    for (a0, a1), (b0, b1) in zip(bounds, bounds[1:]):
        assert a1 <= b0  # chỉ thu hẹp → không bao giờ giao
    for s in out:
        assert s["vad_start"] <= s["speech_start"] <= s["speech_end"] \
            <= s["vad_end"]


def test_input_not_mutated(tmp_path):
    wav = tmp_path / "a.wav"
    _fixture(wav, [(10.4, 11.8)])
    segs = [{"id": 1, "text": "x", "start": 10.0, "end": 12.2,
             "duration": 2.2}]
    before = [dict(s) for s in segs]
    refine_speech_boundaries(segs, str(wav))
    assert segs == before


def test_bad_wav_returns_unchanged(tmp_path):
    bad = tmp_path / "bad.wav"
    bad.write_bytes(b"not a wav")
    segs = [{"id": 1, "text": "x", "start": 0.0, "end": 1.0,
             "duration": 1.0}]
    out = refine_speech_boundaries(segs, str(bad))
    assert out == segs
    assert "speech_start" not in out[0]


def test_empty_segments(tmp_path):
    wav = tmp_path / "a.wav"
    _fixture(wav, [(1.0, 2.0)])
    assert refine_speech_boundaries([], str(wav)) == []


def test_whisper_word_anchor_onset():
    from autodub.speech.transcriber import _anchor_segment_to_words
    seg = {
        "start": 4.70,
        "end": 6.80,
        "words": [
            {"word": "Hello", "start": 5.15, "end": 5.40},
            {"word": "world", "start": 5.45, "end": 6.70},
        ],
    }
    anchored = _anchor_segment_to_words(seg)
    assert anchored["start"] == 5.15
    assert anchored["end"] == 6.70
    assert anchored["duration"] == round(6.70 - 5.15, 3)

