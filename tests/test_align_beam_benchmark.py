"""Benchmark so sánh beam_size=1 (Greedy) và beam_size=2 của Whisper Alignment."""

import math
import struct
import time
import wave

import pytest

from autodub.speech.align import _asr_words, _load_align_model


def _write_complex_tone(path: str, dur: float, rate: int = 16000):
    """Tạo audio nhiều hài âm tần số giọng nói người (150Hz - 800Hz)."""
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        frames = []
        for i in range(n):
            t = i / rate
            val = (
                0.5 * math.sin(2 * math.pi * 200 * t)
                + 0.3 * math.sin(2 * math.pi * 400 * t)
                + 0.2 * math.sin(2 * math.pi * 800 * t)
            )
            frames.append(int(val * 12000))
        w.writeframes(struct.pack(f"<{n}h", *frames))


def test_beam_size_parameter_supported(monkeypatch):
    """Xác minh hàm _asr_words hỗ trợ tham số beam_size."""

    class DummyModel:
        def __init__(self):
            self.last_beam = None

        def transcribe(self, wav_path, **kwargs):
            self.last_beam = kwargs.get("beam_size")
            return [], None

    dummy = DummyModel()
    _asr_words(dummy, "dummy.wav", beam_size=1)
    assert dummy.last_beam == 1

    _asr_words(dummy, "dummy.wav", beam_size=2)
    assert dummy.last_beam == 2


def test_beam1_vs_beam2_speedup_and_consistency(tmp_path):
    """Benchmark so sánh tốc độ và độ tương đồng giữa beam=1 và beam=2."""
    wav_file = tmp_path / "speech_tone.wav"
    _write_complex_tone(str(wav_file), 1.5)

    from unittest import mock

    from autodub.speech.align import unload_align_model

    unload_align_model()
    try:
        model, device, _ = _load_align_model()
        if isinstance(model, mock.Mock):
            pytest.skip("Align model is mocked - skip real benchmark")
    except Exception as e:
        pytest.skip(f"Whisper model không tải được ({e}) - bỏ qua test thật")

    # Đo beam_size=2
    t0 = time.perf_counter()
    words_beam2 = _asr_words(model, str(wav_file), beam_size=2)
    dur_beam2 = time.perf_counter() - t0

    # Đo beam_size=1 (greedy)
    t0 = time.perf_counter()
    words_beam1 = _asr_words(model, str(wav_file), beam_size=1)
    dur_beam1 = time.perf_counter() - t0

    # Greedy phải nhanh hơn hoặc tương đương beam 2
    assert dur_beam1 <= dur_beam2 * 1.25  # Cho phép dung sai nhỏ do context switch

    # Nếu có words, kiểm tra sai số thời gian MAE
    if words_beam1 and words_beam2 and len(words_beam1) == len(words_beam2):
        errors = [
            abs(w1[1] - w2[1]) + abs(w1[2] - w2[2]) for w1, w2 in zip(words_beam1, words_beam2)
        ]
        mae = sum(errors) / (2 * len(errors))
        assert mae <= 0.08  # Sai số mốc thời gian không quá 80ms
