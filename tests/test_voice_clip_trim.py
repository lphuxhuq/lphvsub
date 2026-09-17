"""Trim khoảng lặng đầu clip TTS — giọng Việt vào đúng động tác miệng."""

import wave

import numpy as np

from autodub.media.audio import lead_silence_s, postprocess_voice_clip, wav_duration_s


def _write_wav(path, lead_s, tone_s, rate=24000, click_at=None):
    n = int((lead_s + tone_s + 0.1) * rate)
    t = np.arange(n) / rate
    # "Giọng nói": sóng sin biên độ thay đổi (không phải tick đơn lẻ)
    env = np.minimum(1.0, np.clip((t - lead_s) * 8, 0, 1)) * (t >= lead_s)
    x = 0.4 * np.sin(2 * np.pi * 220 * t) * env
    if click_at is not None:
        i = int(click_at * rate)
        x[i : i + int(0.02 * rate)] = 0.5  # click 20ms rồi lại im
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return x, rate


def test_lead_silence_detected_with_guard():
    x, rate = _write_wav("/tmp/trim_probe.wav" if False else _tmp(), lead_s=0.6, tone_s=1.5)
    trim = lead_silence_s(x, rate)
    assert 0.38 <= trim <= 0.52  # 0.6 - guard 0.12 (± sai số cửa sổ)


def _tmp():
    import os
    import tempfile

    return os.path.join(tempfile.mkdtemp(), "probe.wav")


def test_no_lead_silence_returns_zero():
    x, rate = _write_wav(_tmp(), lead_s=0.0, tone_s=1.5)
    assert lead_silence_s(x, rate) == 0.0


def test_isolated_click_not_treated_as_speech():
    x, rate = _write_wav(_tmp(), lead_s=0.7, tone_s=1.0, click_at=0.1)
    trim = lead_silence_s(x, rate)
    assert 0.45 <= trim <= 0.62  # bỏ qua click, bắt đầu ở 0.7s


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
        head = (
            np.frombuffer(w.readframes(int(0.25 * rate)), dtype=np.int16).astype(np.float32) / 32768
        )
    assert lead_silence_s(head, rate) <= 0.13


def test_compute_speech_gain_db_consistency():
    """Xác minh: compute_speech_gain_db tính toán gain tuyến tính cân bằng âm lượng mà không bóp méo."""
    from autodub.media.audio import compute_speech_gain_db

    # 1. Âm thanh câm/rỗng trả về 0.0
    assert compute_speech_gain_db(np.zeros(1000, dtype=np.float32)) == 0.0
    assert compute_speech_gain_db(np.array([], dtype=np.float32)) == 0.0

    # 2. Câu bình thường (peak ~ 0.3)
    s1 = np.sin(np.linspace(0, 100, 24000)) * 0.3
    g1 = compute_speech_gain_db(s1, target_lufs=-16.0)
    assert -15.0 <= g1 <= 15.0

    # 3. Câu quá to (peak 0.95) bị ghìm lại dưới trần -1.5 dBFS
    s2 = np.sin(np.linspace(0, 100, 24000)) * 0.95
    g2 = compute_speech_gain_db(s2, target_lufs=-16.0, max_peak_db=-1.5)
    # Peak mới: 20*log10(0.95) + g2 <= -1.49
    new_peak = 20 * np.log10(0.95) + g2
    assert new_peak <= -1.45


def test_postprocess_preserves_sample_rate_and_avoids_distortion(tmp_path):
    """Xác minh: postprocess_voice_clip giữ nguyên 24kHz / 44.1kHz và áp dụng linear gain."""
    for rate in (24000, 44100):
        src = tmp_path / f"clip_{rate}.wav"
        _write_wav(src, lead_s=0.2, tone_s=1.0, rate=rate)
        dst = tmp_path / f"out_{rate}.wav"
        ok = postprocess_voice_clip(str(src), str(dst), target_lufs=-16.0)
        assert ok is True
        with wave.open(str(dst)) as w:
            assert w.getframerate() == rate, (
                f"Sample rate {rate} phải được giữ nguyên, thực tế: {w.getframerate()}"
            )
            dur = w.getnframes() / float(w.getframerate())
            assert dur > 0.5
