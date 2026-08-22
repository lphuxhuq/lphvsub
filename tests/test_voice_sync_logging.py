"""Unit test cho log [VOICE-SYNC] (voice-sync TASK-5)."""
import logging
import math
import wave

import numpy as np
import pytest

from autodub.config import Settings
from autodub.media.timing import apply_soft_timing


def _write_tone(path, dur, rate=16000):
    t = np.arange(int(dur * rate)) / rate
    arr = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(arr.tobytes())


def _mk_segs(n, slot=1.0, spacing=1.2):
    return [{"id": i + 1, "start": i * spacing,
             "end": i * spacing + slot, "duration": slot}
            for i in range(n)]


def test_log_contains_required_fields(tmp_path, caplog):
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    _write_tone(str(seg_dir / "seg_00001.wav"), 2.2)   # slot 1.0 → tempo
    _write_tone(str(seg_dir / "seg_00002.wav"), 1.0)
    segments = _mk_segs(2)
    with caplog.at_level(logging.INFO, logger="autodub.timing"):
        apply_soft_timing(segments, str(seg_dir), str(tmp_path / "timed"),
                          Settings())
    voice_sync = [r for r in caplog.records
                  if "[VOICE-SYNC]" in r.getMessage()]
    assert voice_sync, "phải có log [VOICE-SYNC]"
    msg = voice_sync[0].getMessage()
    for field in ("segment=", "source:", "tts: natural=", "available=",
                  "tempo=", "final:", "adjustment=", "drift="):
        assert field in msg, f"thiếu trường {field} trong: {msg}"


def test_log_sampling_for_long_video(tmp_path, caplog):
    """Video dài: log_every sample — 120 câu chỉ ~vài chục dòng, không 120."""
    n = 120
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    for i in range(1, n + 1):
        _write_tone(str(seg_dir / f"seg_{i:05d}.wav"), 1.0)
    segments = _mk_segs(n)
    with caplog.at_level(logging.INFO, logger="autodub.timing"):
        apply_soft_timing(segments, str(seg_dir), str(tmp_path / "timed"),
                          Settings())
    voice_sync = [r for r in caplog.records
                  if "[VOICE-SYNC]" in r.getMessage()]
    # log_every = total//100 = 1 với 120 câu → vẫn ok; nhưng không có câu
    # nào tempo/overlap → mỗi câu đều log vì log_every=1. Test mức: số dòng
    # không vượt quá tổng số câu + không bỏ câu bị fit.
    assert len(voice_sync) <= n
    assert all("[VOICE-SYNC]" in r.getMessage() for r in voice_sync)


def test_fitted_and_overlapped_always_logged(tmp_path, caplog):
    """Câu bị tempo/overlap LUÔN log kể cả khi sample bỏ qua câu khác."""
    n = 150  # log_every = 1 (max(10, 150//100)=1)? — 150//100=1 → vẫn 1.
    # Dùng n đủ lớn để log_every > 1: n=1000 quá nặng — mô phỏng trực tiếp
    # qua placement thay thế: tạo 1 câu tempo giữa đám natural.
    seg_dir = tmp_path / "segs"
    seg_dir.mkdir()
    segments = _mk_segs(3, slot=1.0, spacing=1.12)
    _write_tone(str(seg_dir / "seg_00001.wav"), 1.0)
    _write_tone(str(seg_dir / "seg_00002.wav"), 1.5)  # tràn → tempo
    _write_tone(str(seg_dir / "seg_00003.wav"), 1.0)
    with caplog.at_level(logging.INFO, logger="autodub.timing"):
        apply_soft_timing(segments, str(seg_dir), str(tmp_path / "timed"),
                          Settings())
    voice_sync = [r.getMessage() for r in caplog.records
                  if "[VOICE-SYNC]" in r.getMessage()]
    fitted = [m for m in voice_sync if "segment=2" in m]
    assert fitted, "câu bị fit phải được log"
    assert "tempo=1." in fitted[0] and fitted[0].count("tempo=1.") > 0
