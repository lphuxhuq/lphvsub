# Đặc Tả Yêu Cầu — Turbo + Reliable Smart Download Engine (Bilibili + Douyin V2 Việt Hoá)

- **Mã tính năng**: `SMART-DOWNLOAD-ENGINE-DOUYIN-V2`
- **Mục tiêu**: Tích hợp lõi Douyin Downloader V2 (với thuật toán sinh chữ ký `a_bogus`, streaming chunk 256KB, PCDN anti-blackhole guard, tự động bắt cookie Playwright) vào kiến trúc Smart Download Engine của `lphvsub-main`, thay thế hoàn toàn cơ chế cào HTML mobile cũ; đồng thời Việt hoá 100% trải nghiệm tải (log, tiến trình, giao diện, thông báo lỗi).

---

## 1. Bối cảnh & Vấn đề hiện tại
1. **Douyin Engine hiện tại (`autodub/media/douyin.py` & `douyin_engine.py`)**:
   - Dựa trên việc cào regex HTML mobile (`_ROUTER_DATA_RE`, `_RENDER_DATA_RE`), cấu trúc trang web Douyin thường xuyên thay đổi và trả về trang trắng khiến scraper thất bại.
   - Khi cào HTML thất bại, engine cũ khởi chạy một tiến trình Chromium mới để bắt network request MP4, gây độ trễ 5–10s khởi động, tốn RAM/CPU và có nguy cơ sinh orphan Chromium process khi người dùng hủy.
   - Chưa tích hợp cơ chế sinh chữ ký `a_bogus` chính thống, nên không thể gọi trực tiếp endpoint `/aweme/v1/web/aweme/detail/`.
   - Chưa có công cụ quản lý Cookie tự động bằng tiếng Việt; người dùng gặp lỗi 403 / anti-bot không biết cách khắc phục.
2. **Bilibili Engine hiện tại (`bilibili_engine.py`)**:
   - Đã có DASH + Progressive + CDN Racing và Adaptive Concurrency, nhưng cần đồng bộ hóa contract với Douyin V2.
3. **Yêu cầu Việt hoá**:
   - Toàn bộ log console, tiến trình tải, hướng dẫn cập nhật cookie và thông báo lỗi hiện đang lẫn lộn tiếng Trung/tiếng Anh, cần chuẩn hoá sang tiếng Việt thân thiện, chuyên nghiệp.

---

## 2. User Story
- **Là người dùng LPHVSub**: Tôi muốn dán bất kỳ liên kết Douyin nào (link ngắn `v.douyin.com`, link web `douyin.com/video/...`, link modal `modal_id=...`, link gallery ảnh) hoặc Bilibili vào ứng dụng và tải video gốc chất lượng cao nhất không logo chỉ trong 1–3 giây.
- **Khi chưa có Cookie hoặc Cookie hết hạn**: Tôi muốn hệ thống hiển thị thông báo tiếng Việt rõ ràng, cung cấp tính năng mở trình duyệt tự động để tôi đăng nhập lấy Cookie chỉ với 1 click/lệnh, tự động lưu và dùng ngay.
- **Khi mạng chập chờn**: Quá trình tải không bị xóa file bắt đầu lại từ 0, mà tự động tải tiếp phần dang dở (Resume) và tự ngắt kết nối với các node CDN chậm/nghẽn.

---

## 3. Functional Requirements (Yêu cầu chức năng)

### FR-01: Lõi Tải Douyin V2 Trực Tiếp (Direct API + `a_bogus` Signer)
- Tích hợp thuật toán tính chữ ký `a_bogus` động trực tiếp từ Python, loại bỏ hoàn toàn sự phụ thuộc vào việc mở trình duyệt cho mỗi lượt tải thông thường.
- Gửi yêu cầu chuẩn đến endpoint chính thức `/aweme/v1/web/aweme/detail/`.
- Tự động phân tích payload trả về:
  - Chọn bitrate cao nhất (`video.bit_rate`) không dính watermark.
  - Trích xuất đầy đủ metadata (tiêu đề, tác giả, cover, thời lượng, âm thanh).
  - Hỗ trợ cả video thông thường và bài đăng album ảnh (note/gallery).

### FR-02: Streaming Chunk 256KB + PCDN Anti-Blackhole Guard
- Sử dụng I/O bất đồng bộ với buffer chunk tối ưu 256KB (`_DOWNLOAD_CHUNK_BYTES = 256 * 1024`).
- Tích hợp cơ chế phát hiện và ngắt kết nối nhanh (< 5 giây) đối với các node PCDN nội địa Trung Quốc (`*.qtaeixd.com`) bị nghẽn mạng/blackhole, tự động chuyển hướng sang CDN chính thống.
- Hỗ trợ resume thông qua `Range: bytes=X-` và lưu vết `.progress.json` qua `PartialDownloadManager`.

