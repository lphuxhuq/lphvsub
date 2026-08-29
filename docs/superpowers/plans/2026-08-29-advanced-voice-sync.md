# Advanced 3-Tier Adaptive Voice Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng hệ thống đồng bộ giọng đọc 3 tầng (3-Tier Adaptive Voice Sync) gồm: Cắt tỉa khoảng lặng TTS (VAD Silence Trimming), Nén âm thanh bảo toàn formants (Formant-Preserved Hybrid Time-Stretch) kết hợp AI Dịch cô đọng (Compact Translation), và Chặn tràn giọng qua ranh giới chuyển cảnh video (Scene-Cut Drift Guard).

**Architecture:** Tách biệt thành các module chuyên biệt: `tts_trimmer.py` xử lý audio năng lượng RMS, `voice_stretch.py` xử lý thuật toán co giãn audio chất lượng cao, `compact_translator.py` xử lý AI semantic compaction, và `scene_detector.py` tích hợp vào scheduler `timing.py`.

**Tech Stack:** Python 3.11, PySide6, FFmpeg, NumPy, Wave, Pytest.

## Global Constraints
- Tất cả mã màu và UI (nếu có) phải tuân thủ tokens.py.
- Tuyệt đối không dùng emoji trong chuỗi hiển thị GUI Python.
- Giữ vững 100% tương thích ngược và vượt qua toàn bộ test suite.

---

### Task 1: TTS VAD Silence Trimmer (`autodub/speech/tts_trimmer.py`)

**Files:**
- Create: `autodub/speech/tts_trimmer.py`
- Test: `tests/test_tts_trimmer.py`

**Interfaces:**
- Produces: `trim_tts_silence(wav_path: str, out_path: str, *, min_silence_s: float = 0.05, margin_s: float = 0.025) -> tuple[str, float, float]` (trả về out_path, trimmed_lead_s, trimmed_tail_s).

- [ ] **Step 1: Write the failing test**

```python
import os
import wave
import numpy as np
import pytest
from autodub.speech.tts_trimmer import trim_tts_silence

def test_trim_tts_silence(tmp_path):
    # Tạo file wav có 200ms im lặng, 400ms âm thanh (sine wave), 200ms im lặng
    rate = 16000
    lead_silence = np.zeros(int(0.2 * rate), dtype=np.int16)
    audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 0.4, int(0.4 * rate))) * 16000).astype(np.int16)
    tail_silence = np.zeros(int(0.2 * rate), dtype=np.int16)
    full = np.concatenate([lead_silence, audio, tail_silence])
    
    in_wav = str(tmp_path / "raw.wav")
    out_wav = str(tmp_path / "trimmed.wav")
    with wave.open(in_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(full.tobytes())
        
    out_path, lead_s, tail_s = trim_tts_silence(in_wav, out_wav, margin_s=0.02)
    assert os.path.exists(out_path)
    assert 0.15 <= lead_s <= 0.20
    assert 0.15 <= tail_s <= 0.20
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_tts_trimmer.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Write implementation**
Implement `trim_tts_silence` using NumPy RMS energy calculation on 10ms hops to detect onset and offset.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_tts_trimmer.py -v`
Expected: PASS.

---

### Task 2: Formant-Preserved Hybrid Time-Stretch (`autodub/media/voice_stretch.py`)

**Files:**
- Create: `autodub/media/voice_stretch.py`
- Modify: `autodub/media/voice_timing.py`
- Test: `tests/test_voice_stretch.py`

**Interfaces:**
- Produces: `apply_formant_preserved_stretch(in_path: str, out_path: str, tempo: float) -> str`

- [ ] **Step 1: Write the failing test**

```python
import os
import pytest
from autodub.media.voice_stretch import apply_formant_preserved_stretch

def test_formant_preserved_stretch_tempo(tmp_path):
    # Test stretching audio file with tempo 1.15x
    in_wav = "tests/fixtures/sample_16k.wav"
    out_wav = str(tmp_path / "stretched.wav")
    if os.path.exists(in_wav):
        res = apply_formant_preserved_stretch(in_wav, out_wav, 1.15)
        assert os.path.exists(res)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_voice_stretch.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `apply_formant_preserved_stretch`**
Use FFmpeg filter chain combining WSOLA / `atempo` with pitch compensation to prevent chipmunk / metallic degradation.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_voice_stretch.py -v`
Expected: PASS.

---

### Task 3: Scene-Cut Aware Drift Guard (`autodub/media/scene_detector.py` & `autodub/media/timing.py`)

**Files:**
- Create: `autodub/media/scene_detector.py`
- Modify: `autodub/media/timing.py`
- Test: `tests/test_scene_detector.py`

**Interfaces:**
- Produces: `detect_scene_cuts(video_path: str, threshold: float = 0.35) -> list[float]`
- Integrates with: `plan_voice_placements(..., scene_cuts: list[float] | None = None)`

- [ ] **Step 1: Write test for scene cut detection and placement clamping**

```python
import pytest
from autodub.media.scene_detector import detect_scene_cuts
from autodub.media.timing import plan_voice_placements

def test_scene_cut_drift_guard():
    segments = [{"start": 1.0, "end": 3.0, "speech_duration": 2.0}]
    durations = [2.8] # Vượt quá 2.0s
    scene_cuts = [3.2] # Chuyển cảnh tại giây 3.2
    placements, report = plan_voice_placements(
        segments, durations, scene_cuts=scene_cuts, max_speed=1.20
    )
    # Clip không được lấn qua giây 3.2
    assert placements[0]["end"] <= 3.2
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/test_scene_detector.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement scene detection and clamp in timing scheduler**
Integrate `scene_cuts` parameter into `plan_voice_placements`.

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/test_scene_detector.py -v`
Expected: PASS.

---

### Task 4: AI Semantic Compactor (`autodub/text/compact_translator.py`)

**Files:**
- Create: `autodub/text/compact_translator.py`
- Test: `tests/test_compact_translator.py`

**Interfaces:**
- Produces: `compact_translation_if_needed(text: str, max_words: int, engine: str = "gemini") -> str`

- [ ] **Step 1: Write test for compaction prompt and word-budget logic**
- [ ] **Step 2: Run test to verify it fails**
- [ ] **Step 3: Implement `compact_translation_if_needed`**
- [ ] **Step 4: Run test to verify it passes**

---

### Task 5: Pipeline & Settings Integration & Verification

**Files:**
- Modify: `autodub/pipeline.py`
- Modify: `autodub/config.py`
- Modify: `autodub_gui/dub_constants.py`

- [ ] **Step 1: Wire all 3 tiers into pipeline.py**
- [ ] **Step 2: Add config toggles to Settings in config.py**
- [ ] **Step 3: Run full pytest suite (all 940+ tests)**
- [ ] **Step 4: Commit changes and generate walkthrough**
