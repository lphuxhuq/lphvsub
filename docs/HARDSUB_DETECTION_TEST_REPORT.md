# Hardsub Detection Test Suite Report

## 1. Test Coverage Overview

Tổng cộng **7 tệp kiểm thử chuyên biệt** cho tính năng Hardsub Detection & Masking:

1. **`tests/test_hardsub_detector_model.py`:**
   - `test_hardsub_region_valid`: Xác thực model và chuyển đổi `to_blur_region()`.
   - `test_hardsub_region_validation_rejections`: Kiểm tra chặn giá trị biên lỗi (tọa độ âm, confidence > 1, thời gian end < start).
   - `test_frame_sample_model`: Xác thực model `FrameSample`.
   - `test_text_candidate_model`: Xác thực model `TextCandidate`.

2. **`tests/test_hardsub_sampling.py`:**
   - `test_extract_video_frames_missing_file`: Xử lý an toàn khi tệp video không tồn tại.
   - `test_extract_video_frames_with_mock_opencv`: Kiểm tra trích xuất frame bằng OpenCV và lấy mẫu thời gian đều.

3. **`tests/test_hardsub_detector.py`:**
   - `test_detect_text_candidates_bottom_subtitles`: Phát hiện dải phụ đề đáy.
   - `test_detect_text_candidates_top_subtitles`: Phát hiện dải phụ đề đỉnh.
   - `test_detect_text_candidates_clean_frame`: Đảm bảo không bắt nhầm frame trống.
   - `test_spatial_merge_candidates`: Hợp nhất không gian các ký tự thành khối phụ đề.

4. **`tests/test_hardsub_clustering.py`:**
   - `test_track_temporal_regions_stable_bottom_sub`: Theo dõi chuỗi thời gian liên khung hình.
   - `test_corner_watermark_rejection`: Lọc bỏ logo/watermark góc màn hình.
   - `test_merge_blur_regions_with_manual_deduplication`: Hợp nhất và chống trùng lặp với vùng vẽ tay.

5. **`tests/test_hardsub_pipeline.py`:**
   - `test_pipeline_auto_mask_hardsub_off_by_default`: Đảm bảo giữ nguyên hành vi mặc định khi tắt cờ.
   - `test_pipeline_auto_mask_hardsub_enabled_flow`: Luồng kích hoạt tự động trong pipeline.

6. **`tests/test_hardsub_benchmark.py`:**
   - `test_hardsub_benchmark_and_accuracy`: Đo lường tốc độ (< 1.0s) và độ bao phủ Ground Truth (IoU >= 0.65, Recall >= 0.95).

7. **`tests/test_style_dialog_auto_mask.py`:**
   - `test_auto_detect_hardsub_regions_in_editor`: Gọi từ module Editor.
   - `test_style_dialog_auto_detect_button`: Tương tác nút bấm "Dò tự động" trên giao diện StyleDialog.

---

## 2. Kết quả Chạy Kiểm thử
Tất cả các test case đều đã chạy thành công **100% PASSED**.
