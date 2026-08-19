# Tích Hợp Gemini SRT UI Vào LPH VSub (VoxDub Studio) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tích hợp trọn bộ công cụ dịch phụ đề chuyên sâu `gemini-srt-ui` vào `lphvsub-main`, cho phép chạy trực tiếp từ giao diện chính VoxDub Studio (mục Công cụ) và chạy độc lập qua script `chay_dich_srt.bat`.

**Architecture:** Đóng gói backend Flask và frontend web của `gemini-srt-ui` thành một module công cụ bên trong `autodub.tools.gemini_srt_ui`, đồng bộ cấu hình API Keys và cài đặt từ `.env` của `lphvsub-main`, quản lý vòng đời server qua `GeminiSrtServerManager`, tạo trang giao diện `GeminiSrtPage` trong `autodub_gui` (danh mục CÔNG CỤ), và bổ sung launcher `chay_dich_srt.bat`.

**Tech Stack:** Python 3.10+, PySide6 (Qt for Python), Flask, Werkzeug, pysubs2, google-genai, gemini-srt-translator, pytest.

## Global Constraints

- Không làm gián đoạn hay phá vỡ các chức năng cốt lõi hiện có của `lphvsub-main` (pipeline, editor, batch, download, voice).
- Tự động đồng bộ các khóa `GEMINI_API_KEYS` từ `.env` của VoxDub sang Gemini SRT Tool mà không bắt người dùng nhập lại.
- Quản lý luồng Flask server ở background sạch sẽ, tự động tắt khi đóng ứng dụng để tránh rò rỉ port / process.
- Hỗ trợ cả 2 chế độ: mở từ bên trong VoxDub GUI và chạy độc lập từ file `.bat`.

---

### Task 1: Thiết lập cấu trúc thư mục & sao chép mã nguồn công cụ

**Files:**
- Create: `autodub/tools/__init__.py`
- Create: `autodub/tools/gemini_srt_ui/__init__.py`
- Create: `autodub/tools/gemini_srt_ui/app.py`
- Create: `autodub/tools/gemini_srt_ui/static/index.html`
- Modify: `requirements.txt`
- Test: `tests/test_gemini_srt_module.py`

**Interfaces:**
- Produces: `autodub.tools.gemini_srt_ui.app.create_app(env_path: Optional[str] = None) -> Flask`

- [ ] **Step 1: Write the failing test for module loading and Flask app creation**

```python
# tests/test_gemini_srt_module.py
import pytest

def test_gemini_srt_module_importable():
    from autodub.tools.gemini_srt_ui import create_app
    app = create_app()
    assert app is not None
    assert app.name == "autodub.tools.gemini_srt_ui.app" or "gemini" in app.name

def test_gemini_srt_static_index_exists():
    from autodub.tools.gemini_srt_ui import get_static_folder
    import os
    static_dir = get_static_folder()
    assert os.path.isdir(static_dir)
    assert os.path.isfile(os.path.join(static_dir, "index.html"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gemini_srt_module.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'autodub.tools'"

- [ ] **Step 3: Copy and adapt backend/frontend files and update requirements.txt**

1. Tạo thư mục `autodub/tools/gemini_srt_ui/static`
2. Cập nhật `requirements.txt` thêm:
   ```text
   flask>=3.0.0
   werkzeug>=3.0.0
   pysubs2>=1.7.0
   google-genai>=1.0.0
   gemini-srt-translator>=3.7.0
   ```
3. Chuyển đổi `d:\Project\gemini-srt-ui\app.py` thành `autodub/tools/gemini_srt_ui/app.py` với hàm `create_app()` factory và hàm `get_static_folder()`.
4. Sao chép `d:\Project\gemini-srt-ui\static\index.html` sang `autodub/tools/gemini_srt_ui/static/index.html`.
5. Tạo `autodub/tools/__init__.py` và `autodub/tools/gemini_srt_ui/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gemini_srt_module.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add requirements.txt autodub/tools tests/test_gemini_srt_module.py
git commit -m "feat: add gemini_srt_ui tool module and assets"
```

---

### Task 2: Xây dựng Server Manager & Đồng bộ Cấu hình VoxDub

**Files:**
- Create: `autodub/tools/gemini_srt_ui/server_manager.py`
- Modify: `autodub/tools/gemini_srt_ui/app.py`
- Test: `tests/test_gemini_srt_server.py`

**Interfaces:**
- Produces: 
  - `class GeminiSrtServerManager:`
    - `start(port: int = 5050, open_browser: bool = False) -> str` (trả về URL server)
    - `stop() -> None`
    - `is_running() -> bool`
    - `get_url() -> str`
    - `sync_settings_from_env() -> None`

- [ ] **Step 1: Write the failing test for Server Manager**

```python
# tests/test_gemini_srt_server.py
import pytest
import time
import requests
from autodub.tools.gemini_srt_ui.server_manager import GeminiSrtServerManager

def test_server_manager_lifecycle():
    manager = GeminiSrtServerManager()
    assert not manager.is_running()
    
    url = manager.start(port=5999, open_browser=False)
    assert manager.is_running()
    assert "5999" in url
    
    time.sleep(1)
    # Ping server root
    resp = requests.get(url, timeout=3)
    assert resp.status_code == 200
    
    manager.stop()
    assert not manager.is_running()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gemini_srt_server.py -v`
Expected: FAIL with "No module named 'autodub.tools.gemini_srt_ui.server_manager'"

- [ ] **Step 3: Implement GeminiSrtServerManager with threading and sync**

1. Viết `server_manager.py` sử dụng `werkzeug.serving.make_server` chạy trên background thread an toàn (daemon thread).
2. Tự động đọc cấu hình `GEMINI_API_KEYS`, `GEMINI_MODEL`, `PROXY` từ `autodub.config.Settings` hoặc `.env` và cung cấp endpoint `/api/config/sync` hoặc nạp mặc định vào UI.
3. Cho phép tự tìm port trống nếu port mặc định (5050) đang bị chiếm.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gemini_srt_server.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autodub/tools/gemini_srt_ui/server_manager.py autodub/tools/gemini_srt_ui/app.py tests/test_gemini_srt_server.py
git commit -m "feat: implement GeminiSrtServerManager with config synchronization"
```

