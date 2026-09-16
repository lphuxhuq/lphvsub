# Final Audit: Audio-Video Timing, Synchronization & Engine Health

## 1. Executive Summary
- **Module**: Audio-Video Timing Alignment, Retiming, Muxing, and Subtitle Sync.
- **Upstream Baseline**: `https://github.com/ttthanh2044/voxdub` (main branch).
- **Test Results**: **626/626 PASSED (100%)**.

## 2. Verified Invariants
1. **No Piecewise Frame Dropping**: The entire video and audio follow uniform timeline expansion (`VIDEO_SPEED`), preventing visual stutter.
2. **Soft Timing Fit Drift Invariant**: Drift is strictly bounded by `timing_max_drift_s` (1.5s), and compression is strictly bounded by `timing_max_atempo` (1.1x).
3. **Studio-Grade Ducking**: Cosine S-curve envelope with 80ms attack and 220ms release eliminates audio clipping and abrupt volume jumps.
4. **Single Source of Truth for Subtitles**: `refresh_subtitles` regenerates subtitles from real rendered timestamps, ensuring subtitles and dubbed speech match frame-for-frame.

## 3. Audit Verdict
**FINAL AUDIT: PASSED (100%)**

---

# Codebase-wide Latent Bug, Encoding & Division-by-Zero Audit

## 1. Mục tiêu & Phạm vi
- **Mục tiêu**: Rà soát toàn bộ mã nguồn `autodub`, `autodub_gui`, `scripts`, và `tests` để phát hiện và xử lý triệt để các lỗi tiềm ẩn: mã hóa văn bản (text encoding), lỗi chia cho 0 (division by zero), xử lý biên mốc thời gian (timestamp alignment / None-safety), và chuẩn hóa đọc số/ngày tháng tiếng Việt.
- **Phạm vi**: 587 tệp tin trong kho mã nguồn.

## 2. Các vấn đề đã xử lý
### 2.1. Chuẩn hóa mã hóa văn bản (Text Encoding UTF-8)
- Đã bổ sung `encoding="utf-8"` tường minh tại tất cả các điểm mở tệp văn bản trong kiểm thử (`tests/test_batch.py`, `tests/test_bilibili_downloader.py`, `tests/test_pipeline_asr_source.py`, `tests/test_retime.py`, `tests/test_social_card_ui.py`, `tests/test_url_resume.py`). Toàn bộ lệnh gọi `open()` chế độ văn bản trong codebase hiện đảm bảo chạy độc lập với bảng mã hệ thống Windows ANSI/CP1252.

### 2.2. Khắc phục nguy cơ chia cho 0 (ZeroDivisionError)
- **`autodub_gui/style_dialog.py`**:
  - `normalized_regions()` và `_apply_text_drag()` được kiểm tra `pr.width() <= 0 or pr.height() <= 0` thay vì `== 0`.
- **`autodub_gui/video/timeline.py`**:
  - `_visible_span()` được kiểm tra an toàn `self._zoom > 0`.
  - `_label_step()` được bảo vệ với `span <= 0`.
- **`autodub_gui/waveform.py`**:
  - Phép chia khối mẫu và chia kênh dùng `max(1, width * channels)` và `max(1, channels)`.
- **`autodub_gui/workers_setup.py`**:
  - Tiến trình cài đặt dùng `max(1, total_lines)`.

### 2.3. Khử lỗi mốc thời gian Whisper (Timestamp None / Alignment)
- **`autodub/speech/transcriber.py`**: `seg.start` và `seg.end` ép kiểu an toàn với `float(seg.start or 0.0)` và `float(seg.end or start)`; từ khóa khuyết thời gian được gán theo câu.
- **`autodub/speech/asr_whisper_worker.py`**: từ khóa `w.start` / `w.end` khuyết được fallback về mốc câu.

### 2.4. Chuẩn hóa đọc ngày tháng & nhiệt độ tiếng Việt
- **`autodub/text/vi_numbers.py`**: Bổ sung quy tắc ngày tháng (`dd/mm/yyyy`, `ngày/hôm dd/mm`, `tháng mm/yyyy` với tháng 4 là "tháng tư") và nhiệt độ (`°C`, `°`).

## 3. Kết quả xác thực
- `pytest`: **1344/1344 passed (100%)**
- `tests/test_vi_diacritics.py`: **3/3 passed**
- `tests/test_vi_numbers_extended.py`: **7/7 passed**