### FR-03: Trình Quản Lý & Tự Động Lấy Cookie Douyin Việt Hoá
- Xây dựng module `CookieSessionManager` & `DouyinCookieFetcher`:
  - Cho phép chạy độc lập qua lệnh: `python -m autodub.media.download.cookie_fetcher`
  - Hoặc kích hoạt từ giao diện PyQt6.
  - Tự động khởi chạy Playwright Chromium mở trang Douyin, hướng dẫn người dùng quét mã/đăng nhập bằng tiếng Việt, tự động lưu cookie vào hệ thống (`env_store` / `config.yml`).
  - Tự động nạp cookie khi gọi API để tránh bị chặn 403 / anti-bot.

### FR-04: Bộ Điều Phối Quyết Định Tải Tự Động (DownloadDecisionEngine)
- Bổ sung routing Douyin V2 vào `DecisionEngine`:
  - **Cấp 1**: Kiểm tra `DownloadCache` (nếu đã tải và còn file hợp lệ trên đĩa → Cache Hit tức thì).
  - **Cấp 2**: Direct API với chữ ký `a_bogus` + Session Cookie (tốc độ cao nhất, ~1-2s).
  - **Cấp 3**: BrowserPool Chromium sniffing fallback (chỉ kích hoạt nếu API bị chặn CAPTCHA nâng cao).
  - **Cấp 4**: yt-dlp generic fallback.

### FR-05: Việt Hoá Toàn Diện (Full Vietnamese Localization)
- 100% thông báo trạng thái, nhật ký tiến trình (ETA, tốc độ MB/s), hướng dẫn cookie và thông báo lỗi được hiển thị bằng tiếng Việt:
  - `Đang khởi tạo cơ sở dữ liệu tải...`
  - `Đã nhận diện liên kết Douyin: ID {aweme_id}`
  - `Đang trích xuất liên kết không logo với chữ ký a_bogus...`
  - `Đang tải video [██████████████░░░░] 72% | 38.5 MB/s | Còn lại: 00:02`
  - `Tải hoàn tất sau 1.8s! Đang xác thực toàn vẹn bằng ffprobe...`
  - `Cảnh báo: Cookie Douyin chưa được cấu hình hoặc đã hết hạn. Vui lòng bấm Cập nhật Cookie.`

### FR-06: Chuẩn Hóa Kết Quả DownloadResult & Tương Thích Ngược
- Trả về `DownloadResult` đúng chuẩn:
  ```python
  DownloadResult(
      success=True,
      path=...,
      platform="douyin",
      media_id=...,
      duration=...,
      width=...,
      height=...,
      fps=...,
      video_codec=...,
      audio_codec=...,
      file_size=...,
      elapsed_seconds=...,
      average_speed=...,
      peak_speed=...,
      retries=...,
      backend="direct_api_v2",
      cdn=...,
      resumed=...,
      cache_hit=...,
      validation_passed=True,
  )
  ```
- Duy trì 100% tương thích ngược với các caller hiện có (`download_video`, `download_one`, `download_one_isolated`).
- Sau khi tải, tự động chuyển tiếp mượt mà vào downstream pipeline: ASR (Paraformer/Whisper) → Dịch thuật (Gemini) → TTS → Subtitle/Alignment → Render.

---

## 4. Non-functional Requirements (Yêu cầu phi chức năng)
- **NFR-01: Hiệu năng (Speed)**:
  - Tốc độ giải mã URL và trích xuất link tải: < 1.0 giây.
  - Tốc độ tải thực tế: 30 – 60 MB/s (tải video 50MB trong 1 – 2 giây).
- **NFR-02: Độ ổn định & Tự phục hồi (Reliability & Self-recovering)**:
  - Retry có exponential backoff và jitter, giới hạn tối đa 3 lần cho lỗi mạng tạm thời.
  - Không bao giờ xóa file `.part` khi lỗi mạng; hỗ trợ resume tiếp tục.
  - Xác thực nghiêm ngặt bằng ffprobe (`MediaValidator`) trước khi giao file cho pipeline downstream; không bao giờ trả file rác/file lỗi.
- **NFR-03: Quản lý tài nguyên & Đơn tiến trình**:
  - Tái sử dụng kết nối HTTP (`aiohttp.ClientSession` / `requests.Session`).
  - Không để lại orphan process Chromium khi người dùng cancel hoặc đóng app.

---

## 5. Hành vi hiện tại vs Hành vi mới

| Đặc tính | Hiện tại | Mới (Douyin V2 + Smart Engine) |
| :--- | :--- | :--- |
| **Cơ chế phân giải Douyin** | Cào mobile HTML regex, dễ lỗi trang trắng | Gọi API chính thức `/aweme/v1/...` có chữ ký `a_bogus` |
| **Fallback khi lỗi** | Mở Playwright Chromium mới tinh cho mỗi URL | Dùng Chromium Singleton Pool / Cookie Fetcher tự động |
| **Xử lý ngắt kết nối mạng** | Có thể xóa `.part` hoặc mất tiến trình | Lưu `.progress.json`, tiếp tục tải bằng HTTP Range |
| **Xử lý node CDN chậm** | Bị treo kết nối chờ timeout đến 300s | PCDN Guard phát hiện node `*.qtaeixd.com` ngắt sau 5s |
| **Tốc độ tải video 50MB** | 8 – 20 giây | 1 – 3 giây (30 – 50+ MB/s) |
| **Ngôn ngữ hiển thị** | Tiếng Trung / Tiếng Anh | 100% Tiếng Việt thân thiện, rõ ràng |
| **Xác thực sau tải** | Không bắt buộc | `MediaValidator` kiểm tra ffprobe toàn diện |