---

### Task 3: Tích hợp trang Công cụ vào `autodub_gui`

**Files:**
- Create: `autodub_gui/pages/gemini_srt_page.py`
- Modify: `autodub_gui/app.py:35-125,270-360`
- Modify: `autodub_gui/pages/__init__.py`
- Test: `tests/test_gemini_srt_gui_page.py`

**Interfaces:**
- Produces: `class GeminiSrtPage(BasePage)`
- Modifies: `ROW_GEMINI_SRT` in `autodub_gui.app.PAGES`

- [ ] **Step 1: Write failing test for GUI Page initialization**

```python
# tests/test_gemini_srt_gui_page.py
import pytest
from PySide6.QtWidgets import QApplication
from autodub_gui.pages.gemini_srt_page import GeminiSrtPage
from autodub.config import Settings

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

def test_gemini_srt_page_construct(qapp):
    page = GeminiSrtPage(Settings.load)
    assert page is not None
    assert hasattr(page, "server_manager")
    assert hasattr(page, "cleanup")
    assert hasattr(page, "shutdown")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gemini_srt_gui_page.py -v`
Expected: FAIL with "No module named 'autodub_gui.pages.gemini_srt_page'"

- [ ] **Step 3: Implement `GeminiSrtPage` and register in `autodub_gui/app.py`**

1. Tạo `autodub_gui/pages/gemini_srt_page.py`:
   - Giao diện thẻ công cụ hiện đại, hiển thị trạng thái Server, URL Localhost, số lượng API Key đã nạp sẵn từ hệ thống.
   - Nút hành động nổi bật: "Mở Trình Dịch Web trong Trình Duyệt" (`PrimaryButton`).
   - Nút "Khởi động lại Server" / "Dừng Server".
   - Tích hợp hướng dẫn sử dụng nhanh các tính năng (Multi-key pool, Auto CJK, Subtitle Editor).
   - Quản lý `shutdown()` và `cleanup()` dừng `server_manager`.
2. Khai báo `ROW_GEMINI_SRT = 14` (cập nhật `PAGE_COUNT = 15`) và thêm vào `PAGES` trong `autodub_gui/app.py`:
   ```python
   (ROW_GEMINI_SRT, "Dịch SRT Gemini", "Dịch SRT Gemini Pro",
    "Công cụ web dịch phụ đề chuyên sâu với Multi-key & CJK Fix",
    icons.globe, "tools"),
   ```
3. Cập nhật `_create_page` trong `autodub_gui/app.py` để dựng `GeminiSrtPage`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gemini_srt_gui_page.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autodub_gui/pages/gemini_srt_page.py autodub_gui/app.py tests/test_gemini_srt_gui_page.py
git commit -m "feat: integrate Gemini SRT tool page into VoxDub GUI"
```

---

### Task 4: Tạo Launcher Độc Lập `chay_dich_srt.bat` & Cập Nhật Cài Đặt

**Files:**
- Create: `chay_dich_srt.bat`
- Modify: `cai_dat.bat`
- Modify: `README.md`
- Test: `tests/test_standalone_launcher.py`

**Interfaces:**
- Produces: `chay_dich_srt.bat` (Batch script khởi chạy nhanh `python -m autodub.tools.gemini_srt_ui`)

- [ ] **Step 1: Write test verifying CLI module execution**

```python
# tests/test_standalone_launcher.py
import subprocess
import sys

def test_gemini_srt_cli_help():
    res = subprocess.run([sys.executable, "-m", "autodub.tools.gemini_srt_ui", "--help"],
                         capture_output=True, text=True)
    assert res.returncode == 0
    assert "Gemini SRT" in res.stdout or "port" in res.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_standalone_launcher.py -v`
Expected: FAIL with "No module named autodub.tools.gemini_srt_ui.__main__"

- [ ] **Step 3: Create `__main__.py`, `chay_dich_srt.bat`, and update documentation**

1. Tạo `autodub/tools/gemini_srt_ui/__main__.py` hỗ trợ đối số dòng lệnh `--port`, `--no-browser`, `--host`.
2. Tạo `chay_dich_srt.bat` để người dùng nhấp đúp là mở ngay giao diện Web trên trình duyệt mặc định.
3. Cập nhật `cai_dat.bat` để cài đặt các gói thư viện mới.
4. Cập nhật `README.md` hướng dẫn sử dụng công cụ Dịch SRT Gemini Pro.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_standalone_launcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autodub/tools/gemini_srt_ui/__main__.py chay_dich_srt.bat cai_dat.bat README.md tests/test_standalone_launcher.py
git commit -m "feat: add standalone launcher and CLI entrypoint for Gemini SRT tool"
```

---

### Task 5: Kiểm Tra Toàn Diện & Smoke Test

**Files:**
- Modify: `smoke_test_result.json` (sinh ra khi chạy smoke test)
- Test: Toàn bộ test suite `pytest tests/`

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run VoxDub smoke test**

Run: `python -m autodub_gui` (với biến môi trường `AUTODUB_SMOKE=1`)
Expected: Exit code 0, `smoke_test_result.json` có `"ok": true`.

- [ ] **Step 3: Commit final verification changes**

```bash
git commit -m "chore: verify full integration and pass smoke tests"
```
