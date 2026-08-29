# Karaoke Acoustic Word Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Giải quyết triệt để vấn đề phụ đề cụm chữ/karaoke bị rơi về chia đều phẳng bằng giải pháp 3 lớp: Acoustic RMS Energy Envelope Segmentation, Fuzzy Anchor Mapping, và Whisper Vietnamese Initial Prompt.

**Architecture:** Tạo module `acoustic_align.py` trích xuất đỉnh năng lượng âm thanh của file WAV, nâng cấp `align.py` với Fuzzy Mapping và Whisper prompt, tích hợp vào `ass_karaoke.py`.

**Tech Stack:** Python 3.11, PySide6, NumPy, Wave, Faster-Whisper, Pytest.

---

### Task 1: Acoustic RMS Energy Envelope Word Segmentation (`autodub/speech/acoustic_align.py`)

**Files:**
- Create: `autodub/speech/acoustic_align.py`
- Test: `tests/test_acoustic_align.py`

**Interfaces:**
- Produces: `acoustic_word_times(text: str, wav_path: str, clip_start: float, clip_dur: float) -> list[tuple[str, float, float]]`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_acoustic_align.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `acoustic_word_times`**
- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_acoustic_align.py -v`
Expected: PASS.

---

### Task 2: Upgrading Whisper Alignment & Fuzzy Mapping (`autodub/speech/align.py`)

**Files:**
- Modify: `autodub/speech/align.py`
- Test: `tests/test_ass_karaoke.py`

**Interfaces:**
- Improves: `_map_words` with fuzzy anchor fallback instead of `None`.
- Adds: `initial_prompt="Đây là bản dịch tiếng Việt phụ đề."` to `_asr_words`.
- Lowers: `_MIN_CLIP_S = 0.15`.

- [ ] **Step 1: Write test for resilient `_map_words`**
- [ ] **Step 2: Update `autodub/speech/align.py`**
- [ ] **Step 3: Run `pytest tests/test_ass_karaoke.py -v`**

---

### Task 3: Integration into `ass_karaoke.py` & Full Verification

**Files:**
- Modify: `autodub/text/ass_karaoke.py`
- Test: `tests/test_ass_karaoke.py`

- [ ] **Step 1: Integrate acoustic fallback into `align_words_for_subtitles`**
- [ ] **Step 2: Run full test suite to verify 100% pass**
- [ ] **Step 3: Commit and generate walkthrough**
