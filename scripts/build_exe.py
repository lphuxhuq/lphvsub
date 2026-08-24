"""Đóng gói VoxDub Studio thành thư mục exe phân phối được.

Chạy từ project root với Python chính (đã cài đủ requirements + pyinstaller):

    py scripts/build_exe.py            # build + smoke test
    py scripts/build_exe.py --no-test  # chỉ build

Các bước:
  1. Đọc VOXDUB_API_URL từ .env của máy build → sinh
     autodub_gui/_embedded.py (địa chỉ máy chủ nhúng TRONG exe, không lộ ra
     file .env của người dùng). Khôi phục file rỗng sau khi build.
  2. PyInstaller onedir theo autodub.spec → build/, dist/VoxDub/
  3. Lắp ráp thư mục phân phối dist/VoxDub/:
       - scripts/setup_*.py + các file .bat cài đặt (VieNeu, Paraformer, Douyin)
       - HUONG_DAN_CAI_DAT.md (sinh từ script này)
       - .env.example (KHÔNG kèm .env thật)
       - models/ rỗng (điểm đến khi người dùng cài model)
  4. Smoke test: chạy VoxDub.exe với AUTODUB_SMOKE=1, đọc
     smoke_test_result.json, in kết quả từng mục.

Bản phân phối KHÔNG chứa: model, các venv phụ, ffmpeg — người dùng
cài theo HUONG_DAN_CAI_DAT.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMBEDDED_PY = os.path.join(PROJECT_ROOT, "autodub_gui", "_embedded.py")
DIST_DIR = os.path.join(PROJECT_ROOT, "dist", "VoxDub")

EMBEDDED_TEMPLATE = '''"""Giá trị nhúng cứng vào bản đóng gói (exe).

File này trong repo LUÔN rỗng. Khi build exe, ``scripts/build_exe.py`` sinh
lại nó với VOXDUB_API_URL đọc từ .env của máy build, rồi khôi phục về rỗng
sau khi build xong — địa chỉ máy chủ nằm TRONG exe, không lộ ra .env của
người dùng và người dùng không chỉnh được.
"""

# Rỗng = không nhúng; saas_client rơi về địa chỉ cố định trong mã, rồi tới
# biến môi trường VOXDUB_API_URL (chỉ khi chạy từ mã nguồn).
VOXDUB_API_URL = {url!r}
'''


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def _force_utf8_stdio() -> None:
    """Log tiếng Việt trên console cp1252 của Windows không được làm vỡ build."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def run(cmd: list[str], **kw) -> None:
    log("$ " + " ".join(os.path.basename(c) if os.sep in c else c for c in cmd[:8]))
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT, **kw)


# ------------------------------------------------------------------ steps --

