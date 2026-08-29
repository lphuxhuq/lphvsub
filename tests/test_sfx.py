import os
import wave
import numpy as np
import pytest
from autodub.media.sfx import generate_sfx, write_sfx_wav


def test_generate_sfx_all_presets():
    for preset in ("whoosh", "pop", "swish", "cinematic"):
        arr = generate_sfx(preset=preset, sample_rate=44100, gain_db=-12.0)
        assert isinstance(arr, np.ndarray)
        assert arr.dtype == np.int16
        assert len(arr) > 0
        # Peak value bounded by int16
        assert np.max(np.abs(arr)) <= 32767


def test_write_sfx_wav(tmp_path):
    wav_path = str(tmp_path / "whoosh.wav")
    out = write_sfx_wav(wav_path, preset="whoosh", sample_rate=44100)
    assert os.path.exists(out)
    assert os.path.getsize(out) > 500
    with wave.open(out, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 44100
        assert w.getsampwidth() == 2
