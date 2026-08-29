# Dynamic Moving Watermark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm tính năng Watermark chìm di chuyển / chạy xung quanh khung hình video (Text Watermark & Logo Image Watermark với quỹ đạo nảy 2D mượt mà) để bảo vệ bản quyền, chống reup trên toàn bộ hệ thống từ FFmpeg Filter Engine, Pipeline, Cài đặt đến Giao diện Tạo dự án mới.

**Architecture:** Bổ sung bộ lọc `drawtext` / `overlay` với biểu thức tọa độ tuần hoàn thời gian thực ($x(t), y(t)$ theo hàm `mod` và `abs`) trong `build_filter_complex`, tích hợp các tham số watermark vào `Settings`, `DubRequest`, `merge_video`, `pipeline.py`, `editor.py` và các widget giao diện trong `autodub_gui`.

**Tech Stack:** Python 3.11, PySide6, FFmpeg Filtergraph (drawtext, overlay expressions), Pytest.

## Global Constraints

- Watermark chìm chuyển động phải nằm dưới phụ đề (`subtitles=...`) để không bao giờ che đè chữ phụ đề.
- Nếu `watermark_text` rỗng và không có logo chuyển động, hệ thống không sinh thêm filter thừa để giữ nguyên tốc độ muxing.
- Tốc độ di chuyển và độ mờ phải an toàn, mượt mà trên mọi độ phân giải.

---

### Task 1: Xây dựng biểu thức FFmpeg Filtergraph cho Watermark Chìm Chạy Quanh Video

**Files:**
- Modify: `autodub/media/subtitle.py`
- Modify: `autodub/media/video.py`
- Test: `tests/test_subtitle.py`

**Interfaces:**
- `build_filter_complex(..., watermark_text: str | None, watermark_opacity: float, watermark_font_size: int, watermark_color: str, watermark_speed: int, watermark_motion: str)` -> `str | None`

- [ ] **Step 1: Viết failing test cho moving text watermark trong `tests/test_subtitle.py`**
- [ ] **Step 2: Chạy test xác nhận FAIL**
- [ ] **Step 3: Triển khai logic tính tọa độ nảy và chuỗi filter `drawtext` / moving `overlay` trong `autodub/media/subtitle.py` và `autodub/media/video.py`**
- [ ] **Step 4: Chạy test xác nhận PASS**

---

### Task 2: Tích hợp Cấu hình, Pipeline và Editor

**Files:**
- Modify: `autodub/config.py`
- Modify: `autodub/pipeline.py`
- Modify: `autodub/editor.py`
- Test: `tests/test_editor.py`

- [ ] **Step 1: Thêm các trường cấu hình watermark vào `Settings` và `DubRequest`**
- [ ] **Step 2: Chuyển tiếp các tham số vào `merge_video` trong `pipeline.py` và `editor.py`**
- [ ] **Step 3: Chạy test xác nhận PASS**

---

### Task 3: Tích hợp Giao diện Người dùng (GUI)

**Files:**
- Modify: `autodub_gui/pages/settings_fields.py`
- Modify: `autodub_gui/pages/new_project_steps.py`
- Modify: `autodub_gui/pages/new_project_page.py`

- [ ] **Step 1: Thêm nhóm Watermark Chìm vào `settings_fields.py` trong Thẻ Nâng cao**
- [ ] **Step 2: Bổ sung widget Watermark Chữ Chìm trong `VoiceStep` của `new_project_steps.py`**
- [ ] **Step 3: Kết nối dữ liệu trong `new_project_page.py`**
- [ ] **Step 4: Chạy toàn bộ test suite xác nhận PASS 100%**
