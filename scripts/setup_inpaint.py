"""Cài đặt mô hình AI Subtitle Remover (LaMa ONNX).

Chạy: py scripts/setup_inpaint.py
"""
import os
import sys
import urllib.request
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "inpaint")
MODEL_PATH = os.path.join(MODEL_DIR, "lama.onnx")

# URL chính và mirror dự phòng
MODEL_URLS = [
    "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama_fp32.onnx",
    "https://huggingface.co/Carve/LaMa-ONNX/resolve/main/lama.onnx",
]


def log(msg: str) -> None:
    print(f"[setup-inpaint] {msg}", flush=True)


def download_file(url: str, dest_path: str) -> bool:
    temp_path = f"{dest_path}.tmp"
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    log(f"Đang tải model từ: {url}")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            total_size = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            start_time = time.time()
            last_report = start_time

            with open(temp_path, "wb") as f:
                while True:
                    chunk = resp.read(1024 * 512)  # 512 KB chunks
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_report >= 0.5 or (total_size and downloaded == total_size):
                        last_report = now
                        pct = (downloaded / total_size * 100) if total_size else 0
                        mb = downloaded / (1024 * 1024)
                        total_mb = total_size / (1024 * 1024)
                        speed = (downloaded / (now - start_time)) / (1024 * 1024) if (now > start_time) else 0
                        print(
                            f"\r[setup-inpaint] Tiến độ: {pct:.1f}% ({mb:.1f}/{total_mb:.1f} MB) — {speed:.2f} MB/s",
                            end="",
                            flush=True,
                        )

            print()

        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(temp_path, dest_path)
        log(f"Tải thành công: {dest_path} ({os.path.getsize(dest_path) / (1024*1024):.1f} MB)")
        return True
    except Exception as e:
        log(f"Lỗi tải từ {url}: {e}")
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return False


def main():
    log("=" * 60)
    log("VoxDub / LPHVsub — Cài đặt AI Subtitle Remover (LaMa ONNX)")
    log("=" * 60)

    # 1. Kiểm tra thư viện onnxruntime
    try:
        import onnxruntime as ort
        log(f"Đã có onnxruntime v{ort.__version__} (Providers: {ort.get_available_providers()})")
    except ImportError:
        log("Đang cài đặt onnxruntime...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "onnxruntime"])

    # 2. Kiểm tra file model
    if os.path.isfile(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 10 * 1024 * 1024:
        log(f"Model LaMa ONNX đã có sẵn tại '{MODEL_PATH}' ({os.path.getsize(MODEL_PATH)/(1024*1024):.1f} MB).")
    else:
        success = False
        for url in MODEL_URLS:
            if download_file(url, MODEL_PATH):
                success = True
                break
        if not success:
            log("[LỖI] Không thể tải model LaMa ONNX. Vui lòng kiểm tra kết nối mạng và thử lại.")
            sys.exit(1)

    # 3. Smoke Test
    log("Tiến hành Smoke Test kiểm tra nạp mô hình...")
    try:
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        import numpy as np
        from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine

        engine = LaMaOnnxEngine(model_path=MODEL_PATH)
        test_frame = np.full((128, 256, 3), 120, dtype=np.uint8)
        test_mask = np.zeros((128, 256), dtype=np.uint8)
        test_mask[30:60, 50:200] = 255

        out_frame = engine.inpaint_frame(test_frame, test_mask)
        assert out_frame.shape == (128, 256, 3), f"Shape mismatch: {out_frame.shape}"
        log("Smoke Test HOÀN TẤT — Mô hình AI LaMa ONNX hoạt động chính xác!")
    except Exception as e:
        log(f"[CẢNH BÁO] Smoke test gặp lỗi: {e}")
        sys.exit(1)

    log("=" * 60)
    log("CÀI ĐẶT HOÀN TẤT: AI Inpaint (Phương thức 2) đã sẵn sàng hoạt động!")
    log("=" * 60)


if __name__ == "__main__":
    main()
