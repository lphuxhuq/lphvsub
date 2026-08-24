"""Cài đặt GPU acceleration: PyTorch CUDA 12.4 + Demucs vào .venv-gpu.

Chạy 1 lần:  py scripts/setup_gpu.py

Yêu cầu: card NVIDIA có CUDA support + driver cập nhật.
Dung lượng: ~2 GB (PyTorch wheel + Demucs).

Các bước đều resume-safe — chạy lại script sẽ bỏ qua phần đã xong:
  1. Tạo virtualenv .venv-gpu
  2. pip install torch torchvision torchaudio (cu124 index) nếu chưa có
  3. pip install demucs nếu chưa có
  4. Kiểm tra torch.cuda.is_available() → ghi installed_ok.json
     (GPU không có vẫn OK — Whisper/Demucs rơi về CPU, nhưng cài xong)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv-gpu")
VENV_PY = os.path.join(VENV_DIR,
                        "Scripts" if os.name == "nt" else "bin",
                        "python.exe" if os.name == "nt" else "python")
MARKER = os.path.join(VENV_DIR, "installed_ok.json")

_TORCH_INDEX_URL = "https://download.pytorch.org/whl/cu124"
_TORCH_PACKAGES = ["torch", "torchvision", "torchaudio"]
_DEMUCS_SPEC = "demucs"

# Không bật cửa sổ console trên Windows khi gọi subprocess
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def log(msg: str) -> None:
    print(f"[setup-gpu] {msg}", flush=True)


def step_venv() -> None:
    if os.path.isfile(VENV_PY):
        log("venv .venv-gpu đã có — bỏ qua")
        return
    log("tạo virtualenv .venv-gpu ...")
    subprocess.run([sys.executable, "-m", "venv", VENV_DIR],
                   check=True, creationflags=_NO_WINDOW)
    log("cập nhật pip trong .venv-gpu ...")
    subprocess.run(
        [VENV_PY, "-m", "pip", "install", "--upgrade", "--quiet", "pip"],
        check=True, creationflags=_NO_WINDOW)


def step_torch() -> None:
    """Cài PyTorch CUDA 12.4 nếu chưa có."""
    probe = subprocess.run(
        [VENV_PY, "-c", "import torch; print(torch.__version__)"],
        capture_output=True, text=True, creationflags=_NO_WINDOW)
    if probe.returncode == 0 and probe.stdout.strip():
        log(f"torch {probe.stdout.strip()} đã cài — bỏ qua")
        return
    log("cài PyTorch CUDA 12.4 (~2 GB, có thể mất 10–20 phút) ...")
    subprocess.run(
        [VENV_PY, "-m", "pip", "install", "--quiet",
         *_TORCH_PACKAGES,
         "--index-url", _TORCH_INDEX_URL],
        check=True, creationflags=_NO_WINDOW)
    log("PyTorch CUDA 12.4 đã cài xong")


def step_demucs() -> None:
    """Cài Demucs nếu chưa có."""
    probe = subprocess.run(
        [VENV_PY, "-c", "import demucs"],
        capture_output=True, creationflags=_NO_WINDOW)
    if probe.returncode == 0:
        log("demucs đã cài — bỏ qua")
        return
    log("cài demucs ...")
    subprocess.run(
        [VENV_PY, "-m", "pip", "install", "--quiet", _DEMUCS_SPEC],
        check=True, creationflags=_NO_WINDOW)
    log("demucs đã cài xong")


def step_smoke() -> None:
    """Kiểm tra GPU và ghi marker."""
    if os.path.isfile(MARKER):
        log("installed_ok.json đã có — bỏ qua")
        return

    log("kiểm tra CUDA ...")
    probe = subprocess.run(
        [VENV_PY, "-c",
         "import torch; "
         "cuda = torch.cuda.is_available(); "
         "name = torch.cuda.get_device_name(0) if cuda else 'none'; "
         "print(f'cuda={cuda} device={name}')"],
        capture_output=True, text=True, creationflags=_NO_WINDOW)

    cuda_available = False
    device_name = "none"
    if probe.returncode == 0 and probe.stdout.strip():
        out = probe.stdout.strip()
        log(f"  {out}")
        cuda_available = "cuda=True" in out
        # trích tên GPU nếu có
        if "device=" in out:
            device_name = out.split("device=", 1)[1].strip()
    else:
        log("  (không kiểm tra được CUDA — có thể driver chưa cập nhật)")

    if not cuda_available:
        log("!! GPU NVIDIA không khả dụng. Whisper/Demucs sẽ chạy CPU.")
        log("   Kiểm tra: chạy 'nvidia-smi' trong PowerShell.")

    # Ghi marker dù GPU có hay không — cài package đã xong là đủ
    with open(MARKER, "w", encoding="utf-8") as f:
        json.dump({
            "ok": True,
            "cuda_available": cuda_available,
            "device": device_name,
            "torch_index": _TORCH_INDEX_URL,
        }, f, ensure_ascii=False, indent=2)
    log("installed_ok.json đã ghi")


def main() -> None:
    log("Cài đặt GPU acceleration (PyTorch CUDA 12.4 + Demucs)")
    log(f"Thư mục: {VENV_DIR}")
    step_venv()
    step_torch()
    step_demucs()
    step_smoke()
    log("XONG — mở app, Demucs sẽ tự dùng GPU NVIDIA khi có.")
    log("Bộ giọng đọc VieNeu và Paraformer ASR vẫn chạy CPU riêng.")


if __name__ == "__main__":
    main()
