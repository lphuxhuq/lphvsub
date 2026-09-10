# Thiết Kế Kiến Trúc: Tích Hợp Douyin Downloader V2 & Việt Hoá Vào lphvsub-main

- **Mã thiết kế**: `DESIGN-SMART-DOWNLOAD-ENGINE-DOUYIN-V2`
- **Mục tiêu**: Thiết kế module tích hợp lõi Douyin V2 (chữ ký `a_bogus`, streaming chunk 256KB, PCDN Guard, Playwright Cookie Fetcher) vào download subsystem hiện hữu, Việt hoá toàn diện, giữ nguyên vẹn hợp đồng `DownloadResult` cho pipeline downstream.

---

## 1. Requirement đã duyệt
- **Mã yêu cầu**: `SMART-DOWNLOAD-ENGINE-DOUYIN-V2` (đã duyệt qua `DUYỆT PHÂN TÍCH`).
- **Phạm vi**:
  - Tải video Douyin trực tiếp qua API chính thống `/aweme/v1/web/aweme/detail/` với chữ ký `a_bogus` tự động.
  - Tải streaming với buffer 256KB chunk (`_DOWNLOAD_CHUNK_BYTES`), PCDN anti-blackhole guard.
  - Hỗ trợ resume khi rớt mạng bằng `PartialDownloadManager` và HTTP Range request.
  - Trình lấy cookie Douyin tự động Playwright với giao diện và thông báo tiếng Việt.
  - 100% tiếng Việt cho nhật ký, tiến trình (ETA, tốc độ MB/s), cảnh báo và thông báo lỗi.
  - Xác thực toàn vẹn bằng `MediaValidator` (ffprobe container, video, audio).
  - Không phá vỡ bất kỳ bước downstream nào (`ASR -> Translation -> TTS -> Timing -> Video Render`).

---

## 2. Kiến trúc hiện tại liên quan

```text
autodub/media/
├── downloader.py             # Facade download_video, download_one, normalize_url
├── douyin.py                 # Scraper regex cũ (_ROUTER_DATA_RE) + Playwright launch cũ
└── download/
    ├── contract.py           # DownloadResult, DownloadRequest, PreflightResult, ErrorType
    ├── decision_engine.py    # Điều phối: cache -> bilibili -> douyin -> yt-dlp
    ├── douyin_engine.py      # DouyinDownloader hiện tại (vẫn dùng router regex cũ)
    ├── bilibili_engine.py    # BilibiliDownloader (DASH, progressive, cdn racing)
    ├── partial_manager.py    # Quản lý .progress.json, Range header
    ├── concurrency.py        # AdaptiveConcurrencyController (AIMD)
    ├── session_manager.py    # CookieSessionManager
    ├── browser_pool.py       # Chromium Singleton Pool
    ├── cdn_racer.py          # Lightweight CDN racing
    ├── cache.py              # DownloadCache (Universal Pipeline Cache)
    ├── performance_store.py  # SQLite telemetry & CDN health score
    └── validator.py          # MediaValidator (ffprobe)
```

---

## 3. Kiến trúc đề xuất

Tổ chức lại module Douyin thành một package con chuyên trách độc lập bên trong `autodub/media/download/douyin/`, được kết nối chặt chẽ với `douyin_engine.py`:

```text
autodub/media/download/
├── douyin/                               # Package con chuyên trách Douyin V2
│   ├── __init__.py
│   ├── a_bogus.py                        # Thuật toán ký a_bogus (pure Python, gmssl SM3)
│   ├── api_client.py                     # Web client gọi /aweme/v1/web/aweme/detail/
│   ├── stream_downloader.py              # Async streaming chunk 256KB + PCDN Guard
│   └── cookie_fetcher.py                 # Tool Playwright tự động bắt cookie (Việt hoá)
│
├── douyin_engine.py                      # DouyinDownloader V2 tích hợp DecisionEngine
├── decision_engine.py                    # Tuyến điều phối cấp cao
├── contract.py                           # DownloadResult thống nhất
└── session_manager.py                    # Nạp cookie Douyin từ file lưu trữ
```