def read_env_value(key: str) -> str:
    """Đọc 1 khóa từ .env của máy build (không dùng python-dotenv để script
    chạy được cả khi thiếu package)."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return ""
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.partition("=")[2].strip()
    return ""


def write_embedded(url: str) -> None:
    with open(EMBEDDED_PY, "w", encoding="utf-8") as f:
        f.write(EMBEDDED_TEMPLATE.format(url=url))


def step_embed_api_url() -> str:
    url = read_env_value("VOXDUB_API_URL")
    if url:
        log(f"nhúng VOXDUB_API_URL vào exe: {url}")
    else:
        log("(.env không có VOXDUB_API_URL — exe dùng địa chỉ cố định "
            "trong autodub/saas_client.py)")
    write_embedded(url)
    return url


def step_pyinstaller() -> None:
    # Xóa dist cũ để không lẫn file rác từ lần build trước.
    if os.path.isdir(DIST_DIR):
        log("xóa dist/VoxDub cũ...")
        try:
            shutil.rmtree(DIST_DIR)
        except PermissionError:
            raise SystemExit(
                "!! Không xóa được dist/VoxDub — đóng VoxDub.exe đang chạy, "
                "cửa sổ Explorer/terminal đang mở thư mục đó, rồi build lại.")
    log("chạy PyInstaller (vài phút)...")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         os.path.join(PROJECT_ROOT, "autodub.spec")])
    exe = os.path.join(DIST_DIR, "VoxDub.exe")
    if not os.path.isfile(exe):
        raise SystemExit(f"!! PyInstaller xong nhưng không thấy {exe}")


def step_assemble() -> None:
    log("lắp ráp thư mục phân phối...")

    # Script cài phần mở rộng (giọng đọc, ASR tiếng Trung, Douyin) chạy trên
    # máy người dùng — exe chỉ chứa phần lõi.
    scripts_dst = os.path.join(DIST_DIR, "scripts")
    os.makedirs(scripts_dst, exist_ok=True)
    for script in ("setup_vieneu.py", "setup_paraformer.py",
                   "setup_whisper.py", "setup_douyin.py",
                   "setup_gpu.py"):
        shutil.copy2(os.path.join(PROJECT_ROOT, "scripts", script),
                     scripts_dst)

    # Phiên bản Python của máy build — setup_douyin.py kiểm tra để libs/
    # (C-extension) khớp với python trong exe.
    with open(os.path.join(scripts_dst, "python_tag.txt"), "w",
              encoding="utf-8") as f:
        f.write(f"{sys.version_info[0]}.{sys.version_info[1]}\n")

    # .bat để người dùng đúp chuột là cài — không cần biết dòng lệnh.
    for name, content in (
            ("Cai dat giong VieNeu.bat", SETUP_VIENEU_BAT),
            ("Cai dat Whisper ASR.bat", SETUP_WHISPER_BAT),
            ("Cai dat ASR tieng Trung (Paraformer).bat", SETUP_PARAFORMER_BAT),
            ("Cai dat tinh nang Douyin.bat", SETUP_DOUYIN_BAT),
            ("Cai dat GPU tach nhac (Demucs).bat", SETUP_GPU_BAT)):
        with open(os.path.join(DIST_DIR, name), "w", encoding="utf-8") as f:
            f.write(content)

    # .env.example làm mẫu; TUYỆT ĐỐI không copy .env thật của máy build
    # (địa chỉ máy chủ đã nhúng trong exe).
    src_example = os.path.join(PROJECT_ROOT, ".env.example")
    if os.path.isfile(src_example):
        shutil.copy2(src_example, os.path.join(DIST_DIR, ".env.example"))

    for name in ("LICENSE",):
        src = os.path.join(PROJECT_ROOT, name)
        if os.path.isfile(src):
            shutil.copy2(src, DIST_DIR)

    # Thư mục models rỗng — đích đến của các script cài model.
    os.makedirs(os.path.join(DIST_DIR, "models"), exist_ok=True)

    # Giọng VieNeu: KHÔNG đóng gói voices/ hay custom_voices.json nữa.
    # App tự tải voices.zip từ GitHub release lần đầu chạy (voice_downloader).
    # Lý do: giảm kích thước exe ~60-100 MB, dễ update voices riêng biệt.
    log("voices/ và custom_voices.json KHÔNG đóng gói — app tự tải lần đầu")

    # Font kèm app: copy nguyên fonts/ (file .ttf/.otf + license + README).
    # Nằm CẠNH exe (không trong _internal) để người dùng tự thả thêm font
    # tải từ fonts.google.com mà không cần build lại.
    fonts_src = os.path.join(PROJECT_ROOT, "fonts")
    if os.path.isdir(fonts_src):
        shutil.copytree(fonts_src, os.path.join(DIST_DIR, "fonts"),
                        dirs_exist_ok=True)
        n_fonts = sum(1 for f in os.listdir(fonts_src)
                      if f.lower().endswith((".ttf", ".otf", ".ttc")))
        log(f"đã kèm {n_fonts} font trong fonts/")
    else:
        os.makedirs(os.path.join(DIST_DIR, "fonts"), exist_ok=True)

    with open(os.path.join(DIST_DIR, "HUONG_DAN_CAI_DAT.md"), "w",
              encoding="utf-8") as f:
        f.write(GUIDE_MD)

    # Đảm bảo không có .env nào lọt vào dist.
    stray = os.path.join(DIST_DIR, ".env")
    if os.path.isfile(stray):
        os.remove(stray)
        log("!! đã xóa .env lọt vào dist")


def step_restore_embedded() -> None:
    write_embedded("")
    log("khôi phục autodub_gui/_embedded.py về rỗng")


def step_smoke_test() -> bool:
    log("smoke test: chạy VoxDub.exe với AUTODUB_SMOKE=1 ...")
    result_json = os.path.join(DIST_DIR, "smoke_test_result.json")
    if os.path.isfile(result_json):
        os.remove(result_json)

    env = dict(os.environ, AUTODUB_SMOKE="1")
    # QT_QPA_PLATFORM=offscreen nếu chạy trên máy không có màn hình:
    # env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run([os.path.join(DIST_DIR, "VoxDub.exe")], env=env,
                          cwd=DIST_DIR, timeout=180)

    if not os.path.isfile(result_json):
        log("!! exe không ghi smoke_test_result.json — khởi động thất bại?")
        return False
    with open(result_json, encoding="utf-8") as f:
        checks = json.load(f)

    log("--- kết quả smoke test ---")
    for key, val in checks.items():
        mark = ""
        if isinstance(val, bool):
            mark = "OK " if val else "FAIL "
        log(f"  {mark}{key} = {val}")

    # Trên máy build chưa chắc có model/ffmpeg cạnh dist — chỉ các mục
    # bắt buộc (exe chạy, GUI dựng được, ghi .env được, import đủ) quyết
    # định pass/fail; phần còn lại là thông tin.
    ok = bool(checks.get("ok")) and proc.returncode == 0
    os.remove(result_json)
    # Bài kiểm tra ghi .env đã tạo file .env trong dist — dọn đi để bản
    # phân phối sạch (người dùng tự tạo qua tab Cài đặt).
    stray = os.path.join(DIST_DIR, ".env")
    if os.path.isfile(stray):
        os.remove(stray)
    log("SMOKE TEST PASS" if ok else "SMOKE TEST FAIL")
    return ok


# --------------------------------------------------------------- payloads --

SETUP_VIENEU_BAT = r"""@echo off
chcp 65001 >nul
title Cai dat giong doc VieNeu cho VoxDub Studio
echo.
echo  Script nay cai giong doc VieNeu (chay CPU, ~300 MB, 14 giong).
echo  Yeu cau: da cai Python 3.10-3.12 (xem HUONG_DAN_CAI_DAT.md, Buoc 2).
echo.
cd /d "%~dp0"
py -3.12 scripts\setup_vieneu.py 2>nul || py -3.11 scripts\setup_vieneu.py 2>nul || py -3.10 scripts\setup_vieneu.py 2>nul || py scripts\setup_vieneu.py || python scripts\setup_vieneu.py
if errorlevel 1 (
    echo.
    echo  !! Cai dat that bai. Kiem tra da cai Python chua: py --version
    echo     Xem muc "Xu ly loi" trong HUONG_DAN_CAI_DAT.md
)
echo.
pause
"""

SETUP_WHISPER_BAT = r"""@echo off
chcp 65001 >nul
title Cai dat Whisper ASR cho VoxDub Studio
echo.
echo  Script nay cai faster-whisper vao venv rieng (.venv-whisper).
echo  Whisper se chay ngoai exe — giam ~112 MB kich thuoc ban phan phoi.
echo  Yeu cau: da cai Python 3.10-3.12 (xem HUONG_DAN_CAI_DAT.md, Buoc 2).
echo.
cd /d "%~dp0"
py -3.12 scripts\setup_whisper.py 2>nul || py -3.11 scripts\setup_whisper.py 2>nul || py -3.10 scripts\setup_whisper.py 2>nul || py scripts\setup_whisper.py || python scripts\setup_whisper.py
if errorlevel 1 (
    echo.
    echo  !! Cai dat that bai. Kiem tra da cai Python chua: py --version
    echo     Xem muc "Xu ly loi" trong HUONG_DAN_CAI_DAT.md
)
echo.
pause
"""

SETUP_PARAFORMER_BAT = r"""@echo off
chcp 65001 >nul
title Cai dat ASR tieng Trung (Paraformer) cho VoxDub Studio
echo.
echo  Script nay cai bo nhan dang tieng Trung Paraformer (~520 MB, chay CPU)
echo  — chinh xac hon Whisper voi video tieng Trung.
echo  Yeu cau: da cai Python 3.10-3.12 (xem HUONG_DAN_CAI_DAT.md, Buoc 2).
echo.
cd /d "%~dp0"
py -3.12 scripts\setup_paraformer.py 2>nul || py -3.11 scripts\setup_paraformer.py 2>nul || py -3.10 scripts\setup_paraformer.py 2>nul || py scripts\setup_paraformer.py || python scripts\setup_paraformer.py
if errorlevel 1 (
    echo.
    echo  !! Cai dat that bai. Kiem tra da cai Python chua: py --version
    echo     Xem muc "Xu ly loi" trong HUONG_DAN_CAI_DAT.md
)
echo.
pause
"""

SETUP_DOUYIN_BAT = r"""@echo off
chcp 65001 >nul
title Cai dat tinh nang tai video Douyin cho VoxDub Studio
echo.
echo  Script nay cai thu vien playwright (~40 MB) va trinh duyet Chromium
echo  (~170 MB) de tai video Douyin. YouTube va link truc tiep KHONG can.
echo  Yeu cau: Python DUNG phien ban ghi trong scripts\python_tag.txt.
echo.
cd /d "%~dp0"
py -3.12 scripts\setup_douyin.py 2>nul || py scripts\setup_douyin.py || python scripts\setup_douyin.py
if errorlevel 1 (
    echo.
    echo  !! Cai dat that bai. Kiem tra da cai Python dung phien ban:
    echo     type scripts\python_tag.txt   va   py --version
    echo     Xem muc "Xu ly loi" trong HUONG_DAN_CAI_DAT.md
)
echo.
pause
"""

SETUP_GPU_BAT = r"""@echo off
chcp 65001 >nul
title Cai dat GPU tach nhac (Demucs) cho VoxDub Studio
echo.
echo  Script nay cai PyTorch CUDA 12.4 + Demucs vao .venv-gpu (~2 GB).
echo  Yeu cau: card NVIDIA voi CUDA support + driver cap nhat.
echo  Neu khong co GPU, Demucs van chay duoc bang CPU (cham hon).
echo  Yeu cau: da cai Python 3.10-3.12 (xem HUONG_DAN_CAI_DAT.md).
echo.
cd /d "%~dp0"
py -3.12 scripts\setup_gpu.py 2>nul || py -3.11 scripts\setup_gpu.py 2>nul || py -3.10 scripts\setup_gpu.py 2>nul || py scripts\setup_gpu.py || python scripts\setup_gpu.py
if errorlevel 1 (
    echo.
    echo  !! Cai dat that bai. Kiem tra da cai Python chua: py --version
    echo     Cap nhat driver NVIDIA tai: https://www.nvidia.com/download/index.aspx
    echo     Xem muc "Xu ly loi" trong HUONG_DAN_CAI_DAT.md
)
echo.
pause
"""

GUIDE_MD = """# Hướng dẫn cài đặt VoxDub Studio

