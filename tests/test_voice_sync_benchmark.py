"""Benchmark voice-sync trên fixtures tổng hợp (TASK-6) + AC-14 placement.

Fixture mô phỏng 3 loại video (spec Phase 15):
- A "nói chậm": slot dài, TTS ≈ 0.8× slot → hầu hết natural.
- B "nói nhanh": slot ngắn sát nhau, TTS ≈ 1.1-1.25× → tempo fitting.
- C "VI dài": TTS ≈ 1.4× slot → silence + tempo + residual flags.

Metric đo trên placement (thuần toán, không cần video thật):
speech/dub onset-end error, max/avg drift, số overlap, số forced
compression, video speed (luôn 1.0 — không retime). Kết quả ghi ra
docs/VOICE_SYNC_BENCHMARK.md.
"""
import wave

import numpy as np
import pytest

from autodub.media.timing import plan_voice_placements

KW = dict(max_start_drift_s=0.15, min_gap_s=0.12,
          min_speed=0.90, max_speed=1.15)


def _fixture(name, n, slot, spacing, tts_ratio, jitter=0.0, seed=7):
    rng = np.random.default_rng(seed)
    segs, durations = [], []
    for i in range(n):
        start = i * spacing
        dur = slot * float(np.clip(tts_ratio + rng.normal(0, jitter), 0.3, 3.0))
        segs.append({"id": i + 1, "speech_start": start,
                     "speech_end": start + slot, "speech_duration": slot,
                     "start": start, "end": start + slot, "duration": slot})
        durations.append(round(dur, 3))
    return name, segs, durations


def _metrics(segs, durations):
    placements, report = plan_voice_placements(segs, durations, **KW)
    drifts = [p["drift"] for p in placements]
    end_errs = []
    for seg, p, dur in zip(segs, placements, durations):
        final = dur / p["atempo"] if p["atempo"] > 1 else dur
        end_errs.append(max(0.0, (p["start"] + final) - seg["speech_end"]))
    return {
        "segments": len(segs),
        "avg_drift": float(np.mean(drifts)),
        "max_drift": float(np.max(drifts)),
        "avg_end_err": float(np.mean(end_errs)),
        "max_end_err": float(np.max(end_errs)),
        "overlaps": report.segments_overlapped,
        "forced_compression": report.segments_compressed,
        "video_speed": 1.0,
    }


FIXTURES = [
    _fixture("A — nói chậm (slot 3.0s, TTS≈0.8×)", 40, 3.0, 4.5, 0.8, 0.05),
    _fixture("B — nói nhanh (slot 1.2s, TTS≈1.18×)", 60, 1.2, 1.5, 1.18, 0.05),
    # C: gap giữa câu chỉ 0.2s — silence không đủ chứa TTS 1.4× → phải tempo.
    _fixture("C — VI dài (slot 2.0s, TTS≈1.4×)", 50, 2.0, 2.2, 1.4, 0.05),
]


def test_drift_within_threshold_all_fixtures():
    for name, segs, durs in FIXTURES:
        m = _metrics(segs, durs)
        assert m["max_drift"] <= 0.15 + 1e-9, f"{name}: drift vượt trần"
        assert m["video_speed"] == 1.0


def test_slow_speech_mostly_natural():
    m = _metrics(*FIXTURES[0][1:])
    assert m["forced_compression"] <= 3  # TTS ngắn hơn slot → gần như không nén


def test_fast_speech_uses_tempo_not_shift():
    m = _metrics(*FIXTURES[1][1:])
    assert m["forced_compression"] > 0
    assert m["max_drift"] <= 0.15 + 1e-9


def test_long_vi_capped_and_reported():
    """C: quá 1.15× → tempo chặn trần, phần thiếu được flag (overlap/
    needs_compaction), KHÔNG kéo drift để chứa."""
    name, segs, durs = FIXTURES[2]
    placements, report = plan_voice_placements(segs, durs, **KW)
    assert all(p["atempo"] <= 1.15 + 1e-9 for p in placements)
    assert (report.segments_overlapped > 0
            or any(p["reason"] == "needs_compaction" for p in placements))


def test_benchmark_doc_written():
    """Sinh docs/VOICE_SYNC_BENCHMARK.md từ kết quả đo (AC-12)."""
    import os
    lines = [
        "# VOICE SYNC — BENCHMARK (fixtures tổng hợp)",
        "",
        "> Sinh tự động từ `tests/test_voice_sync_benchmark.py`. Drift trần = "
        "0.15s; tempo trần = 1.15; KHÔNG retime video.",
        "",
        "| Fixture | Segments | Avg drift | Max drift | Avg end err | "
        "Max end err | Overlap | Forced tempo | Video speed |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, segs, durs in FIXTURES:
        m = _metrics(segs, durs)
        lines.append(
            f"| {name} | {m['segments']} | {m['avg_drift']:.3f} | "
            f"{m['max_drift']:.3f} | {m['avg_end_err']:.3f} | "
            f"{m['max_end_err']:.3f} | {m['overlaps']} | "
            f"{m['forced_compression']} | {m['video_speed']} |")
    lines += [
        "",
        "## So sánh với scheduler cũ (shift→compress→overlap)",
        "",
        "- Scheduler cũ cho phép drift tới **1.5s/câu** (trần "
        "`timing_max_drift_s`) — dub có thể trễ gần 2 giây so với môi.",
        "- Scheduler mới: max drift đo được ≤ **0.15s** ở mọi fixture; phần "
        "TTS thừa được xử lý bằng silence → per-segment tempo (trần 1.15) → "
        "overlap nhỏ được báo cáo, thay vì dồn trễ.",
        "",
        "## CHƯA XÁC ĐỊNH",
        "",
        "Đo trên video Douyin thật (có môi) cần chạy thủ công — benchmark "
        "này dùng fixtures tổng hợp để CI lặp lại được.",
        "",
    ]
    out = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "docs", "VOICE_SYNC_BENCHMARK.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    assert os.path.isfile(out)


# --- AC-14: merge đặt clip tại start + wav thật ----------------------------

def _write_tone(path, dur, rate=16000):
    t = np.arange(int(dur * rate)) / rate
    arr = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(arr.tobytes())


def test_merge_places_clip_at_dub_start(tmp_path):
    """AC-14: im lặng trước dub_start, có tiếng sau đó — đúng (start, wav)."""
    from autodub.media.audio import merge_segments
    from autodub.utils import seg_wav_path
    import os

    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    segments = [{"id": 1, "start": 5.0, "end": 6.0, "duration": 1.0}]
    _write_tone(str(seg_wav_path(str(seg_dir), 1)), 1.0)
    out = tmp_path / "mixed.wav"
    merge_segments(segments, str(seg_dir), str(out), total_duration=8.0)

    with wave.open(str(out), "rb") as w:
        rate, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        arr = np.frombuffer(w.readframes(n), dtype=np.int16) \
            .reshape(-1, ch).mean(axis=1)

    def _rms(a, b):
        seg = arr[int(a * rate):int(b * rate)]
        return float(np.sqrt((seg.astype(np.float32) ** 2).mean()))

    assert _rms(0.0, 4.0) < 50        # trước dub_start: im
    assert _rms(5.1, 5.9) > 500       # đúng chỗ clip: có tiếng
    assert _rms(6.5, 7.5) < 50        # sau clip hết: im
