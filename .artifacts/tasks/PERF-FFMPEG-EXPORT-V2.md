# Kế Hoạch Chia Task — PERF-FFMPEG-EXPORT-V2

- **Mã kế hoạch**: `PERF-FFMPEG-EXPORT-V2`
- **Mục tiêu**: Chia nhỏ việc hiện thực hóa Render Plan và tối ưu pipeline FFmpeg thành các Unit độc lập, an toàn và dễ nghiệm thu.

---

## 1. Dependency Graph

```text
TASK-001 (OutputProfile & Resolution Normalization)
   │
   ▼
TASK-002 (BlurStrategy & Downscale Pyramid Engine)
   │
   ▼
TASK-003 (EncoderProfile & Hardware Acceleration)
   │
   ▼
TASK-004 (RenderProfiler & Performance Tracker)
   │
   ▼
TASK-005 (RenderPlan & Subtitle/Video Integration)
   │
   ▼
TASK-006 (Comprehensive Tests, Regression & Multi-tier Benchmarks)
```

---

## 2. Danh Sách Unit Thực Hiện

### TASK-001 — OutputProfile & Pixel Budget Engine
- **Mục tiêu**: Tạo `autodub/media/output_profile.py` quản lý toàn bộ tính toán resolution và tỷ lệ khung hình. Đảm bảo 9:16 = 1080x1920, 16:9 = 1920x1080, 1:1 = 1080x1080, pixel budget $\le$ 2.073.600 px.
- **File sửa/tạo mới**: `autodub/media/output_profile.py`, `tests/test_output_profile.py`.
- **Acceptance Criteria**: Chuyển đổi từ 1920x1080 sang 9:16 trả về đúng (1080, 1920). Vượt pixel budget tự động clamp an toàn.

### TASK-002 — BlurStrategy & Adaptive Downscale Blur Engine
- **Mục tiêu**: Tạo `autodub/media/blur_strategy.py` cung cấp các profile `FAST`, `BALANCED`, `QUALITY`. Tự động tính toán downscale ratio và bán kính blur tương ứng.
- **File sửa/tạo mới**: `autodub/media/blur_strategy.py`, `tests/test_blur_strategy.py`.
- **Acceptance Criteria**: Sinh chuỗi filter graph làm mờ nền downscale -> blur -> upscale bilinear/bicubic chính xác. Không nghẽn CPU Full-HD.

### TASK-003 — EncoderProfile & Hardware Throughput Optimization
- **Mục tiêu**: Tạo `autodub/media/encoder_profile.py` chuẩn hóa các cấu hình phần cứng cho NVIDIA NVENC, Intel QSV, AMD AMF và libx264.
- **File sửa/tạo mới**: `autodub/media/encoder_profile.py`, `tests/test_encoder_profile.py`.
- **Acceptance Criteria**: Hỗ trợ linh hoạt các preset phần cứng theo profile FAST/BALANCED/QUALITY mà không hard-code cứng ngắc.

### TASK-004 — RenderProfiler & Performance Diagnostics
- **Mục tiêu**: Tạo `autodub/media/render_profiler.py` để bóc tách thời gian chi tiết các phase (Decode, Background, Subtitle, Encode, Mux, Speed).
- **File sửa/tạo mới**: `autodub/media/render_profiler.py`, `tests/test_render_profiler.py`.
- **Acceptance Criteria**: Log chi tiết định dạng `[PERF]` khi bật cờ profiler, hoàn toàn zero-overhead khi tắt.

### TASK-005 — RenderPlan Pipeline Integration
- **Mục tiêu**: Tạo `autodub/media/render_plan.py` và tích hợp trơn tru vào `autodub/media/subtitle.py` cùng `autodub/media/video.py`.
- **File sửa/tạo mới**: `autodub/media/render_plan.py`, `autodub/media/subtitle.py`, `autodub/media/video.py`.
- **Acceptance Criteria**: `merge_video()` và `build_filter_complex()` sử dụng RenderPlan mượt mà, backward-compatible 100% với toàn bộ codebase hiện tại.

### TASK-006 — Comprehensive Tests & Production Benchmark Verification
- **Mục tiêu**: Chạy kiểm tra toàn diện 46/46 unit tests cũ + các unit tests mới. Chạy benchmark thực tế trên video người dùng (15s, 60s, 5m, 37m).
- **File tạo**: `tests/test_render_plan_v2.py`, `docs/perf-ffmpeg-export-v2.md`.
- **Acceptance Criteria**: 100% tests pass. Benchmark thực tế đạt $\ge$ 10x – 12x Realtime. Xuất video 37 phút trong $\le$ 4-5 phút.

---

`TRẠNG THÁI: CHỜ DUYỆT TASK`
