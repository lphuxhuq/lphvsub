# Logo / Watermark Overlay Design Spec

> **Feature:** Tùy chọn chèn Logo / Watermark thương hiệu vào video xuất ra
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goal)

Cho phép người dùng chèn logo/watermark thương hiệu (.png trong suốt, .jpg, .webp) vào video xuất ra trong quá trình tạo dự án mới hoặc khi xuất lại từ Trình chỉnh sửa (Editor). Logo có thể tùy chỉnh linh hoạt vị trí (4 góc, ở giữa), tỷ lệ kích thước (% theo độ phân giải video), độ trong suốt (opacity) và khoảng cách lề (margin).

---

## 2. Kiến trúc & Thiết kế kỹ thuật

### 2.1. Tầng Xử lý Video (FFmpeg Filtergraph)

- **Module phụ trách**: `autodub/media/subtitle.py` (hàm `build_filter_complex`) và `autodub/media/video.py` (hàm `merge_video`).
- **Phương thức xử lý**:
  - Khi có `logo_path` hợp lệ trên đĩa:
    - Thêm `-i <logo_path>` vào lệnh `ffmpeg` hoặc đọc trực tiếp qua `movie='<logo_path>'` trong `filter_complex`.
    - Dùng bộ lọc `scale` để tự động co dãn logo theo tỷ lệ `%` chiều rộng video: `scale=w='min(iw,main_w*<logo_scale>)':h=-1`.
    - Dùng `format=rgba,colorchannelmixer=aa=<opacity>` để điều chỉnh độ mờ/trong suốt.
    - Dùng `overlay` để tính toán tọa độ theo `position` và `margin`:
      - `top_left`: `x=margin:y=margin`
      - `top_right`: `x=main_w-overlay_w-margin:y=margin`
      - `bottom_left`: `x=margin:y=main_h-overlay_h-margin`
      - `bottom_right`: `x=main_w-overlay_w-margin:y=main_h-overlay_h-margin`
      - `top_center`: `x=(main_w-overlay_w)/2:y=margin`
      - `bottom_center`: `x=(main_w-overlay_w)/2:y=main_h-overlay_h-margin`
  - Đảm bảo thứ tự vẽ: `[Nền aspect ratio] -> [Vùng làm mờ blur] -> [Logo Overlay] -> [Phụ đề Subtitles] -> [vout]`.

### 2.2. Tầng Cấu hình & Pipeline

- **`autodub/config.py`**:
  - `logo_path: str = ""` (Đường dẫn tệp hình ảnh)
  - `logo_position: str = "top_right"`
  - `logo_scale: float = 0.12` (12% chiều rộng video)
  - `logo_opacity: float = 0.85` (Độ mờ 85%)
  - `logo_margin: int = 24` (Pixel lề cách mép)
- **`autodub/pipeline.py` (`DubRequest`)**:
  - Bổ sung các trường `logo_path`, `logo_position`, `logo_scale`, `logo_opacity`, `logo_margin`.
  - Truyền các tùy chọn này sang `merge_video` ở Bước 7.

### 2.3. Tầng Giao diện Người dùng (GUI)

1. **Trang Cài đặt (`settings_fields.py`)**:
   - Thêm nhóm `"Logo & Watermark"` trong thẻ `TAB_ADVANCED`:
     - Tệp logo mặc định (`FILE`)
     - Vị trí (`COMBO`: 4 góc + 2 vị trí giữa)
     - Kích thước (`SLIDER`: 5% - 40%)
     - Độ mờ (`SLIDER`: 10% - 100%)
2. **Trình tạo dự án mới (`new_project_steps.py` - Bước 4: Giọng & Phụ đề)**:
   - Thêm khối CollapsibleSection `"Logo thương hiệu"`:
     - Nút chọn tệp ảnh logo (kèm nút xem trước / xóa tệp)
     - Chọn vị trí hiển thị
     - Thanh kéo độ mờ (Opacity)
3. **Trình chỉnh sửa (`editor_export.py` & `editor_page.py`)**:
   - Cho phép chọn/đổi logo khi xuất lại video hoàn chỉnh.

---

## 3. Kiểm thử & Tiêu chuẩn chất lượng (Testing)

- **Unit Tests**:
  - `test_filter_complex_with_logo_positions`: Kiểm tra chuỗi `-filter_complex` sinh ra đúng công thức cho tất cả các vị trí.
  - `test_merge_video_with_logo_and_subs`: Xác minh thứ tự overlay logo và burned subtitles không bị xung đột.
  - `test_invalid_logo_path_fallback`: Tệp logo không tồn tại thì tự động bỏ qua, không làm crash pipeline.
