"""Cài đặt OCR hard-sub — RapidOCR (onnxruntime, CPU) trong venv riêng.

Chạy 1 lần:  py scripts/setup_ocr.py

Các bước đều resume-safe — chạy lại script sẽ bỏ qua phần đã xong:
  1. Tạo virtualenv .venv-ocr
  2. pip install rapidocr-onnxruntime (weights zh kèm sẵn trong package)
  3. Smoke test OCR 1 ảnh tự sinh → installed_ok.json
  4. Nhắc bật OCR_ENABLED=true trong .env
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv-ocr")
VENV_PY = os.path.join(VENV_DIR, "Scripts" if os.name == "nt" else "bin",
                       "python.exe" if os.name == "nt" else "python")
WORKER = os.path.join(PROJECT_ROOT, "autodub", "media", "ocr_worker.py")
if not os.path.isfile(WORKER):
    # Bản đóng gói: worker nằm trong data/ (PyInstaller contents_directory).
    for _d in ("data", "_internal"):
        _candidate = os.path.join(PROJECT_ROOT, _d, "autodub", "media",
                                  "ocr_worker.py")
        if os.path.isfile(_candidate):
            WORKER = _candidate
            break
MARKER = os.path.join(VENV_DIR, "installed_ok.json")

#: Pin major để không tự nhảy sang bản đổi API.
_OCR_SPECS = ("rapidocr-onnxruntime<2.0",)


def log(msg: str) -> None:
    print(f"[setup-ocr] {msg}", flush=True)


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    log(" ".join(cmd))
    return subprocess.run(cmd, **kw)


def _make_venv() -> None:
    if os.path.isfile(VENV_PY):
        log(f"virtualenv đã có: {VENV_DIR}")
        return
    log(f"tạo virtualenv {VENV_DIR} ...")
    r = _run([sys.executable, "-m", "venv", VENV_DIR])
    if r.returncode != 0 or not os.path.isfile(VENV_PY):
        sys.exit("Không tạo được .venv-ocr — kiểm tra python -m venv.")


def _install() -> None:
    r = _run([VENV_PY, "-m", "pip", "install", "--upgrade", "pip"])
    if r.returncode != 0:
        sys.exit("pip upgrade lỗi.")
    r = _run([VENV_PY, "-m", "pip", "install", *_OCR_SPECS])
    if r.returncode != 0:
        sys.exit("Cài rapidocr-onnxruntime lỗi — xem log trên.")


def _smoke_test() -> None:
    """Sinh 1 ảnh nhỏ có chữ Hán (PIL kèm theo rapidocr) rồi OCR thử."""
    smoke_dir = os.path.join(VENV_DIR, "_smoke")
    os.makedirs(smoke_dir, exist_ok=True)
    img = os.path.join(smoke_dir, "probe.png")
    code = (
        "from PIL import Image, ImageDraw\n"
        "img = Image.new('RGB', (300, 80), 'black')\n"
        "d = ImageDraw.Draw(img)\n"
        "d.text((20, 20), '你好世界测试', fill='white')\n"
        "img.save(r'%s')\n" % img.replace("\\", "\\\\")
    )
    r = _run([VENV_PY, "-c", code])
    if r.returncode != 0 or not os.path.isfile(img):
        sys.exit("Không sinh được ảnh smoke test.")
    with open(os.path.join(smoke_dir, "list.txt"), "w",
              encoding="utf-8") as f:
        f.write(img)
    r = _run([VENV_PY, WORKER, "--list", os.path.join(smoke_dir, "list.txt")],
             capture_output=True, text=True, encoding="utf-8",
             errors="replace")
    ok = r.returncode == 0 and '"done"' in (r.stdout or "")
    if not ok:
        sys.exit(f"Smoke test OCR lỗi:\n{r.stderr[-500:]}")
    with open(MARKER, "w", encoding="utf-8") as f:
        json.dump({"ok": True, "specs": list(_OCR_SPECS)}, f)
    log("smoke test PASS")


def main() -> None:
    os.chdir(PROJECT_ROOT)
    _make_venv()
    _install()
    _smoke_test()
    log("Xong. Bật OCR_ENABLED=true trong .env để dùng (mặc định tắt).")


if __name__ == "__main__":
    main()
