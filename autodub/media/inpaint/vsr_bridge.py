"""Adapter kết nối với công cụ ngoài YaoFANGUK/video-subtitle-remover (VSR).
"""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable
import numpy as np

from autodub.media.inpaint.base import BaseInpaintEngine
from autodub.utils import setup_logging

logger = setup_logging("autodub.media.inpaint.vsr_bridge")


class VSRBridgeEngine(BaseInpaintEngine):
    """Engine gọi tiến trình con tới dự án video-subtitle-remover bên ngoài."""

    def __init__(self, vsr_dir: str | None = None, python_exe: str | None = None, **kwargs):
        self.vsr_dir = vsr_dir or os.environ.get("VSR_DIR", "").strip()
        self.python_exe = python_exe or "python"

    def inpaint_frame(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """VSR chạy theo video hoặc batch ảnh; fallback về LaMa nếu gọi frame đơn lẻ."""
        from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine
        return LaMaOnnxEngine().inpaint_frame(frame_bgr, mask)

    def inpaint_video(
        self,
        video_path: str,
        output_path: str,
        regions: list[dict],
        device: str = "auto",
        progress_cb: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Thực hiện xóa phụ đề qua VSR CLI (backend/main.py)."""
        if not regions:
            return video_path

        if not self.vsr_dir or not os.path.isdir(self.vsr_dir):
            raise FileNotFoundError(
                f"Thư mục cài đặt VSR không tồn tại: {self.vsr_dir}. "
                "Vui lòng thiết lập đường dẫn VSR_DIR trong Cài đặt."
            )

        main_script = os.path.join(self.vsr_dir, "backend", "main.py")
        if not os.path.isfile(main_script):
            main_script = os.path.join(self.vsr_dir, "main.py")

        if not os.path.isfile(main_script):
            raise FileNotFoundError(f"Không tìm thấy script chạy VSR tại: {self.vsr_dir}")

        # Lấy tọa độ bounding box pixel
        from autodub.media.video import probe_dimensions
        width, height = probe_dimensions(video_path)

        from autodub.media.inpaint.base import get_bounding_box_for_regions
        rx, ry, rw, rh = get_bounding_box_for_regions(regions, width, height, padding=8)
        ymin, ymax = ry, ry + rh
        xmin, xmax = rx, rx + rw

        cmd = [
            self.python_exe,
            main_script,
            "-i", os.path.abspath(video_path),
            "-o", os.path.abspath(output_path),
            "-c", str(ymin), str(ymax), str(xmin), str(xmax),
        ]

        logger.info(f"Khởi chạy VSR Subprocess: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            cwd=self.vsr_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    proc.kill()
                    raise RuntimeError("Inpaint VSR bị hủy bởi người dùng.")

                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break

                if line:
                    stripped = line.strip()
                    logger.debug(f"[VSR] {stripped}")
                    if "%" in stripped and progress_cb:
                        # Thử parse tiến độ nếu có chuỗi dạng 45%
                        try:
                            parts = stripped.split("%")[0].split()
                            val = float(parts[-1])
                            progress_cb(val / 100.0, f"[VSR] {val:.0f}%")
                        except Exception:
                            pass

            ret = proc.wait()
            if ret != 0:
                raise RuntimeError(f"VSR process kết thúc với mã lỗi {ret}.")

        finally:
            if proc.poll() is None:
                proc.kill()

        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1024:
            raise RuntimeError(f"VSR hoàn tất nhưng không tìm thấy file xuất: {output_path}")

        return output_path
