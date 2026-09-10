# Đặc Tả Yêu Cầu — Turbo + Reliable Smart Download Engine (Bilibili + Douyin)

- **Mã tính năng**: `SMART-DOWNLOAD-ENGINE`
- **Mục tiêu**: Nâng cấp toàn diện download subsystem cho Bilibili và Douyin, tối ưu hóa tốc độ, độ tin cậy, tự phục hồi lỗi mạng, hỗ trợ resume/chunking, browser pool và tích hợp media validator.

---

## 1. Bối cảnh & Vấn đề hiện tại
1. **Bilibili**:
   - `downloader.py` dùng yt-dlp với cấu hình cứng; xóa sạch file `.part` khi gặp lỗi làm mất toàn bộ tiến trình đã tải.
   - Bilibili Akamai/BVC CDN ngắt kết nối sau ~85MB (~100s) với audio/video; không có cơ chế race CDN candidate hay adaptive chunking.
   - Không có bộ kiểm tra toàn vẹn đa luồng video+audio sau khi tải/merge.
2. **Douyin**:
   - `douyin.py` dùng requests tải tuần tự 1 luồng; khi thất bại xóa `.part` và launch Chromium (Playwright) mới tinh từ đầu, gây lãng phí RAM, CPU và độ trễ khởi động cao (2-5s mỗi lần mở browser).
   - Không tái sử dụng browser context/session; không quản lý pool browser khiến nguy cơ sinh orphan Chromium process khi người dùng cancel.
3. **Chung**:
   - Thiếu `MediaValidator` bằng ffprobe để xác nhận luồng video/audio hợp lệ trước khi đẩy vào pipeline downstream.
   - Thiếu `DownloadDecisionEngine` phân tích trước (Preflight) để tự động chọn chiến lược tải tốt nhất.
   - Thiếu `DownloadCache` và `PerformanceStore` để học và ưu tiên các CDN ổn định nhất.

---

## 2. Yêu cầu Chức năng (Functional Requirements)

### FR-01: Standardized DownloadResult Contract
- Chuẩn hóa đầu ra thống nhất cho tất cả các downloader:
  ```python
  @dataclass
  class DownloadResult:
      success: bool
      path: str
      platform: str
      media_id: str
      duration: float
      width: int
      height: int
      fps: float
      video_codec: str
      audio_codec: str
      file_size: int
      elapsed_seconds: float
      average_speed: float
      peak_speed: float
      retries: int
      backend: str
      cdn: str
      resumed: bool = False
      cache_hit: bool = False
      validation_passed: bool = True
      title: str = ""
      uploader: str = ""
  ```
- Duy trì 100% tương thích ngược với các caller hiện tại (`download_video`, `download_one`, `download_one_isolated`).

### FR-02: MediaValidator (Kiểm tra Toàn vẹn Media)
- Kiểm tra bắt buộc sau khi tải:
  - File tồn tại và `file_size > 10_000` bytes.
  - Container hợp lệ đọc được bởi ffprobe.
  - `duration > 0`.
  - Có luồng video (width > 0, height > 0, codec hợp lệ).
  - Có luồng audio (nếu video gốc có audio).
- Không bao giờ trả về file hỏng hoặc lỗi moov atom cho downstream pipeline.

### FR-03: Error Classification & Smart Retry
- Phân loại lỗi chính xác:
  - `HTTP 403`: Refresh session, cookie, đổi CDN candidate, fallback Playwright.
  - `HTTP 416 (Range Not Satisfiable)`: Kiểm tra/sửa trạng thái resume, re-probe resource.
  - `HTTP 429 (Rate Limit)`: Exponential backoff + jitter, giảm concurrency, kích hoạt cooldown.
  - `Timeout / Connection Reset`: Giảm concurrency, đổi CDN, tiếp tục tải từ byte dở dang.
- Exponential backoff với jitter: `interval = min(max_backoff, base_backoff * (2 ** attempt)) * (0.8 + 0.4 * random)`.

### FR-04: Resume & Partial Download Engine
- Lưu metadata tiến trình vào file `.progress.json` cạnh `.part`.
- Hỗ trợ HTTP Range request `Range: bytes=X-` để tiếp tục tải từ byte dừng lại thay vì tải lại từ 0.
- Tuyệt đối không xóa `.part` khi gặp lỗi mạng tạm thời hoặc khi user cancel.

### FR-05: Adaptive Concurrency Controller
- Điều chỉnh số luồng tải mảnh/chunk dựa trên throughput thực tế và tỷ lệ lỗi:
  - Ban đầu: 4 luồng.
  - Tốc độ tăng + 0 lỗi: tăng dần lên 6 -> 8 luồng (trần cấu hình).
  - Xuất hiện lỗi mạng / 429 / rớt tốc độ: tự động hạ về 4 -> 2 luồng.

### FR-06: BrowserPool cho Douyin
- Quản lý vòng đời Chromium dùng chung:
  - `BrowserPool` khởi tạo 1 instance Chromium headless duy nhất.
  - Cấp phát `BrowserContext` và `Page` độc lập cho từng request tải.
  - Tự động reset context, thu hồi page, health check và tự khởi động lại khi crash.
  - Tự động đóng hoàn toàn khi ứng dụng tắt, không để lại tiến trình ma (orphan process).

### FR-07: Preflight Analyzer & CDN Candidate Racing
- Probe nhanh (HEAD / Range 0-1024) các CDN candidate để đo độ trễ TTFB, hỗ trợ Range, và dung lượng.
- Xếp hạng candidate, chọn CDN có throughput tốt nhất làm Primary, các CDN còn lại làm Fallback.

### FR-08: Download Cache & Performance Store
- Tích hợp với `autodub/pipeline_cache.py`: lưu trữ video theo `(platform, media_id, quality)` để tái sử dụng ngay lập tức giữa các project.
- SQLite telemetry ghi nhận lịch sử hiệu năng các CDN để `DecisionEngine` học hỏi cho các lần tải sau.

---

## 3. Yêu cầu Phi chức năng (Non-Functional Requirements)
- **Zero GUI Leaks**: Toàn bộ download engine nằm trong Core (`autodub/media/`), không import bất kỳ thành phần nào của `autodub_gui` hay `PySide6`.
- **Cancellation-safe**: Đáp ứng ngay lập tức khi nhận tín hiệu hủy (`cancel_event.is_set()`), đóng stream và giữ nguyên file partial cho lần resume sau.
- **Process-safe**: Mọi lệnh FFmpeg, ffprobe chạy qua subprocess đều có timeout và drain stderr/stdout tránh treo pipe buffer.
- **Performance**: Giảm thời gian tải trung bình ít nhất 30-50%, giảm 90% lỗi tải lại từ đầu.