VoxDub Studio lồng tiếng video tự động sang tiếng Việt: tải video → nhận dạng
giọng nói → dịch → đọc giọng Việt (clone giọng) → ghép lại thành video.

> **Cách nhanh nhất:** Đúp chuột **VoxDub.exe** → Wizard cài đặt tự hiện,
> hướng dẫn bạn qua từng bước ngay trong app — không cần gõ lệnh.

---

## Cách cài bằng Wizard (khuyến nghị)

1. Đúp chuột **VoxDub.exe**.
2. Wizard cài đặt tự hiện ở lần mở đầu tiên.
3. Bấm **"Bắt đầu cài đặt"** → wizard tự cài FFmpeg, VieNeu TTS và Whisper ASR
   (các thành phần bắt buộc), hiện thanh tiến trình + log theo thời gian thực.
4. **Paraformer ASR** (tùy chọn, cho video tiếng Trung): bấm "Tiếp theo" hoặc
   "Bỏ qua" nếu bạn không làm video tiếng Trung.
5. **Tính năng thêm** (tùy chọn): GPU Demucs (tách nhạc siêu nhanh) và Douyin
   — cài ngay trong wizard hoặc bỏ qua rồi làm sau.
6. Nhập mã kích hoạt nếu có, hoặc bỏ qua → bấm **"Bắt đầu dùng VoxDub Studio"**.

