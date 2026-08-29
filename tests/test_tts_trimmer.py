import os
import wave
import numpy as np
import pytest
from autodub.speech.tts_trimmer import trim_tts_silence, compute_speech_extents

def test_compute_speech_extents():
    rate = 16000
    # 0.2s silence + 0.4s audio + 0.2s silence
    lead = np.zeros(int(0.2 * rate), dtype=np.float32)
    tone = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.4, int(0.4 * rate))) * 0.5).astype(np.float32)
    tail = np.zeros(int(0.2 * rate), dtype=np.float32)
    arr = np.concatenate([lead, tone, tail])

    start_s, end_s = compute_speech_extents(arr, rate, threshold_ratio=0.1, margin_s=0.02)
    assert 0.17 <= start_s <= 0.21
    assert 0.59 <= end_s <= 0.63

def test_trim_tts_silence(tmp_path):
    rate = 16000
    lead_silence = np.zeros(int(0.25 * rate), dtype=np.int16)
    audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.5, int(0.5 * rate))) * 16000).astype(np.int16)
    tail_silence = np.zeros(int(0.25 * rate), dtype=np.int16)
    full = np.concatenate([lead_silence, audio, tail_silence])
    
    in_wav = str(tmp_path / "raw.wav")
    out_wav = str(tmp_path / "trimmed.wav")
    with wave.open(in_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(full.tobytes())
        
    out_path, lead_s, tail_s = trim_tts_silence(in_wav, out_wav, margin_s=0.03)
    assert os.path.exists(out_path)
    assert 0.20 <= lead_s <= 0.25
    assert 0.20 <= tail_s <= 0.25
    
    # Kiểm tra thời lượng file sau khi trim
    with wave.open(out_path, "rb") as w:
        trimmed_dur = w.getnframes() / float(w.getframerate())
    assert 0.52 <= trimmed_dur <= 0.60
