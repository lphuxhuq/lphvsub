> [!IMPORTANT]
> **STATUS KIỂM TOÁN 2026-09-10: CANCELLED / SUPERSEDED**
> Kế hoạch Douyin V2 (a_bogus + gmssl SM3) bỏ dở ở TASK-001 — không có `download/douyin/`, không có `tests/test_douyin_v2_core.py`.
> Minh chứng: Thay thế bằng: `autodub/media/download/douyin_engine.py` (Playwright + cookie, đã tích hợp Smart Download Engine, `tests/test_douyin_engine.py` pass). Quyết định không theo hướng ký a_bogus thuần Python.

# Task Breakdown: Tích Hợp Douyin Downloader V2 & Việt Hoá

- **Mã kế hoạch**: `TASK-SMART-DOWNLOAD-ENGINE-DOUYIN-V2`
- **Mục tiêu**: Chia nhỏ thiết kế đã duyệt thành 4 unit độc lập, test-first, đảm bảo tính toàn vẹn và không gây hồi quy.

---

## 1. Dependency Graph

```text
TASK-001: Lõi Ký a_bogus & API Client Douyin V2
   │
   ▼
TASK-002: Streaming Downloader (256KB Chunk, PCDN Guard) & Cookie Fetcher
   │
   ▼
TASK-003: Nâng cấp DouyinDownloader Engine & Tích Hợp Resume/Validation/Việt Hoá
   │
   ▼
TASK-004: Cập nhật Facade Adapter, End-to-End Tests & Benchmark
```

---

## 2. Danh sách Unit

### TASK-001 — Lõi Ký a_bogus & API Client Douyin V2

**Mục tiêu:**
- Triển khai module tính chữ ký bảo mật `a_bogus` độc lập bằng Python thuần (kết hợp SM3 từ `gmssl`).
- Xây dựng `DouyinApiClient` gửi yêu cầu đến endpoint `/aweme/v1/web/aweme/detail/`, tự động bóc tách link video nét nhất không watermark và metadata.

**Dependency:** Không.

**File được phép sửa/tạo mới:**
- `autodub/media/download/douyin/__init__.py` [NEW]
- `autodub/media/download/douyin/a_bogus.py` [NEW]
- `autodub/media/download/douyin/api_client.py` [NEW]
- `tests/test_douyin_v2_core.py` [NEW]

**File không được sửa:**
- `autodub/media/downloader.py`
- `autodub/media/douyin.py`
- Toàn bộ pipeline downstream.

**Thay đổi dự kiến:**
- Tạo class `ABogusSigner` tạo tham số `a_bogus` chuẩn.
- Tạo class `DouyinApiClient` xử lý gọi HTTP, parse JSON response, phân loại lỗi 403 / anti-bot.

**Acceptance Criteria:**
- [ ] AC-1.1: `ABogusSigner.generate_a_bogus()` sinh chuỗi chữ ký hợp lệ khi nhận query string.
- [ ] AC-1.2: `DouyinApiClient` parse đúng mock data Douyin detail, trả về video URL không watermark và metadata (title, author, duration).
- [ ] AC-1.3: Nhận diện và ném ngoại lệ rõ ràng khi gặp lỗi 403 / anti-bot.

**Test:**
- Viết `tests/test_douyin_v2_core.py` kiểm tra sinh chữ ký và trích xuất URL.

**Rủi ro:** Thuật toán `a_bogus` cần thư viện `gmssl` (đã cài đặt).

**Rollback:** Xoá thư mục `autodub/media/download/douyin/` và file test.

---

### TASK-002 — Streaming Downloader (256KB Chunk, PCDN Guard) & Cookie Fetcher Việt Hoá

**Mục tiêu:**
- Xây dựng `DouyinStreamDownloader` tải streaming async với buffer 256KB, tích hợp PCDN Guard ngắt node chậm sau 5s.
- Xây dựng `DouyinCookieFetcher` qua Playwright để tự động bắt cookie, có hướng dẫn tiếng Việt rõ ràng.

**Dependency:** TASK-001.

**File được phép sửa/tạo mới:**
- `autodub/media/download/douyin/stream_downloader.py` [NEW]
- `autodub/media/download/douyin/cookie_fetcher.py` [NEW]
- `tests/test_douyin_stream_downloader.py` [NEW]

**File không được sửa:**
- `autodub/media/download/douyin_engine.py`
- Pipeline downstream.

**Thay đổi dự kiến:**
- Viết `DouyinStreamDownloader` hỗ trợ callback báo cáo tiến trình tiếng Việt (% hoàn thành, tốc độ MB/s, ETA).
- Tích hợp timeout 5s ngắt kết nối với các node CDN đen/chậm (`*.qtaeixd.com`).
- Viết script `cookie_fetcher.py` mở Chromium headless/headed, hướng dẫn người dùng bằng tiếng Việt và lưu `~/.autodub/douyin_cookies.json`.

**Acceptance Criteria:**
- [ ] AC-2.1: `DouyinStreamDownloader` tải stream theo từng chunk 256KB, cập nhật đúng số byte và tốc độ.
- [ ] AC-2.2: PCDN Guard phát hiện node chậm và tự động timeout sau 5s thay vì chờ 300s.
- [ ] AC-2.3: `DouyinCookieFetcher` hỗ trợ đọc/ghi cookie hợp lệ từ/vào tệp JSON.

