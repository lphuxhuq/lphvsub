"""Trim khoảng lặng đầu clip TTS — giọng Việt vào đúng động tác miệng."""
import wave

import numpy as np
import pytest

from autodub.media.audio import lead_silence_s, postprocess_voice_clip, wav_duration_s


def _write_wav(path, lead_s, tone_s, rate=24000, click_at=None):
    n = int((lead_s + tone_s + 0.1) * rate)
    t = np.arange(n) / rate
    # "Giọng nói": sóng sin biên độ thay đổi (không phải tick đơn lẻ)
    env = np.minimum(1.0, np.clip((t - lead_s) * 8, 0, 1)) * (t >= lead_s)
    x = 0.4 * np.sin(2 * np.pi * 220 * t) * env
    if click_at is not None:
        i = int(click_at * rate)
        x[i:i + int(0.02 * rate)] = 0.5  # click 20ms rồi lại im
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return x, rate


def test_lead_silence_detected_with_guard():
    x, rate = _write_wav("/tmp/trim_probe.wav" if False else
                         _tmp(), lead_s=0.6, tone_s=1.5)
    trim = lead_silence_s(x, rate)
    assert 0.38 <= trim <= 0.52   # 0.6 - guard 0.12 (± sai số cửa sổ)


def _tmp():
    import tempfile, os
    return os.path.join(tempfile.mkdtemp(), "probe.wav")


def test_no_lead_silence_returns_zero():
    x, rate = _write_wav(_tmp(), lead_s=0.0, tone_s=1.5)
    assert lead_silence_s(x, rate) == 0.0


def test_isolated_click_not_treated_as_speech():
    x, rate = _write_wav(_tmp(), lead_s=0.7, tone_s=1.0, click_at=0.1)
    trim = lead_silence_s(x, rate)
    assert 0.45 <= trim <= 0.62   # bỏ qua click, bắt đầu ở 0.7s


def test_all_silent_returns_zero():
    rate = 24000
    x = np.zeros(int(2.0 * rate), dtype=np.float32)
    assert lead_silence_s(x, rate) == 0.0


def test_postprocess_trims_real_ffmpeg(tmp_path):
    src = tmp_path / "seg_00001.wav"
    _write_wav(src, lead_s=0.8, tone_s=2.0)
    dst = tmp_path / "out.wav"
    ok = postprocess_voice_clip(str(src), str(dst))
    assert ok is True
    before, after = wav_duration_s(str(src)), wav_duration_s(str(dst))
    # 0.8s im lặng bị bỏ gần hết (giữ ~0.12s guard): dài hơn trước ~0.7s
    assert before - after >= 0.55
    # giọng bật trong vòng guard (~0.12s) — không còn 0.8s lặng đầu
    with wave.open(str(dst)) as w:
        rate = w.getframerate()
        head = (np.frombuffer(w.readframes(int(0.25 * rate)),
                              dtype=np.int16).astype(np.float32) / 32768)
    assert lead_silence_s(head, rate) <= 0.13