---

## 6. Module bị ảnh hưởng
1. `autodub/media/download/douyin/`: Thư mục package mới chứa lõi thuật toán V2:
   - `a_bogus.py`: Thuật toán sinh chữ ký `a_bogus`.
   - `api_client.py`: API client giao tiếp Douyin web endpoint.
   - `cookie_fetcher.py`: Trình lấy cookie tự động bằng tiếng Việt qua Playwright.
2. `autodub/media/download/douyin_engine.py`: Nâng cấp để sử dụng lõi Douyin V2 + tích hợp `PartialDownloadManager` + `MediaValidator`.
3. `autodub/media/douyin.py`: Cập nhật wrapper chuyển tiếp cuộc gọi sang engine mới.
4. `autodub/media/downloader.py`: Cập nhật router và chuẩn hoá URL.
5. `tests/test_douyin_engine.py`: Bổ sung test cases kiểm tra API V2, `a_bogus`, resume, error handling và validation.

---

## 7. Dependency
- `aiohttp >= 3.9.0` (đã có trong môi trường).
- `playwright` (đã cài đặt).
- `ffprobe` / `ffmpeg` (đã có trong hệ thống).
- Không thêm bất kỳ thư viện ngoài không cần thiết nào.

---

## 8. Constraint & Guardrails
- Không thay đổi interface công khai của `downloader.py` để không phá vỡ GUI hoặc pipeline CLI.
- Không sửa đổi mã nguồn bên ngoài phạm vi download subsystem.
- Mã nguồn phải hoàn toàn tương thích môi trường Windows (UTF-8 console, không dính lỗi `charmap`).

---

## 9. Edge Cases
1. Link Douyin dạng modal URL: `.../jingxuan?modal_id=7681994993862577444`.
2. Link rút gọn trên mobile: `https://v.douyin.com/xxxxxx/`.
3. Link kèm caption tiếng Trung dài khi copy từ app điện thoại.
4. Bài đăng album ảnh (Note / Gallery / Live Photo).
5. Video bị xoá hoặc đặt chế độ riêng tư (báo lỗi tiếng Việt chi tiết).
6. Cookie hết hạn giữa chừng (báo thông báo tiếng Việt kèm giải pháp).

---

## 10. Security
- Không log raw cookie hoặc token nhạy cảm ra file log hay terminal.
- File cookie được bảo vệ cục bộ, nằm trong danh sách `.gitignore`.

---

## 11. Acceptance Criteria (Tiêu chuẩn nghiệm thu)
- [ ] AC-01: Tải thành công video Douyin không watermark từ cả link rút gọn (`v.douyin.com`) lẫn link web (`modal_id=...`).
- [ ] AC-02: Tốc độ tải đạt chuẩn streaming chunk 256KB, thời gian tải video ~50MB trong khoảng 1–3 giây.
- [ ] AC-03: Resume hoạt động: Khi ngắt kết nối giữa chừng, lần tải tiếp theo tiếp tục từ byte dang dở thay vì tải từ đầu.
- [ ] AC-04: PCDN Guard hoạt động: Tự động ngắt và chuyển sang CDN khác nếu kết nối rơi vào node PCDN chậm.
- [ ] AC-05: Trình lấy cookie Playwright hoạt động trơn tru với hướng dẫn tiếng Việt 1-click.
- [ ] AC-06: 100% thông báo, log và thanh tiến trình được hiển thị bằng tiếng Việt chuẩn.
- [ ] AC-07: File sau khi tải vượt qua kiểm tra của `MediaValidator` (ffprobe xác thực luồng video/audio hợp lệ).
- [ ] AC-08: Toàn bộ test suite liên quan (`tests/test_download_*.py`, `tests/test_douyin_engine.py`) chạy PASS 100%.

---

## 12. Điểm chưa rõ (Open Questions)
1. **Nơi lưu trữ Cookie Douyin chính thức trong lphvsub-main:**
   - *Đề xuất*: Lưu vào `~/.autodub/douyin_cookies.json` hoặc trong file cấu hình dự án `config/douyin_cookies.json` (được gitignore). Khi khởi động app, `SessionManager` tự động nạp từ file này.
2. **Giao diện kích hoạt lấy Cookie:**
   - Cung cấp lệnh CLI: `python -m autodub.media.download.cookie_fetcher`
   - Bổ sung nút "Lấy Cookie Douyin Tự Động" trên giao diện cài đặt của GUI.

---

## 13. Ngoài phạm vi
- Không can thiệp vào các engine ngoài Douyin & Bilibili (YouTube, TikTok giữ nguyên yt-dlp).
- Không sửa đổi logic downstream (Whisper, Gemini translation, Demucs vocal separation).

---

## Approval Gate

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
