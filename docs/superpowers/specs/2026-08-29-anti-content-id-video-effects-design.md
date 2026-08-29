# Anti-Content ID Video Effects Design Spec

> **Feature:** Bộ lọc Xử lý Video & Chống Quét Bản Quyền / Reup Tự Động (Smart Flip, Micro-Zoom, Color Grading, Auto Crop)
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goals)

Cung cấp bộ công cụ xử lý video chống Content ID và thuật toán quét reup (TikTok, YouTube, Facebook Reels) tự động, giúp video đăng lên đạt tương tác cao mà không bị bóp reach hoặc đánh gậy bản quyền:
1. **Lật gương thông minh (Smart Flip / Mirror)**: Lật ngang video gốc (`hflip`) nhưng **giữ nguyên 100% logo thương hiệu, watermark và phụ đề tiếng Việt không bị lật ngược**.
2. **Zoom động nhẹ & Chuyển động Camera (Micro-Zoom & Drift)**: Phóng to nhẹ ($103\%$) kết hợp chuyển động camera lướt vi mô theo thời gian thực (Micro Ken Burns).
3. **Bộ lọc màu điện ảnh (Cinematic Color Grading)**: 5 preset màu phim chuyên nghiệp (`cinematic_warm`, `teal_orange`, `vintage`, `moody_dark`, `clean_film`).
4. **Tự động cắt viền đen (Auto Black Border Crop)**: Tự động loại bỏ viền đen thừa trên/dưới hoặc 2 bên trước khi căn chỉnh tỷ lệ khung hình.

---

## 2. Thiết kế Kỹ thuật (Technical Design)

### 2.1. Thứ tự Áp dụng trong FFmpeg Filtergraph (`autodub/media/subtitle.py`)

Để đảm bảo hiệu quả chống quét bản quyền tối đa mà không làm ảnh hưởng đến thẩm mỹ phụ đề:
```
[0:v] (Video gốc)
  │
  ├──> 1. Auto Black Border Crop (Cắt viền đen thừa)
  │
  ├──> 2. Smart Flip (hflip - lật ngang video nền)
  │
  ├──> 3. Micro-Zoom & Drift (Phóng to 103% & lướt vi mô)
  │
  ├──> 4. Cinematic Color Grading (Bộ lọc màu điện ảnh)
  │
  ├──> 5. Aspect Ratio Pad ([vasp] - Khung hình 9:16 / 16:9 / 1:1)
  │
  ├──> 6. Blur Regions (Che phụ đề cũ)
  │
  ├──> 7. Logo & Moving Watermark (Chèn watermark bản quyền chuẩn)
  │
  └──> 8. Subtitles ([vout] - Ghi phụ đề tiếng Việt chuẩn, không bị lật)
```

### 2.2. Chi tiết các bộ lọc FFmpeg

1. **Smart Flip**:
   ```
   hflip
   ```
2. **Micro-Zoom & Camera Drift**:
   ```
   scale=1.03*iw:1.03*ih,crop=iw/1.03:ih/1.03:(iw-ow)/2+sin(t*0.6)*6:(ih-oh)/2+cos(t*0.5)*6
   ```
3. **Color Grading Presets**:
   - `cinematic_warm`: `colorbalance=rs=0.08:gs=0.02:bs=-0.06:rm=0.06:gm=0.02:bm=-0.04,eq=contrast=1.06:saturation=1.12`
   - `teal_orange`: `colorbalance=rs=0.12:gs=0.02:bs=-0.08:rh=-0.08:gh=0.04:bh=0.10,eq=contrast=1.10:saturation=1.15`
   - `vintage`: `eq=contrast=0.96:brightness=0.02:saturation=0.86,colorbalance=rs=0.06:gs=0.03:bs=-0.04`
   - `moody_dark`: `eq=contrast=1.14:brightness=-0.03:saturation=0.92,colorbalance=rs=-0.02:gs=-0.02:bs=0.04`
   - `clean_film`: `unsharp=5:5:0.8:5:5:0.0,eq=contrast=1.04:saturation=1.08`

### 2.3. Cấu hình & Giao diện Người dùng

- **`Settings` & `DubRequest`**:
  - `smart_flip: bool = False`
  - `micro_zoom: bool = False`
  - `color_filter: str = "none"` (`none`, `cinematic_warm`, `teal_orange`, `vintage`, `moody_dark`, `clean_film`)
- **`settings_fields.py`**: Thêm nhóm **`Chống quét bản quyền (Anti-Content ID)`** vào Thẻ Nâng cao.
- **`new_project_steps.py` (Bước 4)**: Thêm khối mở rộng **`Xử lý Video & Chống bản quyền`** cho phép bật lật gương, zoom động và chọn bộ lọc màu.