Máy mới được tặng sẵn Vox dùng thử, không cần mua gì để thử.

---

## Cài thủ công (đường dự phòng khi Wizard không chạy được)

Thứ tự khuyến nghị:

### Bước 1 — Python 3.12 (để script cài chạy được)

```
winget install Python.Python.3.12
```

Đóng và mở lại PowerShell, gõ `py --version` — thấy `Python 3.12.x` là được.

> Nếu máy đã có Python 3.10–3.12 thì bỏ qua.

### Bước 2 — Giọng đọc VieNeu (bắt buộc, ~300 MB)

Đúp chuột **`Cai dat giong VieNeu.bat`**.

### Bước 3 — Whisper ASR (bắt buộc, ~1.5 GB)

Đúp chuột **`Cai dat Whisper ASR.bat`**.

### Tùy chọn

| Tính năng | File .bat | Ghi chú |
|---|---|---|
| Nhận dạng tiếng Trung (Paraformer) | `Cai dat ASR tieng Trung (Paraformer).bat` | ~520 MB, CPU |
| Tải video Douyin | `Cai dat tinh nang Douyin.bat` | Playwright + Chromium ~210 MB |
| GPU Demucs (tách nhạc nhanh) | `Cai dat GPU tach nhac (Demucs).bat` | ~2 GB, cần card NVIDIA |

---

## Vox (tài nguyên dịch)

Bước dịch chạy qua máy chủ VoxDub — không cần đăng ký hay lấy API key của ai.
Máy mới được tặng sẵn Vox dùng thử.

