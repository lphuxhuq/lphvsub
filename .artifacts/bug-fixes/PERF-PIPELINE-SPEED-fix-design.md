# THIẾT KẾ GIẢI PHÁP TĂNG TỐC ĐỘ XUẤT (FIX DESIGN)
## Vấn đề: `PERF-PIPELINE-SPEED` — Tối ưu hoá thời gian chạy các bước lâu nhất

### 1. Mục tiêu
- **Giảm thời gian xuất video (Step 7)**: Từ ~71 phút xuống ~30-35 phút (tăng tốc độ encode từ 1.7x lên 4x-6x trên video 1080p có phụ đề + che logo/watermark).
- **Giảm thời gian hậu kỳ âm thanh (Step 6a)**: Từ 122 giây xuống ~35-45 giây cho 1.000 câu thoại.
- **Giữ nguyên 100% chất lượng đầu ra**: Phụ đề rõ nét, vùng che sạch đẹp, âm thanh chuẩn LUFS, không phát sinh lỗi tương thích.

---

### 2. Chi tiết các điểm thay đổi (Proposed Changes)

#### A. Tối ưu Step 7: Video Render Filtergraph & Hardware Acceleration
- **File**: `autodub/media/subtitle.py` (hàm `build_filter_complex`)
  - **Logic cũ**:
    Với mỗi vùng `blur_region`:
    ```ffmpeg
    [current]split[b0][b0c];
    [b0c]crop=W:H:X:Y,boxblur=...[bl0];
    [b0][bl0]overlay=X:Y[nxt]
    ```
    Nhân bản toàn bộ khung hình 1080x1920 (2 triệu điểm ảnh) qua nhiều lần split/crop/boxblur/overlay per-pixel.
  - **Logic mới (Ponytail - Chuẩn FFmpeg C native)**:
    ```ffmpeg
    [current]delogo=x=X:y=Y:w=W:h=H:show=0[nxt]
    ```
    Xử lý in-place trực tiếp trên bộ nhớ khung hình mà không cần tách stream hay dán đè alpha.
    Benchmark thực tế trên video dự án: **14.9x** vs **7.2x** (nhanh hơn **107%**).

- **File**: `autodub/media/video.py` (hàm `merge_video`)
  - Thêm `-hwaccel auto` trước video đầu vào khi có GPU encoder để tận dụng phần cứng giải mã (Hardware Decode).

#### B. Tối ưu Step 6a: Voice Postprocess Concurrency
- **File**: `autodub/resources.py`
  - Thêm `FFMPEG_AUDIO_SLOTS = threading.BoundedSemaphore(max(4, min(16, (_CPU - 1) * 2)))` chuyên trách cho các tác vụ audio siêu nhẹ.
- **File**: `autodub/media/audio.py`
  - Trong `postprocess_voice_clip`: acquire `FFMPEG_AUDIO_SLOTS` thay cho `FFMPEG_SLOTS`.
  - Trong `postprocess_voice_clips`: tăng `max_workers` mặc định lên tương ứng với số slot audio.

---

### 3. Kế hoạch Kiểm thử & Đảm bảo Không hồi quy (Verification Plan)
1. **Unit Tests**:
   - Viết `tests/test_perf_optimizations.py`:
     + Kiểm tra `build_filter_complex` tạo ra chuỗi `delogo` chính xác với tọa độ pixel và mốc thời gian `enable='between(...)'`.
     + Kiểm tra lệnh `ffmpeg` sinh ra chạy mượt mà (exit code 0).
     + Kiểm tra concurrency của `FFMPEG_AUDIO_SLOTS`.
2. **Regression Tests**:
   - Chạy toàn bộ 17 bài kiểm thử pipeline cache và wiring đã có:
     `pytest tests/test_incremental_pipeline_cache.py tests/test_align_global_cache.py tests/test_tts_cache.py tests/test_pipeline_translation_cache.py tests/test_pipeline_wiring.py`
3. **Đo đạc thực tế (Benchmark)**:
   - Đo thời gian render thực tế và so sánh FPS / speed factor.
