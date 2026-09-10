# Báo Cáo Kỹ Thuật Tối Ưu Triệt Để Thuật Toán Export Video (PERF-FFMPEG-EXPORT-V2)

- **Mã báo cáo**: `PERF-FFMPEG-EXPORT-V2`
- **Ngày hoàn tất**: 06/09/2026
- **Trạng thái**: `DONE / VERIFIED`

---

## 1. Tóm Tắt Kết Quả (Executive Summary)

Task tối ưu triệt để toàn diện pipeline FFmpeg export cho LPHVSub đã hoàn thành xuất sắc tất cả các chỉ tiêu đề ra:
- **Thời gian xuất video 37.5 phút (2.251 giây)**: Giảm từ **> 35 phút** xuống chỉ còn **185.21 giây (~3.09 phút)**!
- **Tốc độ xuất video thực tế (Throughput)**: Đạt **12.16x Realtime** (ổn định ở mức **364.7 FPS**), vượt xa mục tiêu ban đầu ($\le$ 5 phút, tốc độ $\ge$ 10x).
- **Độ tin cậy & Test Coverage**: Toàn bộ **61/61 unit tests** (bao gồm 46 tests regression cũ và 15 tests mới) đều **PASS 100%**.
- **Chất lượng hình ảnh & Âm thanh**: Bảo toàn hoàn hảo tỷ lệ khung hình chuẩn Full-HD (1080x1920), nền mờ nghệ thuật mịn màng, phụ đề Karaoke ASS và độ đồng bộ âm thanh lồng tiếng.

---

## 2. Các Thay Đổi Kiến Trúc Cốt Lõi (Architecture Refactoring)

Hệ thống đã được tái cấu trúc thành pipeline tự quyết định và thích ứng linh hoạt:

1. **`OutputProfile` (`autodub/media/output_profile.py`)**:
   - Chuẩn hóa trung tâm kích thước canvas: 9:16 $\rightarrow$ `1080x1920`, 16:9 $\rightarrow$ `1920x1080`, 1:1 $\rightarrow$ `1080x1080`.
   - Cơ chế `pixel_budget` (mặc định 2.073.600 px) loại bỏ vĩnh viễn lỗi phình resolution lên 3.4K (`1920x3414`).

2. **`BlurStrategy` (`autodub/media/blur_strategy.py`)**:
   - Thay thế việc tính toán `boxblur` nặng nề trên CPU Full-HD bằng thuật toán **Downscale Blur Pyramid**:
     - Mode `FAST`: Downscale $6\times$ ($180\times 320$), `boxblur=4:1`, upscale `bilinear` $\rightarrow$ giảm 36 lần tải tính toán pixel của CPU.
     - Mode `BALANCED`: Downscale $4\times$ ($270\times 480$), `boxblur=6:2`, upscale `bicubic`.
     - Mode `QUALITY`: Downscale $2\times$ ($540\times 960$), `boxblur=10:2`, upscale `lanczos`.

3. **`EncoderProfile` (`autodub/media/encoder_profile.py`)**:
   - Chuẩn hóa profile phần cứng cho NVIDIA NVENC (preset `p1`, `p2`, `p4`), Intel QuickSync, AMD AMF và CPU `libx264`. Khai thác triệt để throughput phần cứng.

4. **`RenderPlan` (`autodub/media/render_plan.py`)**:
   - Mô hình DAG quản lý luồng filtergraph thống nhất giữa video gốc, nền mờ, cắt khung hình, logo, watermark và phụ đề Karaoke ASS.
   - Tích hợp mượt mà vào `build_aspect_ratio_filter()` và `merge_video()`.

5. **`RenderProfiler` (`autodub/media/render_profiler.py`)**:
   - Thu thập micro-metrics bóc tách thời gian chi tiết các phase, hoàn toàn zero-overhead khi tắt.

---

## 3. Bảng Số Liệu Đo Kiểm Thực Tế Đa Tầng (Multi-tier Benchmarks)

Đo kiểm trực tiếp trên chính video nguồn của người dùng (`BV1ZitQ62En1.mp4`):

| Thời lượng video | Thời gian render | Tốc độ xuất (Speed) | Khung hình/giây (FPS) | Cấu hình phần cứng | Canvas Output |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **15 giây (0.2m)** | **1.39s** | **10.81x** | 324.3 FPS | NVENC p1 | 1080x1920 |
| **60 giây (1.0m)** | **5.18s** | **11.58x** | 347.4 FPS | NVENC p1 | 1080x1920 |
| **300 giây (5.0m)** | **26.69s** | **11.24x** | 337.2 FPS | NVENC p1 | 1080x1920 |
| **2.251 giây (37.5m)** | **185.21s (~3.09 phút)** | **12.16x** | **364.7 FPS** | NVENC p1 | 1080x1920 |

### Bảng so sánh Trước và Sau tối ưu (Before vs After)

| Chỉ số | Trước tối ưu (Baseline) | Sau tối ưu (Optimized V2) | Mức độ cải thiện |
| :--- | :---: | :---: | :---: |
| **Tốc độ render (Speed)** | ~2.84x (lúc nghẽn 1.9x) | **12.16x** | ⚡ **Tăng +328% (nhanh hơn 4.3 lần)** |
| **Thời gian xuất video 37.5m** | > 35 phút | **~3 phút 05 giây** | ⚡ **Tiết kiệm gần 32 phút chờ đợi** |
| **Tải CPU khi làm mờ nền** | 100% bão hòa | ~12–18% nhẹ nhàng | ⚡ **Giảm 36 lần tải tính toán pixel** |
| **Kích thước Canvas (9:16)** | Bị phình 1920x3414 (3.4K) | Chuẩn 1080x1920 Full-HD | Chuẩn hóa hoàn hảo cho TikTok/Reels |

---

## 4. Danh Sách File Đã Cải Tiến

- `autodub/media/output_profile.py` (Mới)
- `autodub/media/blur_strategy.py` (Mới)
- `autodub/media/encoder_profile.py` (Mới)
- `autodub/media/render_plan.py` (Mới)
- `autodub/media/render_profiler.py` (Mới)
- `autodub/media/subtitle.py` (Tích hợp RenderPlan, tối ưu filtergraph)
- `autodub/media/video.py` (Tích hợp EncoderProfile)
- `tests/test_output_profile.py` (5 tests)
- `tests/test_blur_strategy.py` (3 tests)
- `tests/test_encoder_profile.py` (2 tests)
- `tests/test_render_profiler.py` (2 tests)
- `tests/test_render_plan_v2.py` (3 tests)
- `tests/test_subtitle.py` (29 tests)
- `tests/test_video_merge.py` (17 tests)

Toàn bộ **61/61 tests PASS**.
