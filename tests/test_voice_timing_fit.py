"""Unit test cho fit_voice_to_slot / _decide_tempo (voice-sync TASK-2)."""
import os
import wave

import numpy as np
import pytest

import autodub.media.voice_timing as vt
from autodub.media.voice_timing import _decide_tempo, fit_voice_to_slot


def _write_wav(path, dur_s=1.0, sr=16000):
    t = np.arange(int(dur_s * sr)) / sr
    arr = 0.3 * np.sin(2 * np.pi * 220 * t)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((arr * 32767).astype(np.int16).tobytes())


# --- _decide_tempo: thuần toán, mọi nhánh ---------------------------------

def test_tts_shorter_than_slot_natural():
    assert _decide_tempo(1.6, 2.0) == 1.0


def test_tts_equal_natural():
    assert _decide_tempo(2.0, 2.0) == 1.0


def test_case2_mild_overflow_tempo_within_max():
    """Case 2: 2.2s vào 2.0s → tempo 1.1 (≤ 1.15)."""
    assert abs(_decide_tempo(2.2, 2.0, max_speed=1.15) - 1.1) < 0.001


def test_case3_huge_overflow_capped():
    """Case 3: 3.0s vào 2.0s → muốn 1.5 nhưng chặn 1.15."""
    assert _decide_tempo(3.0, 2.0, max_speed=1.15) == 1.15


def test_below_worthwhile_ignored():
    assert _decide_tempo(2.01, 2.0) == 1.0  # want 1.005 < 1.02


def test_never_stretches():
    """Bất biến: không bao giờ trả < 1.0 (stretch vô hiệu)."""
    assert _decide_tempo(1.0, 10.0, min_speed=0.5) == 1.0
    assert _decide_tempo(0.0, 1.0) == 1.0
    assert _decide_tempo(1.0, 0.0) == 1.0


# --- fit_voice_to_slot: render + cache ------------------------------------

def test_fit_natural_no_ffmpeg(tmp_path):
    src = tmp_path / "s.wav"
    _write_wav(src, dur_s=1.6)
    res = fit_voice_to_slot(str(src), 2.0, str(tmp_path / "out"))
    assert res.tempo_factor == 1.0 and res.rendered is False
    assert res.out_path == str(src)


def test_fit_renders_atempo_and_measures(tmp_path):
    """Render thật qua ffmpeg: wav 2.2s fit vào 2.0s → ~2.0s sau atempo."""
    src = tmp_path / "s.wav"
    _write_wav(src, dur_s=2.2)
    res = fit_voice_to_slot(str(src), 2.0, str(tmp_path / "out"))
    assert res.rendered is True
    assert abs(res.tempo_factor - 1.1) < 0.001
    from autodub.media.audio import wav_duration_s
    got = wav_duration_s(res.out_path)
    assert abs(got - 2.0) < 0.05


def test_fit_caps_at_max_speed(tmp_path):
    src = tmp_path / "s.wav"
    _write_wav(src, dur_s=3.0)
    res = fit_voice_to_slot(str(src), 2.0, str(tmp_path / "out"),
                            max_speed=1.15)
    assert res.tempo_factor == 1.15
    from autodub.media.audio import wav_duration_s
    got = wav_duration_s(res.out_path)
    assert abs(got - 3.0 / 1.15) < 0.05


def test_fit_cache_hit_no_second_render(tmp_path, monkeypatch):
    src = tmp_path / "s.wav"
    _write_wav(src, dur_s=2.2)
    out = tmp_path / "out"
    first = fit_voice_to_slot(str(src), 2.0, str(out))
    assert first.rendered is True

    calls = {"n": 0}
    import autodub.media.audio as audio_mod
    real = audio_mod.apply_atempo

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(audio_mod, "apply_atempo", _counting)
    second = fit_voice_to_slot(str(src), 2.0, str(out))
    assert second.rendered is False  # cache
    assert calls["n"] == 0


# --- stretch (VOICE_FIT_STRETCH) — opt-in ----------------------------------

def test_stretch_disabled_by_default():
    """Mặc định vẫn KHÔNG kéo dài kể cả khi slot dài gấp nhiều lần."""
    assert _decide_tempo(1.0, 10.0, min_speed=0.5) == 1.0


def test_stretch_enabled_floors_at_min_speed():
    """1.6s vào slot 2.0s: muốn 0.8 nhưng chặn tại min_speed 0.90."""
    assert abs(_decide_tempo(1.6, 2.0, min_speed=0.90,
                             allow_stretch=True) - 0.90) < 0.001


def test_stretch_within_floor_uses_exact_ratio():
    """2.0s vào slot 2.1s: want 0.952 ≥ 0.90 → kéo đúng 0.952."""
    assert abs(_decide_tempo(2.0, 2.1, min_speed=0.90,
                             allow_stretch=True) - 2.0 / 2.1) < 0.001


def test_stretch_skips_tiny_difference():
    """1.98s vào 2.0s (chênh 1%): dưới ngưỡng đáng kéo — giữ natural."""
    assert _decide_tempo(1.98, 2.0, min_speed=0.90, allow_stretch=True) == 1.0


def test_stretch_does_not_change_compress_path():
    assert _decide_tempo(3.0, 2.0, max_speed=1.15, allow_stretch=True) == 1.15
