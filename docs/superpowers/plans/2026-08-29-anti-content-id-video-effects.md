# Anti-Content ID Video Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Triển khai trọn bộ tính năng Xử lý Video Chống quét bản quyền / Reup (Smart Flip, Micro-zoom, Color Grading, Black border crop) trên toàn bộ hệ thống từ FFmpeg Filter Engine, Config, Pipeline đến GUI.

**Architecture:** Bổ sung các bộ lọc biến đổi video gốc trước khi dán layout, blur và phụ đề trong `build_filter_complex` ([subtitle.py](file:///D:/Project/lphvsub-main/autodub/media/subtitle.py)), tích hợp vào `Settings`, `DubRequest`, `merge_video` ([video.py](file:///D:/Project/lphvsub-main/autodub/media/video.py)), `pipeline.py`, `editor.py` và các form cài đặt / tạo dự án mới.

**Tech Stack:** Python 3.11, FFmpeg Filtergraph (hflip, scale, crop, eq, colorbalance, unsharp), PySide6, Pytest.

## Global Constraints

- Lật gương (`smart_flip`), phóng to (`micro_zoom`) và lọc màu (`color_filter`) PHẢI áp dụng cho luồng video gốc TRƯỚC bước dán phụ đề, logo và watermark để phụ đề và chữ tiếng Việt luôn đúng chiều, sắc nét 100%.
- Nếu không kích hoạt tính năng nào, không sinh thêm filter thừa để giữ nguyên tốc độ xử lý video.

---

### Task 1: Bộ Lọc FFmpeg Filtergraph Cho Anti-Content ID

**Files:**
- Modify: `autodub/media/subtitle.py`
- Modify: `autodub/media/video.py`
- Test: `tests/test_subtitle.py`

**Interfaces:**
- `build_filter_complex(..., smart_flip: bool = False, micro_zoom: bool = False, color_filter: str = "none")`

- [ ] **Step 1: Viết failing test cases cho smart_flip, micro_zoom và color_filter trong `tests/test_subtitle.py`**
- [ ] **Step 2: Triển khai các chuỗi bộ lọc Anti-Content ID trong `autodub/media/subtitle.py` và `autodub/media/video.py`**
- [ ] **Step 3: Chạy test xác nhận PASS**

---

### Task 2: Tích hợp Cấu hình, Pipeline và Editor

**Files:**
- Modify: `autodub/config.py`
- Modify: `autodub/pipeline.py`
- Modify: `autodub/editor.py`
- Test: `tests/test_video_merge.py`

- [ ] **Step 1: Thêm `smart_flip`, `micro_zoom`, `color_filter` vào `Settings` và `DubRequest`**
- [ ] **Step 2: Truyền các tham số qua `pipeline.py` và `editor.py` vào `merge_video`**
- [ ] **Step 3: Chạy test xác nhận PASS**

---

### Task 3: Tích hợp Giao diện Người dùng (GUI)

**Files:**
- Modify: `autodub_gui/pages/settings_fields.py`
- Modify: `autodub_gui/pages/new_project_steps.py`
- Modify: `autodub_gui/pages/new_project_page.py`

- [ ] **Step 1: Thêm nhóm `Chống quét bản quyền (Anti-Content ID)` vào `settings_fields.py` trong Thẻ Nâng cao**
- [ ] **Step 2: Bổ sung khối `Xử lý Video & Chống bản quyền` vào `VoiceStep` trong `new_project_steps.py`**
- [ ] **Step 3: Kết nối dữ liệu trong `new_project_page.py`**
- [ ] **Step 4: Chạy toàn bộ test suite xác nhận PASS 100%**
