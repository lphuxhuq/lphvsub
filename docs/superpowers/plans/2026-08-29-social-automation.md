# Social Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây dựng hệ thống Tự động hóa & Phân phối Đa nền tảng gồm: Bộ tạo Thumbnail tự động bắt mắt (Auto High-CTR Thumbnail), Gói xuất bản đa nền tảng (Social Publishing Bundle), và công cụ Hàng đợi xuất bản hàng loạt.

**Architecture:** Tạo module `autodub/media/thumbnail.py` (trích xuất frame và vẽ typography thumbnail chuyên nghiệp), tích hợp vào `autodub/pipeline.py` ở Step 8, mở rộng `autodub/content/generator.py` đóng gói thư mục `publish/`, và nâng cấp giao diện Editor/Export với widget xem trước Thumbnail và các nút 1-Click Copy đăng bài.

**Tech Stack:** Python 3.11, Pillow (PIL), FFmpeg, PySide6, Pytest.

## Global Constraints

- Sử dụng font đi kèm trong `fonts/` để hiển thị tiếng Việt có dấu hoàn hảo trên Thumbnail.
- Nếu video không tạo được frame thật, sử dụng frame placeholder tiêu chuẩn.
- Đảm bảo hiệu năng nhanh chóng (quá trình sinh thumbnail < 1 giây).

---

### Task 1: Module Sinh Thumbnail Bắt Mắt Tự Động (`autodub/media/thumbnail.py`)

**Files:**
- Create: `autodub/media/thumbnail.py`
- Test: `tests/test_thumbnail.py`

**Interfaces:**
- `generate_high_ctr_thumbnail(video_path: str, title: str, output_path: str, aspect: str = "16:9") -> str`

- [ ] **Step 1: Viết test cases kiểm tra module tạo thumbnail trong `tests/test_thumbnail.py`**
- [ ] **Step 2: Triển khai logic trích xuất frame tối ưu và vẽ đồ họa thumbnail trong `autodub/media/thumbnail.py`**
- [ ] **Step 3: Chạy test xác nhận PASS**

---

### Task 2: Đóng Gói Xuất Bản Đa Nền Tảng Trong Pipeline

**Files:**
- Modify: `autodub/content/generator.py`
- Modify: `autodub/pipeline.py`
- Test: `tests/test_content_generator.py`

- [ ] **Step 1: Thêm hàm tạo gói xuất bản `build_social_publishing_package` trong `generator.py`**
- [ ] **Step 2: Tích hợp sinh Thumbnail và gói xuất bản vào Step 8 của `pipeline.py`**
- [ ] **Step 3: Chạy test xác nhận PASS**

---

### Task 3: Giao Diện Xem Trước Thumbnail & 1-Click Copy Đăng Bài (GUI)

**Files:**
- Modify: `autodub_gui/pages/editor_export.py`

- [ ] **Step 1: Thêm khung hiển thị Thumbnail và các nút sao chép nhanh Tiêu đề, Mô tả, Hashtag trong trang Xuất bản**
- [ ] **Step 2: Chạy toàn bộ test suites xác nhận PASS 100%**
