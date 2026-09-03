# Smart Auto-Reframe (9:16 Shorts/TikTok) & Auto Scene Cut SFX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 
1. Tự động chuyển đổi tỷ lệ video sang 9:16 (Shorts/TikTok/Reels), 1:1, 16:9 với 3 chế độ Reframe: Blur Background nghệ thuật, Top/Split Screen, Center Crop lấp đầy.
2. Tự động chèn âm thanh chuyển cảnh (Auto SFX: Whoosh, Pop, Swish, Cinematic) tại các điểm Scene Cut để tăng độ lôi cuốn của video.

**Architecture:**
- `subtitle.py`: Mở rộng `build_aspect_ratio_filter` với các chế độ `reframe_mode` (`blur`, `top_split`, `center_crop`).
- `sfx.py`: Sinh âm thanh chuyển cảnh chất lượng cao bằng NumPy (zero external dependencies).
- `audio.py`: Tích hợp SFX mixing tại các mốc `scene_cuts` trong `merge_segments`.
- `config.py`, `pipeline.py`, `editor.py`: Quản lý cài đặt, bảo toàn khi xuất và chỉnh sửa.
- `style_dialog.py` & `settings_fields.py`: Tích hợp giao diện điều khiển trực quan.

**Tech Stack:** Python 3.11, FFmpeg filtergraph, NumPy, PySide6, pytest.

---

### Task 1: Mở rộng Smart Auto-Reframe trong `subtitle.py`

**Files:**
- Modify: `autodub/media/subtitle.py:213-260`
- Test: `tests/test_subtitle.py`

**Interfaces:**
- `build_aspect_ratio_filter(aspect_preset: str | None, video_w: int, video_h: int, reframe_mode: str = "blur") -> tuple[str, int, int] | None`

- [x] **Step 1: Viết failing test cho các chế độ Reframe**
- [x] **Step 2: Triển khai các chế độ Reframe trong `subtitle.py`**
- [x] **Step 3: Chạy test xác nhận PASS**
- [x] **Step 4: Commit**

---

### Task 2: Module Procedural SFX Generator (`autodub/media/sfx.py`)

**Files:**
- Create: `autodub/media/sfx.py`
- Test: `tests/test_sfx.py`

**Interfaces:**
- `generate_sfx(preset: str = "whoosh", sample_rate: int = 44100, duration_s: float = 0.35, gain_db: float = -14.0) -> np.ndarray`
- `write_sfx_wav(output_path: str, preset: str = "whoosh", sample_rate: int = 44100) -> str`

- [x] **Step 1: Viết failing test cho `generate_sfx`**
- [x] **Step 2: Triển khai `sfx.py` với các thuật toán tổng hợp âm thanh chuyển cảnh**
- [x] **Step 3: Chạy test xác nhận PASS**
- [x] **Step 4: Commit**

---

### Task 3: Tích hợp Auto Scene Cut SFX vào Audio Merger (`autodub/media/audio.py`)

**Files:**
- Modify: `autodub/media/audio.py:535-620`
- Test: `tests/test_audio_merger.py`

**Interfaces:**
- Consumes: `scene_cuts: list[float] | None`, `auto_sfx_enabled: bool`, `sfx_preset: str`, `sfx_volume_db: float`
- Tự động hòa trộn âm thanh chuyển cảnh tại các điểm scene cuts hợp lệ.

- [x] **Step 1: Viết test cho `merge_segments` với SFX**
- [x] **Step 2: Cập nhật `merge_segments` trong `audio.py`**
- [x] **Step 3: Chạy test xác nhận PASS**
- [x] **Step 4: Commit**

---

### Task 4: Tích hợp Cấu hình, Pipeline, Editor & GUI

**Files:**
- Modify: `autodub/config.py`
- Modify: `autodub/pipeline.py`
- Modify: `autodub/editor.py`
- Modify: `autodub_gui/style_dialog.py`
- Modify: `autodub_gui/pages/settings_fields.py`

- [x] **Step 1: Thêm fields `auto_sfx_enabled`, `sfx_preset`, `sfx_volume_db`, `video_reframe_mode` vào Settings**
- [x] **Step 2: Tích hợp vào StyleDialog và Pipeline / Editor**
- [x] **Step 3: Chạy test suite xác nhận PASS**
- [x] **Step 4: Commit**

---

### Task 5: Full Regression Testing & Documentation

- [x] **Step 1: Chạy toàn bộ pytest suite (63+ core component tests PASS 100%)**
- [x] **Step 2: Cập nhật plan & verification report**