---

## 4. Component thay đổi

### 4.1. `autodub/media/download/douyin/a_bogus.py` (Mới)
- Cung cấp class `ABogusSigner`:
  - `generate_a_bogus(query_string: str, user_agent: str) -> str`: Tạo chuỗi ký tự `a_bogus` gắn vào query parameter của request.
  - Tự động mã hoá theo thuật toán chuẩn của Douyin Web 2026.

### 4.2. `autodub/media/download/douyin/api_client.py` (Mới)
- Cung cấp class `DouyinApiClient`:
  - `get_video_detail(aweme_id: str, cookies: dict) -> dict`: Gọi endpoint `/aweme/v1/web/aweme/detail/`.
  - Tự động phân tích bitrate cao nhất không watermark, link cover, tiêu đề, tác giả.
  - Phân loại lỗi HTTP 403 / anti-bot để kích hoạt cơ chế thông báo Cookie tiếng Việt.

### 4.3. `autodub/media/download/douyin/stream_downloader.py` (Mới)
- Cung cấp class `DouyinStreamDownloader`:
  - Tải streaming bất đồng bộ với buffer 256KB (`_DOWNLOAD_CHUNK_BYTES = 256 * 1024`).
  - **PCDN Guard**: Đo thời gian phản hồi giữa các chunk. Nếu node chậm bất thường hoặc thuộc blacklist IP/domain (`*.qtaeixd.com`), tự động ngắt sau 5s và chuyển sang URL candidate dự phòng.
  - Báo cáo tiến trình tải chi tiết qua callback: tỷ lệ %, tốc độ MB/s, ETA tiếng Việt.

### 4.4. `autodub/media/download/douyin/cookie_fetcher.py` (Mới)
- Cung cấp hàm `fetch_douyin_cookies_interactive(headless: bool = False) -> dict`:
  - Khởi chạy Chromium qua Playwright mở `https://www.douyin.com/`.
  - In thông báo tiếng Việt trực quan ra console / giao diện.
  - Lưu cookie hợp lệ vào `~/.autodub/douyin_cookies.json` hoặc cấu hình app.

### 4.5. `autodub/media/download/douyin_engine.py` (Nâng cấp)
- Kế thừa và hoàn thiện lớp `DouyinDownloader`:
  - Tiếp nhận `DownloadRequest`.
  - Nạp cookie từ `SessionManager` / `douyin_cookies.json`.
  - Gọi `DouyinApiClient` trích xuất link không watermark trong < 1s.
  - Tải file bằng `DouyinStreamDownloader` hoặc `PartialDownloadManager`.
  - Nếu gặp CAPTCHA nâng cao: tự động fallback sang `BrowserPool`.
  - Chạy `MediaValidator.validate()` bằng ffprobe.
  - Trả về `DownloadResult` đầy đủ trường dữ liệu.

### 4.6. `autodub/media/douyin.py` (Cập nhật Facade)
- Chuyển tiếp toàn bộ các cuộc gọi `download_douyin` cũ sang `DouyinDownloader` V2 mới.

---

## 5. Data Flow (Luồng dữ liệu)

```text
Người dùng dán Link Douyin (ngắn, web, modal_id)
  │
  ▼
PlatformDetector.detect() ──► Platform.DOUYIN
  │
  ▼
DownloadDecisionEngine.download()
  │
  ├──► [1] Kiểm tra DownloadCache (Nếu có file hợp lệ -> Cache Hit)
  │
  └──► [2] Gọi DouyinDownloader.download(request)
         │
         ├── Nạp Cookies từ CookieSessionManager
         ├── Ký query bằng ABogusSigner.generate_a_bogus()
         ├── DouyinApiClient gửi request tới /aweme/v1/web/aweme/detail/
         │     │
         │     ├── [API OK] -> Lấy URL video bitrate cao nhất (không logo)
         │     │
         │     └── [Anti-bot / 403] -> Báo lỗi tiếng Việt / Fallback BrowserPool
         │
         ├── DouyinStreamDownloader tải streaming (buffer 256KB, PCDN Guard)
         │     │
         │     ├── Cập nhật tiến trình: % hoàn thành, tốc độ MB/s, ETA
         │     └── Lưu vào file tạm .part + metadata .progress.json
         │
         ├── Hoàn tất tải -> Đổi tên thành file .mp4 chính thức
         │
         ├── MediaValidator.validate() (ffprobe kiểm tra video, audio, duration)
         │
         └── Trả về DownloadResult -> Chuyển vào Pipeline Downstream
```

