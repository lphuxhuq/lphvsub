# Integrated Logo & Watermark in StyleDialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuyển và tích hợp trọn bộ cấu hình cùng chức năng xem trước trực quan của Logo thương hiệu và Watermark chữ chìm vào trong hộp thoại `StyleDialog` ("Phụ đề & che chữ").

**Architecture:**
- Nâng cấp `_FrameCanvas` trong `style_dialog.py` hỗ trợ vẽ trực tiếp Logo và Watermark text với độ mờ và vị trí tương ứng.
- Nâng cấp `StyleDialog` sử dụng `QTabWidget` gồm 3 tab: `Kiểu chữ`, `Vùng che (Blur)`, `Logo & Watermark`.
- Cung cấp các phương thức `logo_options()` và `watermark_options()` trên `StyleDialog`.
- Đồng bộ dữ liệu trong `new_project_page.py`, `editor_export.py` và `batch_page.py`.

---

### Task 1: Nâng cấp `_FrameCanvas` và `StyleDialog` trong `autodub_gui/style_dialog.py`

**Files:**
- Modify: `autodub_gui/style_dialog.py`
- Test: `tests/test_style_dialog.py`

- [ ] **Step 1: Cập nhật `_FrameCanvas` hỗ trợ `set_logo_options` và `set_watermark_options` và vẽ preview trong `paintEvent`**
- [ ] **Step 2: Xây dựng tab `Logo & Watermark` với đầy đủ các trường cấu hình trong `StyleDialog`**
- [ ] **Step 3: Viết test cases kiểm tra trong `tests/test_style_dialog.py`**
- [ ] **Step 4: Chạy test xác nhận PASS**

---

### Task 2: Tích hợp và Đồng bộ với các trang Wizard, Editor và Batch

**Files:**
- Modify: `autodub_gui/pages/editor_export.py`
- Modify: `autodub_gui/pages/new_project_page.py`
- Modify: `autodub_gui/pages/batch_page.py`

- [ ] **Step 1: Truyền và nhận `logo_options` / `watermark_options` khi mở `StyleDialog` trong `editor_export.py`**
- [ ] **Step 2: Truyền và nhận `logo_options` / `watermark_options` trong `new_project_page.py` và `batch_page.py`**
- [ ] **Step 3: Chạy toàn bộ test suites xác nhận PASS 100%**