**Test:**
- Viết `tests/test_douyin_stream_downloader.py` kiểm tra streaming và timeout guard.

**Rủi ro:** Môi trường không có GUI khi chạy `cookie_fetcher` (hỗ trợ cả cờ `--headless` và hướng dẫn thủ công).

**Rollback:** Revert `stream_downloader.py` và `cookie_fetcher.py`.

---

### TASK-003 — Nâng cấp DouyinDownloader Engine, Tích Hợp Resume, Validation & Việt Hoá Log

**Mục tiêu:**
- Tái cấu trúc `DouyinDownloader` trong `autodub/media/download/douyin_engine.py`:
  - Kết nối với `DouyinApiClient` (Direct API V2 làm kênh chính).
  - Tích hợp `PartialDownloadManager` (tải tiếp file `.part`, ghi nhận `.progress.json`).
  - Fallback sang `BrowserPool` nếu gặp CAPTCHA trượt.
  - Kiểm tra file bằng `MediaValidator` (ffprobe).
  - Chuẩn hoá 100% tiếng Việt cho nhật ký console và thanh tiến trình.

**Dependency:** TASK-001, TASK-002.

**File được phép sửa:**
- `autodub/media/download/douyin_engine.py` [MODIFY]
- `tests/test_douyin_engine.py` [MODIFY]

**File không được sửa:**
- `autodub/pipeline.py`
- Các module khác ngoài download subsystem.

**Thay đổi dự kiến:**
- Thay thế cơ chế mobile scraper cũ bằng quy trình 3 cấp độ: `Direct API V2 -> BrowserPool -> yt-dlp`.
- Tự động nạp cookie từ `CookieSessionManager` / `douyin_cookies.json`.
- Trả về `DownloadResult` đúng chuẩn contract.

**Acceptance Criteria:**
- [ ] AC-3.1: Gọi `DouyinDownloader.download()` thành công qua `Direct API V2` trả về `DownloadResult(success=True, backend="direct_api_v2")`.
- [ ] AC-3.2: Tải dở dang được tiếp tục mà không xóa file `.part`.
- [ ] AC-3.3: Sau khi tải, `MediaValidator` kiểm tra thành công video và audio.
- [ ] AC-3.4: Toàn bộ log console hiển thị bằng tiếng Việt thân thiện.

**Test:**
- Cập nhật và chạy `tests/test_douyin_engine.py`.

**Rủi ro:** Không phá vỡ tương thích với `decision_engine.py`.

**Rollback:** `git checkout autodub/media/download/douyin_engine.py`.

---

### TASK-004 — Cập Nhật Facade Adapter, End-to-End Tests & Benchmark

**Mục tiêu:**
- Cập nhật facade `autodub/media/douyin.py` và router `autodub/media/downloader.py` chuyển tiếp mượt mà sang engine mới.
- Chạy toàn bộ regression test suite (1290+ tests).
- Chạy benchmark đo đạc tốc độ OLD vs NEW và xuất báo cáo nghiệm thu.

**Dependency:** TASK-001, TASK-002, TASK-003.

**File được phép sửa/tạo mới:**
- `autodub/media/douyin.py` [MODIFY]
- `autodub/media/downloader.py` [MODIFY]
- `scripts/benchmark_douyin_v2.py` [NEW]
- `.artifacts/reviews/final-audit-douyin-v2-upgrade.md` [NEW]

**Acceptance Criteria:**
- [ ] AC-4.1: Các caller cũ (`download_douyin`, `download_video`) hoạt động ổn định và hưởng trọn tốc độ của engine mới.
- [ ] AC-4.2: 100% test suite trong `tests/` pass, không có lỗi hồi quy.
- [ ] AC-4.3: Benchmark thực tế chứng minh tốc độ tải Douyin đạt 30–50+ MB/s, thời gian hoàn tất giảm > 70% so với bản cũ.

**Test:**
- `pytest tests/test_download_*.py tests/test_douyin_*.py -v`.
- Chạy script benchmark thực tế.

**Rollback:** `git checkout autodub/media/douyin.py autodub/media/downloader.py`.

---

## 3. Thứ tự thực hiện

1. **TASK-001**: Lõi Ký a_bogus & API Client Douyin V2.
2. **TASK-002**: Streaming Downloader (256KB Chunk, PCDN Guard) & Cookie Fetcher.
3. **TASK-003**: Nâng cấp DouyinDownloader Engine & Tích Hợp Resume/Validation/Việt Hoá.
4. **TASK-004**: Cập nhật Facade Adapter, End-to-End Tests & Benchmark.

---

## 4. Change Budget

- Tổng số file mới: 6 file (thuộc package `autodub/media/download/douyin/`, tests và script benchmark).
- Tổng số file sửa đổi: 3 file (`douyin_engine.py`, `douyin.py`, `downloader.py`).
- Giới hạn dòng code thay đổi trong core: < 400 dòng mới, không sửa đổi bất kỳ file downstream pipeline nào.

---

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT TASK`
