# Project Map — LPHVSub Export & Media Pipeline

- **Trạng thái**: `ĐÃ XÁC MINH`
- **Mục tiêu**: Phục vụ Task PERF-FFMPEG-EXPORT-V2 (Triệt để tối ưu kiến trúc Export Video)

---

## 1. Tổng Quan
LPHVSub (VoxDub) là ứng dụng Python/PySide6 tự động hóa lồng tiếng video, nhận diện giọng nói (ASR), dịch thuật (Translation AI), sinh giọng đọc (TTS), canh chỉnh nhịp (Audio Retiming & ASS Karaoke) và xuất video hoàn thiện (FFmpeg Video Composition & NVENC HW Encoding).

## 2. Technology Stack & Media Core
- **Ngôn ngữ**: Python 3.11
- **GUI**: PySide6 (Qt6)
- **Video Engine**: FFmpeg (`ffmpeg.exe`, `ffprobe.exe`)
- **Bộ mã hóa Video**: NVIDIA NVENC (`h264_nvenc`), Intel QuickSync (`h264_qsv`), AMD AMF (`h264_amf`), CPU Fallback (`libx264`)
- **Subtitle Renderer**: `libass` thông qua bộ lọc FFmpeg `subtitles='...'` (hỗ trợ file ASS Karaoke cụm từ và SRT)
- **AI Inpaint Subtitle**: LaMa ONNX (`lama_onnx.py`) / VSR CLI Bridge (`vsr_bridge.py`)

## 3. Kiến Trúc Pipeline Video Export Hiện Tại

```text
Input Video (MP4) + Dubbed Audio (WAV) + Subtitles (ASS/SRT)
         │
         ▼
merge_video() [autodub/media/video.py]
  ├── (Tùy chọn) AI Inpaint: inpaint_video_with_cache() [autodub/media/inpaint/]
  ├── probe_dimensions(video_path) -> (video_w, video_h)
  ├── build_filter_complex() [autodub/media/subtitle.py]
  │     ├── 1. Smart Flip: [current]hflip[vflip]
  │     ├── 2. Micro Zoom: [current]scale=...,crop=...[vzoom]
  │     ├── 3. Color Filter: [current]colorbalance=...,eq=...[vcolor]
  │     ├── 4. Aspect Preset & Banner: build_aspect_ratio_filter()
  │     │       ├── 'blur': split[asp_bg][asp_fg] -> downscale blur -> upscale -> overlay
  │     │       ├── 'top_split': split[asp_bg][asp_fg] -> top overlay 12%
  │     │       ├── 'center_crop': scale,crop
  │     │       └── 'banner': pad + top/bottom drawtext header/footer
  │     ├── 5. Blur Regions: [current]split... crop... boxblur... overlay
  │     ├── 6. Logo: movie='...',scale=...,colorchannelmixer=... -> overlay
  │     ├── 7. Moving Watermark: drawtext=...
  │     └── 8. Subtitles: subtitles='...':fontsdir='...'
  └── FFmpeg Command Construction:
        ffmpeg -hwaccel auto -threads 0 -i video -i audio -filter_complex ... -c:v h264_nvenc ...
```

## 4. Các Điểm Nghẽn & Rủi Ro Phát Hiện (Findings & Risks)

1. **Resolution Phình Bất Thường (`ĐÃ XÁC MINH`)**:
   - Trước đây trong `build_aspect_ratio_filter`, khi video 1920x1080 chuyển sang 9:16, công thức tính `th = video_w / (9/16) = 3414` khiến canvas bị đội lên 1920x3414 (hơn 6.55 triệu pixel).
   - Đang thiếu một abstraction trung tâm `OutputProfile` có `pixel_budget` quản lý toàn bộ output resolution thống nhất cho cả video, subtitle ASS, và viral clipper.

2. **Hard-coded Filter Graph & Thiếu RenderPlan (`ĐÃ XÁC MINH`)**:
   - Filtergraph được ghép chuỗi tuần tự thủ công trong `subtitle.py` thành một chuỗi string dài.
   - Chưa có phân tách các lớp (Background, Foreground, Subtitle, Overlay) theo dạng DAG / RenderPlan.
   - Không có dirty-layer tracking: mỗi lần xuất đều phải render lại toàn bộ từ đầu, dù có những thành phần tĩnh (static background, watermark, logo, audio mux).

3. **Background Blur Strategy Thiếu Adaptive (`ĐÃ XÁC MINH`)**:
   - Hiện tại tỷ lệ downscale blur đang hardcode 1/6 và boxblur=4:1.
   - Chưa có các profile chất lượng (FAST, BALANCED, QUALITY).
   - Chưa có cơ chế cache background tĩnh (nếu video chỉ cần che hoặc làm mờ nền tĩnh).

4. **ASS Karaoke & libass Complexity (`ĐÃ XÁC MINH`)**:
   - Header ASS sinh bởi `ass_karaoke.py` dùng `PlayResX=512, PlayResY=288` (tương đương 16:9). Khi render trên canvas dọc 9:16 (1080x1920), libass tự scale nhưng nếu không khớp aspect ratio hoặc kích thước, font chữ có thể bị méo hoặc quá khổ nếu wrap style không chuẩn.

5. **Thiếu Render Profiler Chi Tiết (`ĐÃ XÁC MINH`)**:
   - Hiện tại mới chỉ đo tổng thời gian chạy qua `ProgressTracker` và in `speed=x`. Chưa bóc tách được thời gian cho từng giai đoạn: Decode, Blur, Subtitle Render, Encode, Mux.

---

`TRẠNG THÁI: HOÀN THÀNH`