Hết Vox thì mua thêm:
1. Vào trang web VoxDub, chọn gói → chuyển khoản theo mã QR.
2. Giữ nguyên nội dung chuyển khoản (mã đơn hàng).
3. Nhận mã kích hoạt VOX-XXXX-XXXX-XXXX qua web/email.
4. Mở **VoxDub.exe → Tài khoản**, dán mã, bấm **Kích hoạt**.

> Mỗi mã chỉ dùng được một lần trên một máy. Đổi máy thì liên hệ hỗ trợ.

---

## Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| Wizard không hiện khi mở app | Xóa file cache/setup_wizard_done trong thư mục dữ liệu app rồi mở lại |
| ffmpeg không nhận sau khi cài | Đóng mở lại app; hoặc chép ffmpeg.exe+ffprobe.exe vào cạnh VoxDub.exe |
| py không nhận | Cài lại Python bằng winget (Bước 1), mở PowerShell mới |
| App báo hết Vox | Mở trang Tài khoản để nạp thêm |
| GPU không được dùng | nvidia-smi trong PowerShell phải chạy được; cập nhật driver NVIDIA |
| Antivirus chặn VoxDub.exe | Thêm thư mục VoxDub Studio vào danh sách loại trừ |

## Cấu trúc thư mục sau khi cài đủ

```
VoxDub Studio/
├── VoxDub.exe                                  <- mở app tại đây
├── _internal/                                  <- thư viện app (không đụng)
├── Cai dat giong VieNeu.bat                    <- dự phòng (wizard đã lo)
├── Cai dat Whisper ASR.bat                     <- dự phòng
├── Cai dat ASR tieng Trung (Paraformer).bat    <- tùy chọn
├── Cai dat tinh nang Douyin.bat                <- tùy chọn
├── Cai dat GPU tach nhac (Demucs).bat          <- tùy chọn, cần NVIDIA
├── scripts/
├── models/vieneu/         <- model VieNeu (sau khi cài)
├── models/paraformer-zh/  <- model Paraformer (nếu cài)
├── models/whisper/        <- model Whisper (sau khi cài)
├── .venv-vieneu/          <- môi trường VieNeu
├── .venv-whisper/         <- môi trường Whisper
├── .venv-asr/             <- môi trường Paraformer (nếu cài)
├── .venv-gpu/             <- môi trường GPU/Demucs (nếu cài)
├── pw-browsers/           <- Chromium (nếu dùng Douyin)
├── .env                   <- app tự tạo khi Lưu cài đặt
└── output/                <- video kết quả
```
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-test", action="store_true",
                        help="bỏ qua smoke test sau khi build")
    parser.add_argument("--no-zip", action="store_true",
                        help="bỏ qua bước nén .zip phát hành")
    args = parser.parse_args()

    _force_utf8_stdio()
    start = time.time()
    step_embed_api_url()
    try:
        step_pyinstaller()
    finally:
        # Kill-switch URL không được nằm lại trong source tree.
        step_restore_embedded()

    step_assemble()

    ok = True
    if not args.no_test:
        ok = step_smoke_test()

    size = sum(os.path.getsize(os.path.join(dp, f))
               for dp, _, fs in os.walk(DIST_DIR) for f in fs)
    log(f"xong sau {time.time() - start:.0f}s — dist/VoxDub ({size >> 20} MB)")

    # Nén sẵn gói phát hành: dist/VoxDub-Studio-v<ver>.zip, giải nén ra
    # thư mục gốc "VoxDub Studio/" (đúng tên trong HUONG_DAN_CAI_DAT.md).
    # Chỉ nén khi smoke test đạt — không bao giờ phát hành bản hỏng.
    if ok and not args.no_zip:
        # Đọc APP_VERSION bằng regex — import autodub_gui.app sẽ kéo cả Qt
        # và chạy _frozen.init(), không đáng cho một chuỗi số.
        import re
        src = open(os.path.join(PROJECT_ROOT, "autodub_gui", "app.py"),
                   encoding="utf-8").read()
        m = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', src, re.M)
        version = m.group(1) if m else "0.0"
        zip_path = os.path.join(PROJECT_ROOT, "dist",
                                f"VoxDub-Studio-v{version}.zip")
        log(f"đang nén gói phát hành: {os.path.basename(zip_path)} ...")
        import zipfile
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6) as zf:
            for dp, _, fs in os.walk(DIST_DIR):
                for f in fs:
                    full = os.path.join(dp, f)
                    rel = os.path.relpath(full, DIST_DIR)
                    zf.write(full, os.path.join("VoxDub Studio", rel))
        zsize = os.path.getsize(zip_path)
        log(f"gói phát hành sẵn sàng: {zip_path} ({zsize >> 20} MB)")
    elif not ok:
        log("SMOKE TEST FAIL — bỏ qua bước nén .zip")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
