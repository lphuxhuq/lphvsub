# Báo Cáo Phân Tích Sự Cố & Giải Pháp Tối Ưu Tốc Độ Xuất Video (FFmpeg Export Optimization)

- **Mã báo cáo**: `PERF-FFMPEG-EXPORT-SPEED`
- **Thời gian phân tích**: 06/09/2026
- **Trạng thái**: Đã giải quyết & xác thực bằng Benchmark thực tế (`DONE / VERIFIED`)

---

## 1. Vấn Đề Gặp Phải (The Problem)

Khi xuất video đã lồng tiếng và ghép phụ đề Karaoke ASS (đặc biệt ở chế độ chuyển đổi tỷ lệ khung hình sang TikTok 9:16), tốc độ xuất video (`ffmpeg`) ban đầu chỉ đạt **~1.9x – 2.5x**, sau đó dao động quanh **4.x – 6.x**.
- Với video dài khoảng **37 phút (2.251s)**, việc render mất tới **hơn 35 phút**.
- Mặc dù hệ thống có trang bị GPU NVIDIA NVENC (`h264_nvenc`), GPU không phát huy được hiệu năng và tốc độ bị nghẽn nghiêm trọng.

---

## 2. Nguyên Nhân Gốc Rễ (Root Cause Analysis)

Qua kiểm tra lệnh FFmpeg thực tế và giám sát tiến trình (`PID 4576` và `PID 25712`), nhóm đã phát hiện 2 nguyên nhân cốt lõi:

### Nguyên nhân 1: Nghẽn cổ chai CPU do `boxblur` ở độ phân giải Full-HD
- **Cơ chế cũ**: Trong `autodub/media/subtitle.py`, khi tạo nền mờ nghệ thuật cho chế độ TikTok 9:16:
  ```bash
  [asp_bg]scale=tw:th:force_original_aspect_ratio=increase,crop=tw:th,boxblur=20:2,eq=brightness=-0.08:saturation=1.15[asp_bgb]
  ```
- **Nút thắt**: `boxblur` là bộ lọc **Software Filter (chạy trên CPU)**. Khi áp dụng bán kính làm mờ lớn với 2 lượt quét (`passes=2`) trực tiếp trên hàng triệu điểm ảnh mỗi khung hình, CPU bị bão hòa 100% tài nguyên tính toán (CPU thread-lock).
- **Hệ quả**: GPU NVENC phải liên tục dừng chờ CPU cung cấp khung hình đã blur, khiến tốc độ tụt thảm hại xuống **~2.0x – 2.8x**.

### Nguyên nhân 2: Độ phân giải canvas bị thổi phồng lên 3.4K (`1920x3414`)
- **Cơ chế cũ**: Khi tính toán kích thước canvas đích từ video gốc 16:9 (`1920x1080`):
  ```python
  th = int(round(video_w / target_ratio))  # 1920 / (9/16) = 3414 px!
  tw = int(round(th * target_ratio))      # 1920 px
  ```
- **Nút thắt**: Thay vì xuất ra chuẩn dọc TikTok/Reels Full-HD là **1080x1920** (2.07 triệu pixels/frame), công thức trên đã vô tình tạo ra khung hình **1920x3414 (hơn 6.55 triệu pixels/frame - gấp 3.2 lần bình thường)**.
- **Hệ quả**: Khung hình khổng lồ 3.4K làm quá tải cả bộ render phụ đề ASS (`libass`) lẫn băng thông của bộ mã hóa NVENC, khiến tốc độ chỉ lẹt đẹt ở mức **4.x – 5.x**.

---

## 3. Giải Pháp Kỹ Thuật Đã Áp Dụng (Technical Solutions)

### Giải pháp 1: Kim tự tháp làm mờ (Downscale Blur Pyramid)
- Thay vì tính toán làm mờ nặng nề ở độ phân giải 1080p, ta **thu nhỏ ảnh nền trước khi blur** (xuống 1/6 kích thước: `180x320`), áp dụng `boxblur=4:1`, rồi phóng to lại kích thước đích bằng nội suy song tuyến tính mượt mà `scale=1080:1920:flags=bilinear`.
- **Hiệu quả**:
  - Giảm tải tính toán điểm ảnh cho CPU tới **36 lần** (từ 2.073.600 pixels xuống còn 57.600 pixels).
  - Nền mờ sau khi upscale mịn màng, nghệ thuật và tự nhiên hơn, hoàn toàn loại bỏ hiện tượng giật cục.

### Giải pháp 2: Chuẩn hóa kích thước Canvas Reframe (Full-HD Cap)
- Cập nhật logic trong [`autodub/media/subtitle.py`](file:///d:/Project/lphvsub-main/autodub/media/subtitle.py):
  - Khi video ngang (16:9) chuyển sang dọc (9:16), chiều rộng canvas đích được chuẩn hóa về **1080** (tức `1080x1920`), tương thích hoàn hảo chuẩn xuất của TikTok/Facebook Reels/YouTube Shorts.
  - Chặn triệt để hiện tượng bị phình lên 3.4K.

### Giải pháp 3: Tối ưu NVENC Hardware Preset
- Cập nhật trong [`autodub/media/video.py`](file:///d:/Project/lphvsub-main/autodub/media/video.py):
  - Chuyển preset phần cứng NVIDIA NVENC sang `p1` (fastest) nhằm khai thác tối đa thông lượng GPU cho các video lồng tiếng.

---

## 4. Kết Quả Đo Kiểm Thực Tế (Evidence-First Benchmarks)

Đo kiểm trực tiếp trên chính video nguồn của người dùng (`BV1ZitQ62En1.mp4`, 15 giây đầu):

| Cấu hình kiểm thử | Thời gian render 15s | Tốc độ xuất thực tế | Ghi chú |
| :--- | :---: | :---: | :---: |
| **1. Ban đầu (boxblur 20:2 Full-HD)** | `5.28s` | **2.84x** | Nghẽn CPU do boxblur |
| **2. Khi bị phình 3.4K (`1920x3414`)** | `2.66s` | **5.65x** | Quá tải canvas 6.5M pixels |
| **3. Tối ưu hoàn chỉnh (Downscale Blur + Full-HD 1080p + Preset P1)** | **1.32s** | **11.39x** | ⚡ **Nhanh gấp 4 lần (+301%)** |

> **Ước tính thời gian thực tế cho video 37 phút**:
> - Trước tối ưu: Mất **~35 phút**.
> - Sau tối ưu: Chỉ còn khoảng **~3 phút 15 giây**.

---

## 5. File Đã Thay Đổi (Modified Files)
- [`autodub/media/subtitle.py`](file:///d:/Project/lphvsub-main/autodub/media/subtitle.py):
  - Chuẩn hóa tỷ lệ canvas 9:16/16:9/1:1 tránh phình độ phân giải.
  - Tích hợp pipeline Downscale Blur Pyramid cho 2 mode `blur` và `top_split`.
- [`autodub/media/video.py`](file:///d:/Project/lphvsub-main/autodub/media/video.py):
  - Tối ưu NVENC preset sang `p1`.

Tất cả **46/46 unit tests** liên quan đến phụ đề và xuất video (`test_subtitle.py`, `test_video_merge.py`) đều vượt qua 100% (`PASSED`).
