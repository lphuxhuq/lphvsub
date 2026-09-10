# Kế Hoạch Phân Chia Task — Turbo + Reliable Smart Download Engine

- **Mã kế hoạch**: `SMART-DOWNLOAD-ENGINE`
- **Mục tiêu**: Phân chia lộ trình nâng cấp download engine thành các unit độc lập, test-first, đảm bảo không hồi quy.

---

## Danh Sách Các Task & Thứ Tự Thực Hiện

### TASK-00: Baseline & Test Harness Setup
- Tạo các mock/fixture test cho HTTP Range, CDN racing, Douyin stream sniffing, và Bilibili DASH streams.
- Kiểm tra baseline hiện tại và bảo đảm 100% tests hiện hữu đều pass.

### TASK-01: DownloadResult Contract & Exception Models
- Tạo `autodub/media/download/contract.py` định nghĩa `DownloadResult`, `DownloadRequest`, `PreflightResult`, `ErrorClassification`.
- Đảm bảo tương thích với kết quả trả về của `downloader.py` và `douyin.py`.

### TASK-02: MediaValidator Component
- Tạo `autodub/media/download/validator.py`.
- Sử dụng ffprobe bóc tách metadata, kiểm tra tính hợp lệ của video/audio stream, duration, container, moov atom.
- Viết `tests/test_download_media_validator.py`.

### TASK-03: Error Classification & Smart Retry Policy
- Tạo `autodub/media/download/retry.py`.
- Định nghĩa phân loại lỗi HTTP 403, 416, 429, timeout, connection reset và exponential backoff với jitter.
- Viết `tests/test_download_retry.py`.

### TASK-04: Resume & Partial Download Manager
- Tạo `autodub/media/download/partial_manager.py`.
- Hỗ trợ lưu/nạp `.progress.json`, kiểm tra byte range cục bộ, gửi `Range: bytes=X-`, merge các chunk mà không làm mất tiến trình khi lỗi mạng.
- Viết `tests/test_download_resume.py`.

### TASK-05: Adaptive Concurrency Controller
- Tạo `autodub/media/download/concurrency.py`.
- Hiện thực hóa thuật toán AIMD tự động tăng giảm số luồng tải mảnh dựa trên throughput và lỗi 429/timeout.
- Viết `tests/test_download_concurrency.py`.

### TASK-06: Cookie & Session Manager
- Tạo `autodub/media/download/session_manager.py`.
- Quản lý cookies cho Bilibili và Douyin từ browser, tệp cookie, hoặc session lưu trữ.
- Viết `tests/test_download_session.py`.

### TASK-07: BrowserPool cho Douyin
- Tạo `autodub/media/download/browser_pool.py`.
- Singleton quản lý 1 tiến trình Chromium duy nhất của Playwright, tái sử dụng contexts/pages, tự phục hồi khi crash và dọn dẹp sạch tiến trình khi shutdown.
- Viết `tests/test_download_browser_pool.py`.

### TASK-08: Preflight Analyzer & CDN Candidate Racing
- Tạo `autodub/media/download/preflight.py` và `cdn_racer.py`.
- Thực hiện probe nhẹ (HEAD/Range), đo TTFB, đánh giá băng thông sơ bộ và xếp hạng candidate CDN.
- Viết `tests/test_download_cdn_racing.py`.

### TASK-09: Download Cache & Performance Store
- Tạo `autodub/media/download/cache.py` (kết nối với `pipeline_cache.py`) và `performance_store.py` (SQLite telemetry & health score).
- Viết `tests/test_download_cache.py`.

### TASK-10: Douyin Engine Upgrade
- Tạo `autodub/media/download/douyin_engine.py`.
- Tích hợp direct play URL không watermark, kết nối `BrowserPool`, tải đa luồng DASH và mux FFmpeg.
- Viết `tests/test_douyin_engine.py`.

### TASK-11: Bilibili Engine Upgrade
- Tạo `autodub/media/download/bilibili_engine.py`.
- Hỗ trợ phân tích DASH/Progressive, CDN racing, chunked range downloading với Adaptive Concurrency và mux FFmpeg.
- Viết `tests/test_bilibili_engine.py`.

### TASK-12: Download Decision Engine & Facade Integration
- Tạo `autodub/media/download/decision_engine.py`.
- Cập nhật adapter `autodub/media/downloader.py` chuyển tiếp toàn bộ cuộc gọi sang engine mới mà không làm thay đổi public API (`download_video`, `download_one`, `download_one_isolated`).

### TASK-13: Comprehensive Tests, Benchmarks & Regression Sweep
- Chạy toàn bộ test suite (unit, integration, regression).
- Chạy benchmark so sánh tốc độ tải và khả năng resume giữa phiên bản cũ và mới.
- Xuất báo cáo nghiệm thu hoàn chỉnh.
