import os
import wave
import numpy as np
import pytest
from autodub.speech.acoustic_align import acoustic_word_times

def test_acoustic_word_times_aligns_with_audio_bursts(tmp_path):
    rate = 16000
    # 0.1s silence + 0.3s tone1 + 0.1s silence + 0.3s tone2 + 0.1s silence
    s1 = np.zeros(int(0.1 * rate), dtype=np.int16)
    t1 = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.3, int(0.3 * rate))) * 16000).astype(np.int16)
    s2 = np.zeros(int(0.1 * rate), dtype=np.int16)
    t2 = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.3, int(0.3 * rate))) * 16000).astype(np.int16)
    s3 = np.zeros(int(0.1 * rate), dtype=np.int16)
    full = np.concatenate([s1, t1, s2, t2, s3])
    
    wav_path = str(tmp_path / "burst.wav")
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(full.tobytes())
        
    words = acoustic_word_times("Xin chào", wav_path, clip_start=1.0, clip_dur=0.9)
    assert len(words) == 2
    assert words[0][0] == "Xin"
    assert words[1][0] == "chào"
    # Từ đầu tiên bắt đầu khoảng 1.1s (sau 0.1s silence)
    assert 1.05 <= words[0][1] <= 1.15
    # Từ thứ 2 kết thúc khoảng 1.8s
    assert 1.75 <= words[1][2] <= 1.85
