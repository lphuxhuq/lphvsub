# Multiple Blur Regions Management Design Spec

> **Feature:** Quản lý và tùy chọn nhiều vùng làm mờ (Multiple Blur Regions Management)
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goal)

Nâng cấp khả năng quản lý và thao tác nhiều vùng làm mờ (Blur Regions) trên video trong `StyleDialog` và quy trình tạo dự án:
- Thêm danh sách trực quan hiển thị tất cả các vùng làm mờ hiện có (`Vùng 1`, `Vùng 2`, `Vùng 3`...).
- Cho phép người dùng chọn và xóa từng vùng cụ thể (không chỉ mỗi nút `Xóa vùng cuối` hoặc `Xóa tất cả`).
- Thêm các mẫu vùng che nhanh (Quick Presets):
  - **Dải che phụ đề đáy** (Toàn bộ đáy màn hình: `y=82%..98%`, `w=100%`)
  - **Dải che phụ đề đỉnh** (Đỉnh màn hình: `y=3%..16%`, `w=100%`)
  - **Vùng che góc trên bên phải** (Che logo kênh gốc)
  - **Vùng che góc trên bên trái**
- Tương thích 100% với FFmpeg Filtergraph (đã hỗ trợ chuỗi `split -> crop -> boxblur -> overlay` tuần hoàn đa vùng).

---

## 2. Thiết kế Kỹ thuật

### 2.1. Nâng cấp `_FrameCanvas` trong `autodub_gui/style_dialog.py`
- Hỗ trợ `selected_index: int | None` để đánh dấu viền nổi bật (màu vàng/xanh sáng) cho vùng đang được chọn trong danh sách.
- Phương thức `remove_region(index: int)` để xóa đúng vùng mong muốn.
- Phương thức `add_normalized_region(dict)` để thêm vùng từ mẫu preset.
- Callback `on_regions_changed` phát tín hiệu cập nhật danh sách vùng sang giao diện panel bên phải.

### 2.2. Nâng cấp Panel "Che chữ trên hình" trong `StyleDialog`
- Hiển thị nhãn số lượng: `Đang có N vùng làm mờ`.
- Hộp danh sách `QListWidget` hiển thị danh sách vùng kèm nút Xóa [✕] cho từng vùng.
- Menu/Nút chọn Mẫu nhanh (`+ Dải đáy`, `+ Dải đỉnh`, `+ Góc trên phải`, `+ Góc trên trái`).
- Các nút thao tác: `Dò tự động`, `Xóa vùng chọn`, `Xóa tất cả`.

---

## 3. Kế hoạch kiểm thử (Testing)
- `tests/test_subtitle.py`: Kiểm tra filtergraph với 3+ vùng làm mờ đồng thời.
- `tests/test_style_dialog.py`: Kiểm tra logic thêm, xóa, preset của multiple blur regions.
