# Dual-Edge Scene Guard & Word-Level Timing Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khắc phục triệt để tình trạng phụ đề và giọng đọc xuất hiện trước khi video chuyển cảnh (sub/voice nói trước cảnh) thông qua:
1. Neo mốc thời gian vào từ đầu tiên (Word-level anchor) và giảm padding VAD từ 500ms xuống 150ms.
2. Bộ chốt chặn cảnh kép (Dual-Edge Scene Guard: Left-Edge snapping & Right-Edge clamping).
3. Tích hợp tự động quét chuyển cảnh trong Pipeline và Trình chỉnh sửa (Editor).

**Architecture:** 
- ASR (`transcriber.py` & `boundaries.py`) trích xuất mốc phát âm thật của từ đầu tiên (`words[0].start`).
- Scene Detector (`scene_detector.py`) phân tích điểm cắt cảnh qua FFmpeg showinfo và tính toán `snap_to_scene_boundaries`.
- Voice Sync (`timing.py`) bảo đảm mọi câu thoại không vượt ngược về cảnh trước và không tràn sang cảnh sau.
- Pipeline (`pipeline.py`) và Editor (`editor.py`) tự động quét và áp dụng Scene Guard khi xếp lịch thời gian âm thanh/phụ đề.

**Tech Stack:** Python 3.11, faster-whisper, FFmpeg, NumPy, pytest.

## Global Constraints
- Tất cả các mốc thời gian làm tròn tối đa 3 chữ số thập phân (độ chính xác mili-giây).
- Không phá vỡ tương thích dữ liệu `segments` cũ (giữ nguyên các trường `id`, `text`, `start`, `end`, `duration`).
- Quá trình quét chuyển cảnh `detect_scene_cuts` có bộ nhớ đệm `data/scene_cuts.json` để không tốn thời gian quét lại.
- Luôn giữ 100% các bài kiểm thử unit tests hiện có vượt qua (PASS).

---

### Task 1: Word-Level Onset Anchor & VAD Padding Optimization

**Files:**
- Modify: `autodub/speech/transcriber.py:400-450`
- Modify: `autodub/speech/boundaries.py:25-40, 100-120`
- Test: `tests/test_speech_boundaries.py`

**Interfaces:**
- Consumes: `raw_segments` từ faster-whisper với `word_timestamps=True`.
- Produces: `segments` có `start` được neo chính xác vào `words[0]["start"]` khi độ lệch hợp lệ (<= 0.45s).

- [x] **Step 1: Viết failing test kiểm tra word-level onset anchor**
- [x] **Step 2: Chạy test để xác nhận fail**
- [x] **Step 3: Triển khai tối ưu hóa trong `transcriber.py` & `boundaries.py`**
- [x] **Step 4: Chạy test để xác nhận pass**
- [x] **Step 5: Commit**

---

### Task 2: Dual-Edge Scene Guard in `scene_detector.py`

**Files:**
- Modify: `autodub/media/scene_detector.py`
- Test: `tests/test_scene_detector.py`

**Interfaces:**
- Produces: `snap_to_scene_boundaries(start, end, scene_cuts, threshold_s=0.45) -> tuple[float, float]`
- Produces: `load_or_detect_scene_cuts(video_path, work_dir, threshold=0.35) -> list[float]`

- [x] **Step 1: Viết test cho Left-Edge và Right-Edge Scene Guard**
- [x] **Step 2: Chạy test để xác nhận fail**
- [x] **Step 3: Triển khai `snap_to_scene_boundaries` và `load_or_detect_scene_cuts` trong `scene_detector.py`**
- [x] **Step 4: Chạy test để xác nhận pass**
- [x] **Step 5: Commit**

---

### Task 3: Scene Guard Integration in `timing.py`

**Files:**
- Modify: `autodub/media/timing.py:110-155, 250-270`
- Test: `tests/test_timing.py`

**Interfaces:**
- Consumes: `scene_cuts: list[float] | None`
- Modifies: `plan_voice_placements` và `apply_soft_timing` để áp dụng Left-Edge snapping và chống vượt ngược qua Scene Cut khi tính Pre-Roll.

- [x] **Step 1: Viết test kiểm tra `plan_voice_placements` với `scene_cuts`**
- [x] **Step 2: Chạy test để xác nhận fail**
- [x] **Step 3: Cập nhật `plan_voice_placements` & `apply_soft_timing` trong `timing.py`**
- [x] **Step 4: Chạy test để xác nhận pass**
- [x] **Step 5: Commit**

---

### Task 4: Pipeline & Editor Wiring

**Files:**
- Modify: `autodub/pipeline.py:720-740`
- Modify: `autodub/editor.py:760-785`
- Test: `tests/test_editor.py`

**Interfaces:**
- Pipeline tự động gọi `load_or_detect_scene_cuts(video_path, work_dir)` và truyền `scene_cuts` vào `apply_soft_timing`.
- Editor tự động nạp `scene_cuts.json` khi rebuild output.

- [x] **Step 1: Viết test kiểm tra pipeline & editor truyền `scene_cuts`**
- [x] **Step 2: Cập nhật `pipeline.py` & `editor.py`**
- [x] **Step 3: Chạy test để xác nhận pass**
- [x] **Step 4: Commit**

---

### Task 5: Full Regression & Verification

- [x] **Step 1: Chạy toàn bộ pytest suite (111+ unit tests PASS 100%)**
- [x] **Step 2: Cập nhật tài liệu walkthrough**
