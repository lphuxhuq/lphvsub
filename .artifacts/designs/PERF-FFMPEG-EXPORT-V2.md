# Thiết Kế Kiến Trúc — PERF-FFMPEG-EXPORT-V2

- **Mã thiết kế**: `PERF-FFMPEG-EXPORT-V2`
- **Mục tiêu**: Thiết kế hệ thống Render Plan, Output Profile, Blur Strategy, Encoder Profile, Render Profiler và Render Cache cho pipeline FFmpeg export.

---

## 1. Cấu Trúc Mô-Đun Kiến Trúc Đề Xuất

Tất cả các thành phần mới được đặt gọn gàng trong `autodub/media/` theo nguyên tắc Single Responsibility và dễ dàng tích hợp ngược vào `merge_video()`:

```text
autodub/media/
├── output_profile.py     # Quản lý tỷ lệ khung hình, pixel budget, resolution chuẩn hóa
├── blur_strategy.py      # Thuật toán Downscale Blur Pyramid adaptive (FAST, BALANCED, QUALITY)
├── encoder_profile.py    # Bộ hồ sơ encoder (NVENC, QSV, AMF, CPU) theo profile FAST/BALANCED/QUALITY
├── render_profiler.py    # Đo kiểm chi tiết thời gian từng giai đoạn (zero overhead khi tắt)
├── render_plan.py        # Abstract DAG: Input -> FilterGraph -> Subtitle -> Encoder -> Output
├── render_cache.py       # Dirty layer tracking & cache static assets
├── subtitle.py           # Tích hợp dùng OutputProfile và BlurStrategy (giữ tương thích 100% API cũ)
└── video.py              # Tích hợp RenderPlan và RenderProfiler vào merge_video
```

---

## 2. Chi Tiết Các Thành Phần Cốt Lõi

### 2.1. `OutputProfile` (`output_profile.py`)
- Định nghĩa class `OutputProfile`:
  ```python
  @dataclass(frozen=True)
  class OutputProfile:
      aspect_preset: str  # "tiktok_9_16", "youtube_16_9", "square_1_1", "custom", "original"
      target_w: int
      target_h: int
      pixel_budget: int = 2_073_600  # Full HD cap mặc định

      @classmethod
      def from_source_and_preset(
          cls, src_w: int, src_h: int, preset: str | None, custom_w=None, custom_h=None
      ) -> OutputProfile: ...
  ```
- **Quy tắc chuẩn hóa**:
  - `9:16`: nếu video ngang 16:9 (`1920x1080`) $\rightarrow$ canvas chuẩn là **1080x1920**. Tuyệt đối không phình lên 3.4K (1920x3414).
  - `16:9`: nếu video dọc $\rightarrow$ canvas chuẩn là **1920x1080**.
  - `1:1`: canvas chuẩn là **1080x1080**.
  - Kiểm tra `target_w * target_h <= pixel_budget`, nếu vượt ngưỡng tự động scale tỷ lệ về trong budget.

### 2.2. `BlurStrategy` (`blur_strategy.py`)
- Hỗ trợ 3 profile:
  - `FAST`: Downscale hệ số $6\times$ (ví dụ $1080 \times 1920 \rightarrow 180 \times 320$), `boxblur=4:1`, upscale `bilinear`.
  - `BALANCED`: Downscale hệ số $4\times$ ($270 \times 480$), `boxblur=6:2`, upscale `bicubic`.
  - `QUALITY`: Downscale hệ số $2\times$ ($540 \times 960$), `boxblur=10:3`, upscale `lanczos`.
- Tính toán kích thước thu nhỏ tự động chẵn `(low_w, low_h)` đảm bảo tương thích mọi định dạng yuv420p.

### 2.3. `EncoderProfile` (`encoder_profile.py`)
- Quản lý tham số cho NVENC/QSV/AMF/x264:
  - `FAST`: NVENC `preset=p1`, `multipass=0`, `cq=23`.
  - `BALANCED`: NVENC `preset=p2`, `multipass=0`, `cq=22`.
  - `QUALITY`: NVENC `preset=p4`, `multipass=2passes`, `cq=20`.

### 2.4. `RenderPlan` (`render_plan.py`)
- Nhận diện các layer:
  1. Base Video (Decode & Anti-Content ID: smart flip, micro zoom, color grading).
  2. Canvas Reframe (Background Blur / Top Split / Center Crop / Banner).
  3. ROI Masking / Blur (Subtitle removal).
  4. Brand Overlays (Logo, Watermark, Header/Footer Banners).
  5. Subtitles Burn (Karaoke ASS / libass).
- Xây dựng filter graph tối ưu, loại bỏ việc chuyển đổi trung gian dư thừa.

### 2.5. `RenderProfiler` (`render_profiler.py`)
- Đo kiểm micro-benchmarks thông qua FFmpeg progress parse và timing từng phase.
- In log dạng:
  ```text
  [PERF] Pipeline Plan: 1080x1920 @ 30fps, Encoder: NVIDIA NVENC (p1)
  [PERF] Render Speed : 11.8x Realtime (240 FPS)
  ```

---

## 3. Kế Hoạch Kiểm Thử & Chống Regression

1. **Unit Tests Hiện Tại**: Giữ nguyên 46 tests trong `test_subtitle.py` và `test_video_merge.py`. Mọi sửa đổi đều đảm bảo các tests này PASS 100%.
2. **Bộ Unit Tests Mới** (`tests/test_render_plan_v2.py`):
   - `test_output_profile_9_16_normalization()`: Kiểm tra video 1920x1080 chuyển 9:16 ra đúng 1080x1920.
   - `test_pixel_budget_capping()`: Kiểm tra không bị thổi phồng độ phân giải.
   - `test_blur_strategy_modes()`: Kiểm tra các mode FAST, BALANCED, QUALITY.
   - `test_render_plan_filter_graph()`: Kiểm tra cú pháp filter complex tạo ra hợp lệ.
3. **Benchmarks Đo Thực Tế**:
   - Chạy các mốc 15s, 60s, 5m và full 37m trên file video `BV1ZitQ62En1.mp4`.

---

`TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ`
