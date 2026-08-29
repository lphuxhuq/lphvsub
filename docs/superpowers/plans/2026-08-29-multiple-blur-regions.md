# Multiple Blur Regions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Nâng cấp tính năng tùy chọn và quản lý nhiều vùng làm mờ (Multiple Blur Regions) trong `StyleDialog` và GUI: quản lý danh sách từng vùng, xóa/chọn vùng cụ thể, phím tắt tạo nhanh các mẫu vùng che đáy/đỉnh/góc logo, và kiểm thử chuỗi đa vùng làm mờ.

**Architecture:** Mở rộng `_FrameCanvas` trong `style_dialog.py` với hỗ trợ chọn vùng, xóa theo chỉ số `remove_region(idx)` và thêm preset `add_preset_region()`; thiết kế lại giao diện nhóm `Che chữ trên hình` với `QListWidget` hiển thị danh sách vùng và nút bấm preset nhanh.

**Tech Stack:** Python 3.11, PySide6, Qt GUI Widgets, FFmpeg Filtergraph, Pytest.

## Global Constraints

- Vẫn giữ nguyên định dạng dữ liệu chuẩn hóa `0..1` (`x`, `y`, `w`, `h`) tương thích tuyệt đối với `build_filter_complex` và `pipeline.py`.
- Khi người dùng vẽ bằng chuột trên Canvas hoặc bấm thêm từ preset, danh sách vùng lập tức đồng bộ thời gian thực.
- Không làm ảnh hưởng đến tính năng phát video xem trước và di chuyển phụ đề.

---

### Task 1: Nâng cấp `_FrameCanvas` hỗ trợ quản lý nhiều vùng và Highlight vùng chọn

**Files:**
- Modify: `autodub_gui/style_dialog.py:110-260`
- Test: `tests/test_style_dialog.py`

**Interfaces:**
- `_FrameCanvas.remove_region(index: int)` -> `None`
- `_FrameCanvas.select_region(index: int | None)` -> `None`
- `_FrameCanvas.add_preset_region(preset_type: str)` -> `None`
- `_FrameCanvas.on_regions_changed = callback(regions: list[dict])`

- [ ] **Step 1: Triển khai các phương thức chọn, xóa và thêm preset vùng trong `_FrameCanvas`**
- [ ] **Step 2: Vẽ viền highlight nổi bật khi một vùng được chọn trên Canvas**

---

### Task 2: Thiết kế giao diện Quản lý nhiều vùng làm mờ trong `StyleDialog`

**Files:**
- Modify: `autodub_gui/style_dialog.py:640-700`

- [ ] **Step 1: Thêm hàng nút Mẫu vùng che nhanh (`+ Dải đáy`, `+ Dải đỉnh`, `+ Góc phải`, `+ Góc trái`)**
- [ ] **Step 2: Thêm danh sách `QListWidget` hiển thị `Vùng N: (x%, y%, w%, h%)` kèm nút xóa từng mục**
- [ ] **Step 3: Kết nối sự kiện nhấp chọn vùng trên danh sách để highlight trên Canvas**

---

### Task 3: Kiểm thử toàn diện

**Files:**
- Test: `tests/test_subtitle.py`
- Test: `tests/test_style_dialog.py`

- [ ] **Step 1: Viết test cho chuyển đổi và xuất nhiều vùng làm mờ**
- [ ] **Step 2: Chạy toàn bộ test suite xác nhận PASS 100%**
