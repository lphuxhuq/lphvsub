# Reverse Engineering Report: Hardsub Masking & Detection Architecture

## 1. Existing `blur_regions` Data Model & Schema

In the LPHVSub codebase, `blur_regions` is a list of dictionary objects representing rectangular areas to be blurred on the video frame.

### Schema Fields:
```python
{
    "x": float,       # Tọa độ X góc trên-trái chuẩn hóa [0.0 .. 1.0]
    "y": float,       # Tọa độ Y góc trên-trái chuẩn hóa [0.0 .. 1.0]
    "w": float,       # Chiều rộng hình chữ nhật chuẩn hóa [0.0 .. 1.0]
    "h": float,       # Chiều cao hình chữ nhật chuẩn hóa [0.0 .. 1.0]
    "t_start": float, # (Tùy chọn) Thời điểm bắt đầu làm mờ (giây, float)
    "t_end": float,   # (Tùy chọn) Thời điểm kết thúc làm mờ (giây, float)
}
```

### Coordinate & Pixel Conversion (`autodub/media/subtitle.py`):
- Hàm `_to_pixels(region: dict, video_w: int, video_h: int) -> tuple[int, int, int, int]`:
  - `x = int(round(region["x"] * video_w))`
  - `y = int(round(region["y"] * video_h))`
  - `w = int(round(region["w"] * video_w))`
  - `h = int(round(region["h"] * video_h))`
  - Đảm bảo `w` và `h` là số chẵn (`w - (w % 2)`) để tương thích với bộ giải mã màu `yuv420p` của FFmpeg.

---

## 2. Video Rendering & FFmpeg Filter Complex

In `autodub/media/subtitle.py` (`build_filter_complex`):
- Đối với từng vùng `blur_region` thứ $i$:
  - Luồng video được tách (`split`) thành nhánh gốc và nhánh cắt (`crop=w:h:x:y`).
  - Áp dụng bộ lọc `boxblur` / `avgblur` qua `blur_filter(w, h)`.
  - Dán (`overlay`) trở lại luồng video tại vị trí `x:y`.
  - Nếu có `t_start` và `t_end`, tự động kích hoạt điều kiện thời gian: `overlay=x:y:enable='between(t,t_start,t_end)'`.
  - Phụ đề dịch mới (SRT/ASS) được vẽ đè lên trên cùng sau các lớp làm mờ (`subtitles=...`).

---

## 3. Retiming & Video Speed Scaling (`autodub/media/retime.py`)

- Khi video bị làm chậm/tăng tốc (`settings.video_speed`):
  - Hàm `rescale_blur_regions(blur_regions: list[dict], scale: float) -> list[dict]` tự động nhân tỷ lệ `scale` vào `t_start` và `t_end`. Các vùng không có mốc thời gian tĩnh được giữ nguyên.

---

## 4. Pipeline & Persistence Architecture

- **`DubRequest` (`autodub/pipeline.py`):** Chứa trường `blur_regions: list[dict]` và `auto_mask_hardsub: bool`.
- **`Settings` (`autodub/config.py`):** `blur_regions: str` (chuỗi JSON), `auto_mask_hardsub: bool`.
- **`render_opts.json` (`autodub/editor.py`):** Lưu trữ persistent các vùng làm mờ theo từng thư mục dự án (`opts["blur_regions"]`).

---

## 5. UI / GUI Interaction

- **`StyleDialog` (`autodub_gui/style_dialog.py`):**
  - Sử dụng `_FrameCanvas` với `normalized_regions()` và `set_rects_from_normalized(regions)`.
  - Nút bấm `btn_auto_detect` kích hoạt quét video trong nền hoặc đồng bộ để đổ danh sách hình chữ nhật lên canvas xem trước.

---

## 6. Available Dependencies

- **Python Standard Library** (os, subprocess, json, dataclasses, typing, math).
- **NumPy** (v2.4.6) - Xử lý mảng và ma trận ảnh.
- **SciPy** (v1.17.1) - Xử lý gradient, Sobel, nhãn liên thông `ndimage`.
- **OpenCV / cv2** (v5.0.0) - Sẵn sàng cho trích xuất và xử lý hình thái học.
- **PIL** (v12.3.0) & **PySide6** (v6.11.1).
- **FFmpeg / FFprobe** - Có sẵn trong PATH hệ thống.
