import os
import wave
import numpy as np
import pytest
from autodub.media.voice_stretch import build_stretch_filter_chain, apply_formant_preserved_stretch

def test_build_stretch_filter_chain():
    # Khi tempo = 1.0 -> không cần filter
    assert build_stretch_filter_chain(1.0) == ""
    # Khi tempo = 1.10 -> atempo=1.1
    assert "atempo=1.1" in build_stretch_filter_chain(1.10)
    # Khi tempo = 2.5 -> chuỗi multiple atempo (vì atempo max 2.0)
    chain = build_stretch_filter_chain(2.5)
    assert "atempo=2.0" in chain and "atempo=1.25" in chain

def test_apply_formant_preserved_stretch(tmp_path):
    rate = 16000
    audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, rate)) * 16000).astype(np.int16)
    in_wav = str(tmp_path / "in.wav")
    out_wav = str(tmp_path / "out.wav")
    with wave.open(in_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio.tobytes())

    # Stretch 1.25x
    res = apply_formant_preserved_stretch(in_wav, out_wav, 1.25)
    assert os.path.exists(res)
    with wave.open(res, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    # 1.0s / 1.25 = 0.8s
    assert 0.75 <= dur <= 0.85
