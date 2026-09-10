# Thanh Tiến Độ Phần Trăm Khi Tải Video (Douyin & Bilibili) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm thanh tiến độ hiển thị phần trăm (%), dung lượng MB và tốc độ mạng theo thời gian thực vào giao diện khi người dùng dán link tải video (hỗ trợ cả Bilibili, Douyin và các nền tảng khác).

**Architecture:** Bổ sung `progress_cb` xuyên suốt từ tầng lõi download (`PartialDownloadManager`, `BilibiliDownloader`, `download_douyin`, `download_video`) truyền lên `PrefetchWorker` và `DownloadWorker` qua Qt `Signal(float, str)`, sau đó cập nhật trực tiếp vào component `DownloadProgressBar` trên giao diện `VideoStep` (Bước 1) và nút `Tiếp tục`.

**Tech Stack:** Python 3.11, PySide6 (QProgressBar, QLabel, QThread Signals), requests (chunk streaming), yt-dlp (progress hooks), PartialDownloadManager.

---

### Task 1: Truyền Tín Hiệu Tiến Độ Từ Tầng Download Core (Bilibili & Douyin & yt-dlp)

**Files:**
- Modify: `autodub/media/download/bilibili_engine.py:120-250`
- Modify: `autodub/media/douyin.py:518-630`
- Modify: `autodub/media/downloader.py:224-330`
- Test: `tests/test_download_progress_callback.py`

**Interfaces:**
- `download_video(url, output_dir, progress_cb=None)`
- `download_douyin(url, output_dir, filename=None, progress_cb=None)`
- `BilibiliDownloader.download(request)` phát `request.progress_callback({"percent": pct, "speed_mb": speed, ...})`

- [ ] **Step 1: Viết test cho `progress_cb` trong `tests/test_download_progress_callback.py`**
- [ ] **Step 2: Cập nhật `autodub/media/douyin.py` để tính toán byte stream và gọi `progress_cb`**
- [ ] **Step 3: Cập nhật `autodub/media/download/bilibili_engine.py` để kết nối `progress_callback` trong DASH streams**
- [ ] **Step 4: Cập nhật `autodub/media/downloader.py` để nhận `progress_cb` và truyền cho Smart Download Engine / Douyin / yt-dlp**
- [ ] **Step 5: Chạy test xác nhận các callback hoạt động chuẩn xác**
- [ ] **Step 6: Git commit cho Task 1**

---

### Task 2: Cập Nhật Workers Phát Signal Tiến Độ Ra GUI

**Files:**
- Modify: `autodub_gui/workers.py:613-685` (DownloadWorker)
- Modify: `autodub_gui/workers.py:844-877` (PrefetchWorker)
- Test: `tests/test_prefetch_worker_progress.py`

**Interfaces:**
- `PrefetchWorker.progress = Signal(float, str)`
- `DownloadWorker.item_status = Signal(int, int, str, str, str)`

- [ ] **Step 1: Thêm `progress = Signal(float, str)` vào `PrefetchWorker`**
- [ ] **Step 2: Kết nối `progress_cb` trong `PrefetchWorker.run()` và `DownloadWorker.run()`**
- [ ] **Step 3: Viết test cho `PrefetchWorker` signal**
- [ ] **Step 4: Git commit cho Task 2**

---

### Task 3: Xây Dựng Component `DownloadProgressBar` & Tích Hợp Vào Giao Diện

**Files:**
- Modify: `autodub_gui/ui/progress.py` (tạo `DownloadProgressBar`)
- Modify: `autodub_gui/pages/new_project_steps.py` (nhúng vào `VideoStep`)
- Modify: `autodub_gui/pages/new_project_page.py` (kết nối worker signal với UI)
- Modify: `autodub_gui/pages/download_page.py` (hiển thị % tải trong bảng)

**Interfaces:**
- `DownloadProgressBar.set_progress(pct: float, message: str)`
- `DownloadProgressBar.set_finished(message: str)`
- `DownloadProgressBar.set_error(message: str)`
- `DownloadProgressBar.reset()`

- [ ] **Step 1: Xây dựng class `DownloadProgressBar` trong `autodub_gui/ui/progress.py`**
- [ ] **Step 2: Nhúng `DownloadProgressBar` vào `VideoStep` ngay dưới `url_badge`**
- [ ] **Step 3: Kết nối `worker.progress` với thanh tiến độ và cập nhật text nút `btn_next` trong `NewProjectPage`**
- [ ] **Step 4: Tự động khởi động tải trước (prefetch) khi người dùng dán link hợp lệ mà không cần chờ bấm Tiếp tục**
- [ ] **Step 5: Cập nhật hiển thị % trong bảng của `DownloadPage`**
- [ ] **Step 6: Kiểm thử giao diện và git commit**