---

## 6. Control Flow (Luồng điều khiển & Fallback)

1. **Direct API V2 (Primary)**:
   - Thời gian xử lý: ~1 – 2 giây.
   - Không mở browser, sử dụng `a_bogus` + Cookies.
2. **BrowserPool Sniffing (Secondary)**:
   - Kích hoạt khi: API trả về 403 / anti-bot liên tục 3 lần hoặc yêu cầu trượt CAPTCHA.
   - Mở context trong `BrowserPool` đã khởi tạo sẵn, bắt URL media từ request network.
3. **Smart Retry**:
   - Áp dụng exponential backoff (1s, 2s, 4s) kèm random jitter cho các lỗi mạng tạm thời.
   - PCDN blackhole timeout: ngắt kết nối sau 5s thay vì chờ 300s.

---

## 7. Database
- Sử dụng `performance_store.py` (SQLite) hiện tại:
  - Bảng `download_history`: Ghi nhận `platform='douyin'`, `backend='direct_api_v2'`, `elapsed_seconds`, `average_speed`, `file_size`.
  - Bảng `cdn_health`: Đánh giá chất lượng các domain CDN Douyin.
- File lưu cookie: `~/.autodub/douyin_cookies.json` (JSON dạng key-value đơn giản, nhẹ, dễ đọc/ghi).

---

## 8. API Contract
- Duy trì 100% signature của `autodub.media.download.contract.DownloadRequest` và `DownloadResult`.
- Public functions trong `autodub/media/douyin.py`:
  - `download_douyin(url: str, output_dir: str = "downloads") -> dict`
  - `extract_clean_url(text: str) -> str`
  - `is_douyin_url(url: str) -> bool`

---

## 9. UI Contract & Việt Hoá
- Định dạng chuỗi thông báo tiến trình hiển thị trên Terminal và giao diện:
  - Bắt đầu: `"Đang phân tích liên kết Douyin: {id}..."`
  - Đang tải: `"Đang tải: [{bar}] {percent}% | {speed} MB/s | Còn lại: {eta}"`
  - Hoàn tất: `"Tải thành công video {id} ({size} MB) sau {time}s"`
  - Lỗi cookie: `"Lỗi: Cookie Douyin chưa được cấu hình hoặc đã hết hạn. Hãy chạy lệnh 'python -m autodub.media.download.douyin.cookie_fetcher' để cập nhật."`

---

## 10. Validation
- Sử dụng `MediaValidator`:
  - `file_size > 10_000` bytes.
  - ffprobe container đọc được (format_name chứa mp4 hoặc mov).
  - Có luồng video (width > 0, height > 0, fps > 0).
  - Có luồng audio (codec aac/mp3) nếu video gốc có âm thanh.
  - `duration > 0.5s`.

---

## 11. Error Handling (Xử lý lỗi)
- **HTTP 403 / Anti-bot**: `ErrorType.HTTP_403` -> Báo cảnh báo tiếng Việt yêu cầu cập nhật cookie, tự động chuyển hướng fallback sang `BrowserPool`.
- **PCDN Stalling (Treo mạng)**: `ErrorType.TIMEOUT` -> Timeout 5s ngắt kết nối, chuyển sang candidate CDN khác.
- **Rớt mạng giữa chừng**: `PartialDownloadManager` giữ nguyên `.part` và `.progress.json`, cho phép tải tiếp.
- **Video riêng tư / Bị xoá**: Trả về `DownloadResult(success=False, error_type=ErrorType.UNRECOVERABLE, error_message="Video không tồn tại hoặc đã bị xoá")`.

