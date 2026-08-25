# Hardsub Detection & Masking Technical Design

## 1. System Overview

Tính năng Auto Hardsub Masking tự động phát hiện các dải phụ đề cứng (burned-in subtitles) xuất hiện trên video bằng phương pháp thị giác máy tính cục bộ (Computer Vision), hợp nhất không gian - thời gian, và sinh ra danh sách `blur_regions` chuẩn tương thích 100% với hệ thống render video FFmpeg của VoxDub / LPHVSub.

---

## 2. Pipeline Architecture

```text
Video File (MP4/MKV/WebM)
          │
          ▼
Uniform Temporal Frame Sampler (OpenCV / FFmpeg Fallback)
          │
          ▼
Grayscale Preprocessing & Gradient Computation (Sobel & Morphological Closing)
          │
          ▼
Text Candidate Extraction & Corner Watermark/Logo Filtering
          │
          ▼
Spatial Clustering (Merge horizontal character/word boxes)
          │
          ▼
Temporal Tracking & Clustering (Multi-frame Track Alignment)
          │
          ▼
Multi-factor Confidence Scoring & Safety Padding
          │
          ▼
HardsubRegion Dataclass Objects
          │
          ▼
Conversion to System `blur_regions` Schema
          │
          ▼
FFmpeg `-filter_complex` (crop + boxblur + overlay)
```

---

## 3. Data Models (`autodub/media/hardsub_detector.py`)

### `HardsubRegion`
- `x`, `y`, `w`, `h`: Tọa độ $[0.0 .. 1.0]$.
- `start`, `end`: Thời điểm bắt đầu và kết thúc (giây).
- `confidence`: Trọng số tin cậy $[0.0 .. 1.0]$.
- `to_blur_region()`: Xuất dictionary `{"x": x, "y": y, "w": w, "h": h, "t_start": start, "t_end": end}`.

### `TextCandidate`
- Điểm mật độ cạnh (`edge_score`), độ tương phản (`contrast_score`), mật độ liên thông (`density_score`), vị trí không gian (`position_score`).
- `confidence = 0.30*edge + 0.25*contrast + 0.25*density + 0.20*position`.

---

## 4. Conflict Resolution & Retiming

- **Manual vs. Auto:** Hàm `merge_blur_regions_with_manual()` tự động hợp nhất các vùng vẽ tay và vùng tự động phát hiện, loại bỏ các vùng trùng lặp để tránh tạo nhiều lớp filter làm mờ trên cùng một tọa độ.
- **Retiming:** Khi thay đổi tốc độ video (`video_speed`), `rescale_blur_regions()` tự động co giãn `t_start` và `t_end` đồng bộ với âm thanh và hình ảnh.
