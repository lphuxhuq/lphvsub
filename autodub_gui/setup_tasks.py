"""Cài đặt các thư viện ngoài trực tiếp trong ứng dụng.

Thay thế cho các tệp script độc lập trong thư mục scripts/, giúp đóng gói
ứng dụng sạch sẽ hơn và tránh lộ mã nguồn cài đặt ra ngoài bản phân phối.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
import wave
from collections.abc import Callable

from autodub.utils import app_root

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _run_cmd(
    cmd: list[str], log_cb: Callable[[str], None], input_str: str | None = None, timeout: int = 600
) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_str else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=app_root(),
        creationflags=_NO_WINDOW,
    )
    if input_str and proc.stdin:
        proc.stdin.write(input_str)
        proc.stdin.close()

    lines_seen = 0
    stdout_tail = []
    for line in proc.stdout:  # type: ignore[union-attr]
        line = line.rstrip()
        if not line:
            continue
        lines_seen += 1
        stdout_tail.append(line)
        if len(stdout_tail) > 200:
            stdout_tail.pop(0)
        log_cb(line)

    proc.wait(timeout=timeout)
    if proc.returncode != 0:
        err = "\n".join(stdout_tail[-20:]) if stdout_tail else "Không có output."
        raise RuntimeError(f"Tiến trình kết thúc với mã lỗi {proc.returncode}:\n{err}")
    return proc


def _download(url: str, dest: str, log_cb: Callable[[str], None]) -> None:
    log_cb(f"tải {os.path.basename(dest)} ...")
    tmp = dest + ".part"
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_mb = -1
        while True:
            chunk = resp.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            mb = done >> 20
            if mb != last_mb and total:
                log_cb(f"  {mb}/{total >> 20} MB")
                last_mb = mb
    os.replace(tmp, dest)


def _extract_flat(tarball: str, dest_dir: str, wanted: tuple[str, ...]) -> None:
    os.makedirs(dest_dir, exist_ok=True)
    with tarfile.open(tarball, "r:bz2") as tf:
        for member in tf.getmembers():
            base = os.path.basename(member.name)
            if base in wanted and member.isfile():
                with tf.extractfile(member) as src, open(os.path.join(dest_dir, base), "wb") as out:
                    shutil.copyfileobj(src, out)


def _find_worker(name: str) -> str:
    root = app_root()
    worker = os.path.join(root, "autodub", "speech", name)
    if not os.path.isfile(worker):
        for _d in ("data", "_internal"):
            _c = os.path.join(root, _d, "autodub", "speech", name)
            if os.path.isfile(_c):
                return _c
    return worker


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


def task_vieneu(python_exe: str, log_cb: Callable[[str], None]) -> None:
    root = app_root()
    venv_dir = os.path.join(root, ".venv-vieneu")
    venv_py = os.path.join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python",
    )
    model_dir = os.path.join(root, "models", "vieneu")
    marker = os.path.join(model_dir, "installed_ok.json")
    voices_json = os.path.join(model_dir, "voices.json")
    spec = "vieneu>=3.2,<4.0"

    log_cb("[setup-vieneu] Cài đặt VieNeu-TTS — giọng đọc tiếng Việt chạy CPU")
    log_cb("[setup-vieneu] Model: pnnbao-ump/VieNeu-TTS-v3-Turbo")

    if not os.path.isfile(venv_py):
        log_cb("[setup-vieneu] tạo virtualenv .venv-vieneu ...")
        _run_cmd([python_exe, "-m", "venv", venv_dir], log_cb)
    else:
        log_cb("[setup-vieneu] venv .venv-vieneu đã có — bỏ qua")

    probe = subprocess.run(
        [venv_py, "-c", "import vieneu"], capture_output=True, creationflags=_NO_WINDOW
    )
    if probe.returncode != 0:
        log_cb("[setup-vieneu] cài vieneu (ONNX, không cần GPU) ...")
        _run_cmd([venv_py, "-m", "pip", "install", "--quiet", spec], log_cb)
    else:
        log_cb("[setup-vieneu] package vieneu đã cài — bỏ qua")

    if not (os.path.isfile(voices_json) and os.path.isfile(marker)):
        log_cb("[setup-vieneu] tải model VieNeu-TTS-v3-Turbo (~300 MB, lần đầu hơi lâu) ...")
        os.makedirs(model_dir, exist_ok=True)
        code = f"""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["HF_HOME"] = {model_dir!r}
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
from vieneu import Vieneu
v = Vieneu(backend="onnx")
voices = v.list_preset_voices()
json.dump([{{"label": l, "name": n}} for l, n in voices],
          open({voices_json!r}, "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
import soundfile as sf
audio = v.infer("xin chào, hai nghìn không trăm hai mươi sáu", voice=voices[0][1])
smoke = os.path.join({model_dir!r}, "smoke_test.wav")
sf.write(smoke, audio, v.sample_rate)
assert os.path.getsize(smoke) > 10000
json.dump({{"ok": True, "model": "VieNeu-TTS-v3-Turbo", "backend": "onnx",
           "sample_rate": v.sample_rate}},
          open({marker!r}, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("model OK,", len(voices), "giọng")
"""
        _run_cmd([venv_py, "-c", code], log_cb)
    else:
        log_cb("[setup-vieneu] model + voices.json đã có — bỏ qua")

    log_cb("[setup-vieneu] XONG — mở app, giọng đọc VieNeu được dùng tự động (14 giọng nam/nữ).")


def task_whisper(python_exe: str, log_cb: Callable[[str], None]) -> None:
    root = app_root()
    venv_dir = os.path.join(root, ".venv-whisper")
    venv_py = os.path.join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python",
    )
    model_dir = os.path.join(root, "models", "whisper")
    marker = os.path.join(model_dir, "installed_ok.json")
    spec = "faster-whisper<2.0"
    worker_script = _find_worker("asr_whisper_worker.py")

    log_cb("[setup-whisper] Cài đặt Whisper ASR vào venv riêng")
    log_cb(f"[setup-whisper] Model cache: {model_dir}")

    if not os.path.isfile(venv_py):
        log_cb("[setup-whisper] tạo virtualenv .venv-whisper ...")
        _run_cmd([python_exe, "-m", "venv", venv_dir], log_cb)
    else:
        log_cb("[setup-whisper] venv .venv-whisper đã có — bỏ qua")

    probe = subprocess.run(
        [venv_py, "-c", "import faster_whisper"], capture_output=True, creationflags=_NO_WINDOW
    )
    if probe.returncode != 0:
        log_cb("[setup-whisper] cài faster-whisper (ctranslate2, CPU/GPU) ...")
        _run_cmd([venv_py, "-m", "pip", "install", "--quiet", spec], log_cb)
    else:
        log_cb("[setup-whisper] faster-whisper đã cài — bỏ qua")

    if not os.path.isfile(marker):
        os.makedirs(model_dir, exist_ok=True)
        smoke_wav = os.path.join(model_dir, "smoke_test.wav")
        with wave.open(smoke_wav, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00\x00" * 32000)

        log_cb("[setup-whisper] chạy smoke test (tải model lần đầu có thể mất vài phút) ...")
        try:
            cmd = [
                venv_py,
                worker_script,
                "--audio",
                smoke_wav,
                "--model",
                "medium",
                "--language",
                "zh",
                "--model-dir",
                model_dir,
            ]
            cuda_dir = os.path.join(root, ".venv-gpu", "Lib", "site-packages", "torch", "lib")
            if os.name == "nt" and os.path.isdir(cuda_dir):
                cmd += ["--cuda-dll-dir", cuda_dir]

            request = {"audio": smoke_wav, "language": "zh", "beam_size": 1}
            _run_cmd(cmd, log_cb, input_str=json.dumps(request) + "\n")

            with open(marker, "w", encoding="utf-8") as f:
                json.dump(
                    {"ok": True, "model": "medium", "backend": "faster-whisper"},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            log_cb("[setup-whisper] smoke test PASS")
        finally:
            try:
                os.remove(smoke_wav)
            except OSError:
                pass
    else:
        log_cb("[setup-whisper] smoke test đã đạt — bỏ qua")

    log_cb("[setup-whisper] XONG — Whisper chạy trong .venv-whisper.")


def task_paraformer(python_exe: str, log_cb: Callable[[str], None]) -> None:
    root = app_root()
    venv_dir = os.path.join(root, ".venv-asr")
    venv_py = os.path.join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python",
    )
    model_dir = os.path.join(root, "models", "paraformer-zh")
    marker = os.path.join(model_dir, "installed_ok.json")
    specs = ("sherpa-onnx<2.0", "numpy<3.0")
    worker_script = _find_worker("asr_paraformer_worker.py")

    _GH = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
    ASR_TARBALL = f"{_GH}/asr-models/sherpa-onnx-paraformer-zh-2023-09-14.tar.bz2"
    VAD_URL = f"{_GH}/asr-models/silero_vad.onnx"
    PUNCT_TARBALL = f"{_GH}/punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12.tar.bz2"

    log_cb("[setup-asr] Cài đặt Paraformer — nhận dạng tiếng Trung chính xác hơn (chạy CPU)")

    if not os.path.isfile(venv_py):
        log_cb("[setup-asr] tạo virtualenv .venv-asr ...")
        _run_cmd([python_exe, "-m", "venv", venv_dir], log_cb)
    else:
        log_cb("[setup-asr] venv .venv-asr đã có — bỏ qua")

    probe = subprocess.run(
        [venv_py, "-c", "import sherpa_onnx, numpy"], capture_output=True, creationflags=_NO_WINDOW
    )
    if probe.returncode != 0:
        log_cb("[setup-asr] cài sherpa-onnx + numpy (ONNX, không cần GPU) ...")
        _run_cmd([venv_py, "-m", "pip", "install", "--quiet", *specs], log_cb)
    else:
        log_cb("[setup-asr] package sherpa-onnx đã cài — bỏ qua")

    os.makedirs(model_dir, exist_ok=True)
    if not (
        os.path.isfile(os.path.join(model_dir, "model.int8.onnx"))
        and os.path.isfile(os.path.join(model_dir, "tokens.txt"))
    ):
        log_cb("[setup-asr] tải model Paraformer-large zh (~230 MB) ...")
        tarball = os.path.join(model_dir, "paraformer.tar.bz2")
        _download(ASR_TARBALL, tarball, log_cb)
        _extract_flat(tarball, model_dir, ("model.int8.onnx", "tokens.txt"))
        os.remove(tarball)
    else:
        log_cb("[setup-asr] model Paraformer đã có — bỏ qua")

    vad = os.path.join(model_dir, "silero_vad.onnx")
    if not os.path.isfile(vad):
        _download(VAD_URL, vad, log_cb)
    else:
        log_cb("[setup-asr] silero_vad.onnx đã có — bỏ qua")

    punct_dir = os.path.join(model_dir, "punct")
    if not os.path.isfile(os.path.join(punct_dir, "model.onnx")):
        try:
            log_cb("[setup-asr] tải model chấm câu CT-Transformer (~290 MB) ...")
            tarball = os.path.join(model_dir, "punct.tar.bz2")
            _download(PUNCT_TARBALL, tarball, log_cb)
            _extract_flat(tarball, punct_dir, ("model.onnx",))
            os.remove(tarball)
        except Exception as e:
            log_cb(f"[setup-asr] !! không tải được model chấm câu ({e}) — bỏ qua")
    else:
        log_cb("[setup-asr] model chấm câu đã có — bỏ qua")

    if not os.path.isfile(marker):
        log_cb("[setup-asr] chạy thử nhận dạng 1 file (smoke test) ...")
        smoke_wav = os.path.join(model_dir, "smoke_test.wav")
        gen = f"import numpy as np, wave\nw = wave.open({smoke_wav!r}, 'wb')\nw.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)\nw.writeframes(np.zeros(32000, dtype=np.int16).tobytes())\nw.close()\n"
        _run_cmd([venv_py, "-c", gen], log_cb)

        try:
            _run_cmd(
                [venv_py, worker_script, "--audio", smoke_wav, "--model-dir", model_dir], log_cb
            )
            with open(marker, "w", encoding="utf-8") as f:
                json.dump(
                    {"ok": True, "model": "paraformer-zh-2023-09-14", "backend": "sherpa-onnx"},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
            log_cb("[setup-asr] smoke test PASS")
        finally:
            try:
                os.remove(smoke_wav)
            except OSError:
                pass
    else:
        log_cb("[setup-asr] smoke test đã đạt — bỏ qua")

    env_path = os.path.join(root, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("ASR_ENGINE="):
            lines[i] = "ASR_ENGINE=paraformer"
            found = True
            break
    if not found:
        lines.append("ASR_ENGINE=paraformer")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log_cb("[setup-asr] đã bật ASR_ENGINE=paraformer trong .env")
    log_cb("[setup-asr] XONG — mở app, video tiếng Trung sẽ được nhận dạng bằng Paraformer.")


def task_douyin(python_exe: str, log_cb: Callable[[str], None]) -> None:
    root = app_root()
    libs_dir = os.path.join(root, "libs")
    browsers_dir = os.path.join(root, "pw-browsers")

    log_cb("[setup-douyin] Cài tính năng tải video Douyin (playwright + Chromium)")

    probe = subprocess.run(
        [python_exe, "-c", f"import sys; sys.path.insert(0, {libs_dir!r}); import playwright"],
        capture_output=True,
        creationflags=_NO_WINDOW,
    )
    if probe.returncode != 0:
        log_cb("[setup-douyin] cài playwright vào libs/ (~40 MB) ...")
        os.makedirs(libs_dir, exist_ok=True)
        _run_cmd(
            [
                python_exe,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--target",
                libs_dir,
                "--upgrade",
                "playwright>=1.50,<2",
            ],
            log_cb,
        )
    else:
        log_cb("[setup-douyin] playwright đã cài trong libs/ — bỏ qua")

    if not (
        os.path.isdir(browsers_dir)
        and any(name.startswith("chromium") for name in os.listdir(browsers_dir))
    ):
        log_cb("[setup-douyin] tải Chromium (~170 MB, vài phút) ...")
        env = dict(
            os.environ,
            PLAYWRIGHT_BROWSERS_PATH=browsers_dir,
            PYTHONPATH=libs_dir + os.pathsep + os.environ.get("PYTHONPATH", ""),
        )

        proc = subprocess.Popen(
            [python_exe, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=root,
            env=env,
            creationflags=_NO_WINDOW,
        )
        for line in proc.stdout:  # type: ignore[union-attr]
            log_cb(f"[setup-douyin] {line.rstrip()}")
        proc.wait(timeout=1800)
        if proc.returncode != 0:
            raise RuntimeError(f"Lỗi cài Chromium: exit code {proc.returncode}")
    else:
        log_cb("[setup-douyin] Chromium đã cài trong pw-browsers/ — bỏ qua")

    log_cb("[setup-douyin] XONG — mở lại VoxDub, tính năng tải Douyin đã sẵn sàng.")


def task_gpu(python_exe: str, log_cb: Callable[[str], None]) -> None:
    root = app_root()
    venv_dir = os.path.join(root, ".venv-gpu")
    venv_py = os.path.join(
        venv_dir,
        "Scripts" if os.name == "nt" else "bin",
        "python.exe" if os.name == "nt" else "python",
    )
    marker = os.path.join(venv_dir, "installed_ok.json")
    torch_index = "https://download.pytorch.org/whl/cu124"
    torch_pkgs = ["torch", "torchvision", "torchaudio"]

    log_cb("[setup-gpu] Cài đặt GPU acceleration (PyTorch CUDA 12.4 + Demucs)")
    log_cb(f"[setup-gpu] Thư mục: {venv_dir}")

    if not os.path.isfile(venv_py):
        log_cb("[setup-gpu] tạo virtualenv .venv-gpu ...")
        _run_cmd([python_exe, "-m", "venv", venv_dir], log_cb)
        log_cb("[setup-gpu] cập nhật pip trong .venv-gpu ...")
        _run_cmd([venv_py, "-m", "pip", "install", "--upgrade", "--quiet", "pip"], log_cb)
    else:
        log_cb("[setup-gpu] venv .venv-gpu đã có — bỏ qua")

    probe = subprocess.run(
        [venv_py, "-c", "import torch; print(torch.__version__)"],
        capture_output=True,
        text=True,
        creationflags=_NO_WINDOW,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        log_cb("[setup-gpu] cài PyTorch CUDA 12.4 (~2 GB, có thể mất 10–20 phút) ...")
        _run_cmd(
            [venv_py, "-m", "pip", "install", "--quiet", *torch_pkgs, "--index-url", torch_index],
            log_cb,
            timeout=3600,
        )
        log_cb("[setup-gpu] PyTorch CUDA 12.4 đã cài xong")
    else:
        log_cb(f"[setup-gpu] torch {probe.stdout.strip()} đã cài — bỏ qua")

    probe = subprocess.run(
        [venv_py, "-c", "import demucs"], capture_output=True, creationflags=_NO_WINDOW
    )
    if probe.returncode != 0:
        log_cb("[setup-gpu] cài demucs ...")
        _run_cmd([venv_py, "-m", "pip", "install", "--quiet", "demucs"], log_cb)
        log_cb("[setup-gpu] demucs đã cài xong")
    else:
        log_cb("[setup-gpu] demucs đã cài — bỏ qua")

    if not os.path.isfile(marker):
        log_cb("[setup-gpu] kiểm tra CUDA ...")
        probe = subprocess.run(
            [
                venv_py,
                "-c",
                "import torch; cuda = torch.cuda.is_available(); name = torch.cuda.get_device_name(0) if cuda else 'none'; print(f'cuda={cuda} device={name}')",
            ],
            capture_output=True,
            text=True,
            creationflags=_NO_WINDOW,
        )

        cuda_avail = False
        device_name = "none"
        if probe.returncode == 0 and probe.stdout.strip():
            out = probe.stdout.strip()
            log_cb(f"[setup-gpu]   {out}")
            cuda_avail = "cuda=True" in out
            if "device=" in out:
                device_name = out.split("device=", 1)[1].strip()
        else:
            log_cb("[setup-gpu]   (không kiểm tra được CUDA — có thể driver chưa cập nhật)")

        if not cuda_avail:
            log_cb("[setup-gpu] !! GPU NVIDIA không khả dụng. Whisper/Demucs sẽ chạy CPU.")
            log_cb("[setup-gpu]    Kiểm tra: chạy 'nvidia-smi' trong PowerShell.")

        with open(marker, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ok": True,
                    "cuda_available": cuda_avail,
                    "device": device_name,
                    "torch_index": torch_index,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
        log_cb("[setup-gpu] installed_ok.json đã ghi")
    else:
        log_cb("[setup-gpu] installed_ok.json đã có — bỏ qua")

    log_cb("[setup-gpu] XONG — mở app, Demucs sẽ tự dùng GPU NVIDIA khi có.")
    log_cb("[setup-gpu] Bộ giọng đọc VieNeu và Paraformer ASR vẫn chạy CPU riêng.")
