# Tối Ưu Tốc Độ Ghi Phụ Đề & Xuất Video Dài Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tối ưu hóa tốc độ ghi phụ đề (cả phụ đề chuẩn lẫn Karaoke đổi màu/nhấp nháy) và tăng tốc độ xuất video dài (15m - 2h) trên các tỷ lệ khung hình (16:9 gốc, 9:16 TikTok có nền mờ nghệ thuật) bằng cách tích hợp RenderPlan v2, Downscale Blur Pyramid, Filtergraph Multi-threading và tối ưu hóa Libass event stream.

**Architecture:** Sử dụng `RenderPlan` và `BlurStrategy` để tự động hóa việc downscale nền mờ $6\times$ (giảm $36\times$ số phép tính boxblur); mở khóa toàn bộ nhân CPU cho libass bằng `-filter_complex_threads 0`; tinh gọn chuỗi dialogue events trong `ass_karaoke.py` để triệt tiêu việc libass liên tục xóa/tạo lại vector glyph cache trên timeline dài; tối ưu bước ghi đĩa cuối tệp MP4.

**Tech Stack:** Python 3.11, FFmpeg 8.0, NVIDIA NVENC / CPU libx264, libass / Subtitles filter, PySide6, Pytest.

## Global Constraints

- Phải đảm bảo 100% test suite hiện có trong `tests/test_subtitle.py`, `tests/test_video_merge.py`, `tests/test_ass_karaoke.py`, `tests/test_render_plan_v2.py` tiếp tục PASS (Zero Regression).
- Giữ nguyên tương thích ngược (backward compatibility) cho toàn bộ API của hàm `merge_video()`.
- Giữ nguyên độ sắc nét và tính thẩm mỹ của phụ đề và nền mờ nghệ thuật.

---

### Task 1: FFmpeg Filtergraph Multi-Threading & Tối Ưu Ghi Tệp (`autodub/media/video.py`)

**Files:**
- Modify: `autodub/media/video.py:370-435`
- Test: `tests/test_video_merge.py`

**Interfaces:**
- Consumes: `merge_video(...)` trong `autodub/media/video.py`
- Produces: Tham số dòng lệnh FFmpeg chứa `-filter_complex_threads 0`, xử lý `faststart` linh hoạt.

- [ ] **Step 1: Viết test kiểm tra `-filter_complex_threads 0` và `faststart` trong `tests/test_video_merge.py`**
- [ ] **Step 2: Chạy pytest để xác nhận test phát hiện thiếu `-filter_complex_threads 0`**
- [ ] **Step 3: Cập nhật `merge_video()` trong `autodub/media/video.py` để thêm `-filter_complex_threads 0` khi có `filter_complex`**
- [ ] **Step 4: Chạy lại `tests/test_video_merge.py` xác nhận tất cả test pass**
- [ ] **Step 5: Git commit cho Task 1**

---

### Task 2: Tích Hợp Downscale Blur Pyramid & Tối Ưu Khung Hình (`autodub/media/subtitle.py`)

**Files:**
- Modify: `autodub/media/subtitle.py:390-550`
- Test: `tests/test_subtitle.py`

**Interfaces:**
- Consumes: `BlurStrategy` từ `autodub/media/blur_strategy.py`, `OutputProfile` từ `autodub/media/output_profile.py`
- Produces: `build_filter_complex(...)` sinh chuỗi filter graph downscale blur nhẹ hơn $36\times$, khống chế pixel budget cho 9:16.

- [ ] **Step 1: Viết test kiểm tra `build_filter_complex` sử dụng Downscale Blur Pyramid khi đổi tỷ lệ 9:16**
- [ ] **Step 2: Chạy pytest kiểm tra test thất bại trước khi cập nhật**
- [ ] **Step 3: Tích hợp `BlurStrategy` và `OutputProfile` vào `build_filter_complex()` trong `autodub/media/subtitle.py`**
- [ ] **Step 4: Chạy `tests/test_subtitle.py` xác nhận 100% test pass (cả test mới và test cũ)**
- [ ] **Step 5: Git commit cho Task 2**

---

### Task 3: Tối Ưu Hóa Libass Karaoke Event Stream (`autodub/text/ass_karaoke.py`)

**Files:**
- Modify: `autodub/text/ass_karaoke.py:172-278`
- Test: `tests/test_ass_karaoke.py`

**Interfaces:**
- Consumes: `_effect_prefix(effect)`, `render_karaoke_events(...)`
- Produces: Dialogue events ASS nhẹ nhàng, không gây giật lag glyph cache libass trên timeline dài hàng nghìn câu.

- [ ] **Step 1: Viết test kiểm tra định dạng effect và timestamp an toàn, không có overlap micro-giây trong `tests/test_ass_karaoke.py`**
- [ ] **Step 2: Cập nhật `_effect_prefix()` và `render_karaoke_events()` trong `autodub/text/ass_karaoke.py`**
- [ ] **Step 3: Chạy `tests/test_ass_karaoke.py` xác nhận 17/17 test pass**
- [ ] **Step 4: Git commit cho Task 3**

---

### Task 4: Kiểm Thử Toàn Diện & Đo Lường Hiệu Năng (Full Verification & Benchmark)

**Files:**
- Test: Toàn bộ test suite liên quan (`tests/test_video_merge.py`, `tests/test_subtitle.py`, `tests/test_ass_karaoke.py`, `tests/test_render_plan_v2.py`)
- Script: `scripts/benchmark_export_speed.py`

- [ ] **Step 1: Chạy toàn bộ pytest liên quan để đảm bảo Zero Regression**
- [ ] **Step 2: Chạy benchmark so sánh tốc độ export video trước và sau khi tối ưu**
- [ ] **Step 3: Ghi nhận kết quả tốc độ thực tế vào báo cáo walkthrough**
