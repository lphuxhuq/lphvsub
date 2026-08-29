# Fix Plan: Watermark & Logo Disappearing on Video Export

## 1. Root Cause Analysis (Nguyên nhân gốc rễ)

Khi người dùng cấu hình Logo và Watermark trong **Tạo dự án mới (New Project Wizard)** hoặc **Trình chỉnh sửa (Editor/Style Dialog)**, khi bấm **"Xuất video"**, logo và watermark không xuất hiện trên video vì 4 vị trí bị đứt gãy luồng dữ liệu:

1. **Đứt gãy tại `pipeline.py` (`export_state` & `_stop_for_export`)**:
   - Khi Wizard chạy với `defer_export=True` (chờ người dùng xem trước và bấm Xuất video), `export_state` chỉ lưu `video_path`, `subtitle_mode`, `blur_regions` mà bỏ quên toàn bộ các trường `logo_*`, `watermark_*`, `smart_flip`, `micro_zoom`, `color_filter`, `aspect_preset`.
   - Khi hàm `_export_phase()` chạy lúc người dùng bấm Xuất video, `DubRequest` được dựng lại từ `export_state` bị gán `logo_path=None`, `watermark_text=None`, dẫn đến fallback về chuỗi rỗng `""`.

2. **Lệch tham số positional tại `workers.py` và `editor.py` (`RebuildWorker` / `rebuild_output`)**:
   - Trong `editor.py`, hàm `rebuild_output()` đặt tham số `reporter` ở cuối sau `logo_path`.
   - Trong `workers.py`, `RebuildWorker` gọi `rebuild_output(..., subtitle_style, reporter)` khiến biến `reporter` (đối tượng `ProgressReporter`) bị truyền nhầm vào tham số `logo_path`.

3. **Lưu trữ thiếu trong `editor_export.py` (`_save_render_opts`)**:
   - Khi người dùng mở `StyleDialog` trong màn hình Editor để chọn logo/watermark, `_save_render_opts()` lưu vào `.env` nhưng không cập nhật `logo_*` và `watermark_*` vào `render_opts.json` của dự án.

4. **Cú pháp bộ lọc FFmpeg overlay trong `subtitle.py`**:
   - Dòng `overlay=x='{ox}':y='{oy}'` có dấu nháy đơn lồng nhau trong filtergraph khiến FFmpeg có thể gặp lỗi parse biểu thức tọa độ toán học (như `bounce` hoặc `main_w-overlay_w-24`). Cần chuẩn hóa thành `overlay={ox}:{oy}`.

---

## 2. Proposed Changes (Kế hoạch sửa đổi chi tiết)

### 2.1. `autodub/pipeline.py`
- Bổ sung đầy đủ các trường `logo_*`, `watermark_*`, `smart_flip`, `micro_zoom`, `color_filter`, `aspect_preset` vào `export_state` trong `_run_pipeline()`.
- Lưu các trường này vào `render_opts.json` trong `_stop_for_export()`.
- Khôi phục đầy đủ các trường này khi dựng lại `DubRequest` trong `_export_phase()`.

### 2.2. `autodub/editor.py` & `autodub_gui/workers.py`
- Chuyển `logo_path`, `logo_position`, `logo_scale`, `logo_opacity`, `logo_margin`, `logo_motion`, `watermark_*`, `smart_flip`, `micro_zoom`, `color_filter`, `aspect_preset` và `reporter` trong `rebuild_output()` và `rebuild_subtitles()` thành keyword-only arguments (`*, ...`).
- Cập nhật `RebuildWorker` và `SubtitleWorker` truyền `reporter=reporter` an toàn, đọc trực tiếp các tùy chọn render từ `render_opts.json`.

### 2.3. `autodub_gui/pages/editor_export.py`
- Lưu đầy đủ `logo_*`, `watermark_*` vào `render_opts.json` khi người dùng chỉnh sửa trong `StyleDialog`.
- Load lại đúng các trường này khi mở lại dự án trong Editor.

### 2.4. `autodub/media/subtitle.py` & `autodub/media/video.py`
- Chuẩn hóa cú pháp overlay: `overlay={ox}:{oy}`.
- Đảm bảo kiểm tra sự tồn tại của file `logo_path` (`os.path.isfile(logo_path)`), nếu file bị xóa/không tồn tại thì log warning và bỏ qua thay vì làm hỏng quá trình xuất video.

---

## 3. Verification Plan (Kế hoạch kiểm thử)

1. **Unit Tests mới**:
   - `test_export_state_preserves_logo_and_watermark_in_pipeline`: Kiểm tra `export_state` và `DubRequest` giữ nguyên vẹn 100% các trường logo/watermark qua các phase.
   - `test_rebuild_output_with_logo_and_watermark`: Kiểm tra `rebuild_output` và `RebuildWorker` gọi `merge_video` với đầy đủ `logo_path`, `watermark_text` từ `render_opts.json`.
   - `test_editor_export_saves_logo_and_watermark_opts`: Kiểm tra `editor_export.py` lưu và nạp đúng `logo_options` / `watermark_options`.
2. **Regression Testing**:
   - Chạy toàn bộ 953+ pytest tests đảm bảo 100% PASSED.
