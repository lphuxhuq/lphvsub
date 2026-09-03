# AI Viral Shorts & Reels Clipper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng tính năng AI Viral Shorts & Reels Clipper hoàn chỉnh: phân tích kịch bản video để tìm các mốc cao trào ngắn 25-65s, chấm điểm Viral Score, căn chỉnh câu nói và cắt xuất video 9:16 Shorts/TikTok có phụ đề và Smart Reframe.

**Architecture:**
- `viral_clipper.py`: Phân tích kịch bản bằng Direct AI API (Gemini/OpenAI/v.v.) + Heuristic Analyzer offline fallback.
- `clipper.py`: Trích xuất slice phụ đề ASS theo mốc thời gian và render clip 9:16 bằng FFmpeg.
- `viral_clipper_dialog.py`: Giao diện Qt GUI Dark-themed trực quan cho phép xem trước và 1-click xuất Shorts.

**Tech Stack:** Python 3.11, PySide6, FFmpeg filtergraph, NumPy, pytest.

---

### Task 1: Module AI & Heuristic Highlight Analyzer (`autodub/content/viral_clipper.py`)

**Files:**
- Create: `autodub/content/viral_clipper.py`
- Test: `tests/test_viral_clipper.py`

**Interfaces:**
- `snap_to_segment_boundaries(start_sec: float, end_sec: float, segments: list[dict], min_duration: float = 25.0, max_duration: float = 65.0) -> tuple[float, float, int, int]`
- `heuristic_viral_analysis(segments: list[dict], video_title: str = "", max_clips: int = 5, scene_cuts: list[float] | None = None) -> list[dict]`
- `analyze_viral_highlights(segments: list[dict], settings, video_title: str = "", min_duration: float = 25.0, max_duration: float = 65.0, max_clips: int = 5, scene_cuts: list[float] | None = None) -> list[dict]`

- [x] **Step 1: Viết test cho `snap_to_segment_boundaries` và `heuristic_viral_analysis`**
- [x] **Step 2: Viết test cho `analyze_viral_highlights` với mock Direct AI Client**
- [x] **Step 3: Triển khai `autodub/content/viral_clipper.py`**
- [x] **Step 4: Chạy test xác nhận PASS**
- [x] **Step 5: Commit**

---

### Task 2: Subtitle Slicer & Media Clipper Engine (`autodub/media/clipper.py`)

**Files:**
- Create: `autodub/media/clipper.py`
- Test: `tests/test_clipper_media.py`

**Interfaces:**
- `slice_ass_subtitles(ass_text: str, start_time: float, end_time: float) -> str`
- `build_short_export_command(source_video: str, source_audio: str | None, ass_sub_path: str | None, start_time: float, end_time: float, output_path: str, aspect_preset: str = "tiktok_9_16", reframe_mode: str = "blur") -> list[str]`
- `export_short_clip(source_video: str, source_audio: str | None, ass_sub_path: str | None, start_time: float, end_time: float, output_path: str, aspect_preset: str = "tiktok_9_16", reframe_mode: str = "blur") -> str`

- [x] **Step 1: Viết test cho `slice_ass_subtitles` (kiểm tra shift time và lọc dòng thoại ngoài dải)**
- [x] **Step 2: Viết test cho `build_short_export_command`**
- [x] **Step 3: Triển khai `autodub/media/clipper.py`**
- [x] **Step 4: Chạy test xác nhận PASS**
- [x] **Step 5: Commit**

---

### Task 3: Tích hợp vào `autodub/editor.py` & Pipeline

**Files:**
- Modify: `autodub/editor.py`
- Test: `tests/test_editor.py`

**Interfaces:**
- `get_or_analyze_viral_clips(state: EditorState, settings: Settings, force_refresh: bool = False) -> list[dict]`
- `export_project_short_clip(state: EditorState, clip_id: int, settings: Settings, output_dir: str | None = None) -> str`

- [x] **Step 1: Viết test cho việc nạp và lưu `viral_clips.json` trong Editor**
- [x] **Step 2: Triển khai các hàm hỗ trợ trong `autodub/editor.py`**
- [x] **Step 3: Chạy test xác nhận PASS**
- [x] **Step 4: Commit**

---

### Task 4: Giao diện `ViralClipperDialog` (`autodub_gui/viral_clipper_dialog.py`)

**Files:**
- Create: `autodub_gui/viral_clipper_dialog.py`
- Modify: `autodub_gui/editor_page.py` (hoặc thanh công cụ Editor)
- Test: `tests/test_viral_clipper_dialog.py`

**Interfaces:**
- `ViralClipperDialog(parent, editor_state, settings)`
- Giao diện Dark theme: Clip Cards, Viral Score Badge, Nút Preview, Nút Export 9:16.

- [x] **Step 1: Viết test khởi tạo `ViralClipperDialog` bằng `qtbot`**
- [x] **Step 2: Triển khai `ViralClipperDialog`**
- [x] **Step 3: Gắn nút "AI Shorts Clipper" vào thanh công cụ Editor**
- [x] **Step 4: Chạy test xác nhận PASS**
- [x] **Step 5: Commit**

---

### Task 5: Full Regression Testing & Verification

- [x] **Step 1: Chạy toàn bộ pytest suite (974 tests PASS 100%)**
- [x] **Step 2: Báo cáo nghiệm thu hoàn tất**
