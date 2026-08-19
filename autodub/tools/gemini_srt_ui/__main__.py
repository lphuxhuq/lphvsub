"""Điểm khởi động chạy độc lập cho Gemini SRT Translator Pro.

Sử dụng:
    python -m autodub.tools.gemini_srt_ui [--port 5050] [--no-browser] [--host 127.0.0.1]
"""
from __future__ import annotations

import argparse
import sys
import time

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from autodub.tools.gemini_srt_ui.server_manager import GeminiSrtServerManager


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gemini SRT Translator Pro — Dịch vụ Web dịch phụ đề AI chuyên nghiệp"
    )
    parser.add_argument("--port", type=int, default=5050, help="Cổng mạng của máy chủ (mặc định: 5050)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Địa chỉ máy chủ (mặc định: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Không tự động mở trình duyệt web")

    args = parser.parse_args()

    print("=" * 60)
    print("  Gemini SRT Translator Pro — VoxDub Studio")
    print("=" * 60)
    print(f"[*] Đang khởi động Web Server trên http://{args.host}:{args.port} ...")

    manager = GeminiSrtServerManager(default_port=args.port, host=args.host)
    url = manager.start(port=args.port, open_browser=not args.no_browser)

    print(f"[+] Máy chủ đang hoạt động tại: {url}")
    print("[*] Nhấn tổ hợp phím Ctrl+C để dừng máy chủ.")
    print("=" * 60)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Đang dừng máy chủ...")
        manager.stop()
        print("[+] Đã tắt máy chủ an toàn.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