---

## 12. Security
- Mặt nạ hoá (mask) cookie trong toàn bộ log: `CookieSessionManager` chỉ ghi nhận độ dài hoặc các ký tự đầu/cuối của token.
- File `douyin_cookies.json` được loại trừ trong `.gitignore`.

---

## 13. Performance
- Streaming buffer: **256 KB** (`256 * 1024` bytes) tối ưu I/O throughput trên hệ thống Windows.
- Tốc độ tải mục tiêu: **30 – 50+ MB/s** đối với đường truyền cáp quang thông thường.
- Thời gian lấy thông tin metadata: **< 1.0 giây**.

---

## 14. Testing (Kế hoạch kiểm thử)
- **Unit Tests**:
  - `test_abogus_generation`: Xác minh chuỗi `a_bogus` được tạo ra đúng cấu trúc.
  - `test_api_client_parsing`: Mock response Douyin detail JSON, kiểm tra bóc tách bitrate cao nhất.
  - `test_douyin_engine_resume`: Kiểm tra resume tải dở dang.
  - `test_pcdn_guard_timeout`: Kiểm tra ngắt kết nối nhanh khi node chậm.
  - `test_media_validator_integration`: Xác thực file tải về qua ffprobe.
- **Integration Test**: Tải thử nghiệm video Douyin thực tế.

---

## 15. Migration / Rollback
- Vì kiến trúc sử dụng adapter facade, nếu engine mới gặp sự cố ngoài dự kiến, hệ thống có thể chuyển cờ `use_legacy_engine=True` trong cấu hình để quay lại scraper cũ mà không cần sửa code.

---

## 16. File dự kiến thay đổi
1. `autodub/media/download/douyin/__init__.py` [NEW]
2. `autodub/media/download/douyin/a_bogus.py` [NEW]
3. `autodub/media/download/douyin/api_client.py` [NEW]
4. `autodub/media/download/douyin/stream_downloader.py` [NEW]
5. `autodub/media/download/douyin/cookie_fetcher.py` [NEW]
6. `autodub/media/download/douyin_engine.py` [MODIFY]
7. `autodub/media/douyin.py` [MODIFY]
8. `tests/test_douyin_engine.py` [MODIFY]

---

## 17. File không được tự ý thay đổi
- `autodub/pipeline.py` (Pipeline downstream).
- `autodub/speech/*` (Paraformer, ASR, Alignment, TTS).
- `autodub/text/*` (Dịch thuật AI, Gemini, Subtitle).
- `autodub/media/audio.py`, `vocal_separator.py` (Demucs).

---

## 18. Rủi ro & Giải pháp phòng ngừa
- **Rủi ro Douyin nâng cấp thuật toán WAF**: Luôn duy trì lớp fallback cấp 2 `BrowserPool` để bắt network request trực tiếp từ trình duyệt khi API bị chặn.
- **Rủi ro thiếu thư viện `gmssl`**: Đã cài đặt `gmssl` vào môi trường Python và thuật toán `a_bogus` được bao bọc `try/except` an toàn.

---

## 19. Các phương án đã cân nhắc
1. *Gọi subprocess sang `D:\Project\douyin-downloader\run.py`*: Nhược điểm là phụ thuộc vào 2 môi trường Python riêng biệt, khó quản lý tiến trình và IPC phức tạp.
2. *Nhúng trực tiếp lõi V2 vào package nội bộ `autodub/media/download/douyin/`*: **Được chọn** vì đóng gói hoàn chỉnh, nhẹ, tốc độ cao nhất, độc lập và dễ bảo trì.

---

## 20. Quyết định thiết kế
- Chọn **Phương án 2 (Nhúng lõi V2 trực tiếp)**.
- Kết hợp `a_bogus` + Session Cookies làm kênh tải chính (Direct API V2).
- Giữ nguyên hợp đồng `DownloadResult` và chuẩn hóa 100% tiếng Việt cho giao diện/log.

---

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ`
