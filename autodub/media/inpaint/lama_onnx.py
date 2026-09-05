"""Engine LaMa Inpainting nhúng trực tiếp qua ONNX Runtime.

Tối ưu hóa:
1. ROI Bounding-Box Crop: Chỉ đưa vùng chứa phụ đề vào mạng neural, sau đó dán đè lại
   vào khung hình lớn -> Tăng tốc 3-5 lần, không lo tràn VRAM trên video 2K/4K.
2. Streaming FFmpeg Pipes: Đọc và ghi frame tuần tự qua stdin/stdout để không ngốn RAM.
3. Hỗ trợ đa nền tảng: CUDA (NVIDIA), DirectML (AMD/Intel) và CPU.
"""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable
import numpy as np

from autodub.media.inpaint.base import (
    BaseInpaintEngine,
    convert_normalized_regions_to_mask,
    get_bounding_box_for_regions,
)
from autodub.utils import app_root, setup_logging

logger = setup_logging("autodub.media.inpaint.lama_onnx")

_SESSION_CACHE: dict[tuple[str, str], dict] = {}
_SESSION_LOCK = threading.Lock()


def default_lama_model_path() -> str:
    """Đường dẫn tệp model LaMa ONNX mặc định trong thư mục ứng dụng."""
    return os.path.join(app_root(), "models", "inpaint", "lama.onnx")


class LaMaOnnxEngine(BaseInpaintEngine):
    """Inpainting Engine sử dụng mô hình LaMa ONNX."""

    def __init__(self, model_path: str | None = None, device: str = "auto"):
        self.model_path = model_path or default_lama_model_path()
        self.device = device
        self._session = None
        self._input_names = None
        self._output_name = None

    def _ensure_session(self, device: str | None = None):
        """Khởi tạo session ONNX Runtime khi cần dùng (chia sẻ session đã nạp trước)."""
        if self._session is not None:
            return

        if not os.path.exists(self.model_path):
            logger.info(
                f"File weights LaMa ONNX chưa có tại '{self.model_path}'. "
                "Hệ thống sẽ dùng thuật toán Inpainting OpenCV Telea để tái tạo nền sạch không để lại vết mờ."
            )
            self._session = None
            return

        target_device = (device or self.device).strip().lower()
        cache_key = (os.path.abspath(self.model_path), target_device)

        with _SESSION_LOCK:
            if cache_key in _SESSION_CACHE:
                cached = _SESSION_CACHE[cache_key]
                self._session = cached["session"]
                self._input_names = cached["input_names"]
                self._input_shapes = cached["input_shapes"]
                self._output_name = cached["output_name"]
                self._fixed_h = cached["fixed_h"]
                self._fixed_w = cached["fixed_w"]
                self._cached_mask_key = None
                self._cached_mask_tensor = None
                logger.debug("Dùng lại session LaMa ONNX đã nạp sẵn từ cache")
                return

            try:
                import onnxruntime as ort
            except ImportError:
                logger.warning(
                    "Chưa cài đặt onnxruntime — chuyển sang Inpainting OpenCV Telea."
                )
                self._session = None
                return

            available_providers = ort.get_available_providers()

            providers = []
            if target_device == "cuda":
                if "CUDAExecutionProvider" in available_providers:
                    providers.append("CUDAExecutionProvider")
                else:
                    logger.warning("Yêu cầu CUDA nhưng không tìm thấy CUDAExecutionProvider — fallback CPU.")
            elif target_device == "directml":
                if "DmlExecutionProvider" in available_providers:
                    providers.append("DmlExecutionProvider")
                else:
                    logger.warning("Yêu cầu DirectML nhưng không tìm thấy DmlExecutionProvider — fallback CPU.")
            elif target_device == "cpu":
                providers.append("CPUExecutionProvider")
            else:  # "auto"
                if "CUDAExecutionProvider" in available_providers:
                    providers.append("CUDAExecutionProvider")
                elif "DmlExecutionProvider" in available_providers:
                    providers.append("DmlExecutionProvider")

            providers.append("CPUExecutionProvider")

            logger.info(f"Khởi tạo LaMa ONNX Session với providers: {providers} (đang nạp weights, chờ chút)...")
            import time
            t_init_start = time.time()
            so = ort.SessionOptions()
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            session = ort.InferenceSession(self.model_path, sess_options=so, providers=providers)
            input_names = [i.name for i in session.get_inputs()]
            input_shapes = [i.shape for i in session.get_inputs()]
            output_name = session.get_outputs()[0].name
            fixed_h, fixed_w = None, None
            for shape in input_shapes:
                if shape and len(shape) == 4:
                    sh_h, sh_w = shape[2], shape[3]
                    if isinstance(sh_h, int) and sh_h > 0 and isinstance(sh_w, int) and sh_w > 0:
                        fixed_h, fixed_w = sh_h, sh_w
                        break

            active_providers = session.get_providers()
            logger.info(
                f"Nạp LaMa ONNX Session thành công ({time.time() - t_init_start:.1f}s) "
                f"— Provider hoạt động: {active_providers[0] if active_providers else 'Unknown'}"
            )

            _SESSION_CACHE[cache_key] = {
                "session": session,
                "input_names": input_names,
                "input_shapes": input_shapes,
                "output_name": output_name,
                "fixed_h": fixed_h,
                "fixed_w": fixed_w,
            }

            self._session = session
            self._input_names = input_names
            self._input_shapes = input_shapes
            self._output_name = output_name
            self._fixed_h = fixed_h
            self._fixed_w = fixed_w
            self._cached_mask_key = None
            self._cached_mask_tensor = None

    def inpaint_frame(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Inpaint 1 ảnh/patch BGR (H, W, 3) với mask (H, W)."""
        h, w = frame_bgr.shape[:2]
        if h == 0 or w == 0:
            return frame_bgr

        import cv2

        self._ensure_session()

        if self._session is None:
            mask_uint8 = (mask > 0).astype(np.uint8) * 255
            kernel = np.ones((3, 3), np.uint8)
            mask_dilated = cv2.dilate(mask_uint8, kernel, iterations=1)
            return cv2.inpaint(frame_bgr, mask_dilated, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

        fixed_h = getattr(self, "_fixed_h", None)
        fixed_w = getattr(self, "_fixed_w", None)
        if fixed_h is None or fixed_w is None:
            for shape in getattr(self, "_input_shapes", []) or []:
                if shape and len(shape) == 4:
                    sh_h, sh_w = shape[2], shape[3]
                    if isinstance(sh_h, int) and sh_h > 0 and isinstance(sh_w, int) and sh_w > 0:
                        fixed_h, fixed_w = sh_h, sh_w
                        self._fixed_h, self._fixed_w = fixed_h, fixed_w
                        break

        if fixed_h and fixed_w:
            # Mô hình kích thước cố định (ví dụ 512x512)
            cur_img = cv2.resize(frame_bgr, (fixed_w, fixed_h), interpolation=cv2.INTER_LINEAR)
            img_rgb = cur_img[:, :, ::-1].astype(np.float32) / 255.0

            mask_key = (id(mask), mask.shape, fixed_w, fixed_h)
            if getattr(self, "_cached_mask_key", None) == mask_key:
                mask_tensor = self._cached_mask_tensor
            else:
                cur_mask = cv2.resize((mask > 0).astype(np.uint8) * 255, (fixed_w, fixed_h), interpolation=cv2.INTER_NEAREST)
                mask_f = (cur_mask > 0).astype(np.float32)
                mask_tensor = mask_f[np.newaxis, np.newaxis, :, :].astype(np.float32)
                self._cached_mask_key = mask_key
                self._cached_mask_tensor = mask_tensor

            img_tensor = np.transpose(img_rgb, (2, 0, 1))[np.newaxis, :, :, :].astype(np.float32)

            inputs = {}
            for name in self._input_names:
                lower_name = name.lower()
                if "image" in lower_name or "img" in lower_name or "input" in lower_name:
                    inputs[name] = img_tensor
                elif "mask" in lower_name:
                    inputs[name] = mask_tensor
                else:
                    if len(inputs) == 0:
                        inputs[name] = img_tensor
                    else:
                        inputs[name] = mask_tensor

            outputs = self._session.run([self._output_name], inputs)
            out_tensor = outputs[0][0]  # (3, fixed_h, fixed_w)

            out_rgb = np.transpose(out_tensor, (1, 2, 0))
            out_rgb = np.clip(out_rgb * 255.0, 0, 255).astype(np.uint8)
            out_bgr_fixed = out_rgb[:, :, ::-1]

            # Resize ngược lại kích thước ban đầu (w, h)
            out_bgr = cv2.resize(out_bgr_fixed, (w, h), interpolation=cv2.INTER_LANCZOS4)
        else:
            # Mô hình dynamic resolution: Pad kích thước chia hết cho 8
            img_rgb = frame_bgr[:, :, ::-1].astype(np.float32) / 255.0
            mask_f = (mask > 0).astype(np.float32)

            pad_h = (8 - (h % 8)) % 8
            pad_w = (8 - (w % 8)) % 8

            if pad_h > 0 or pad_w > 0:
                img_rgb = np.pad(img_rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
                mask_f = np.pad(mask_f, ((0, pad_h), (0, pad_w)), mode="reflect")

            img_tensor = np.transpose(img_rgb, (2, 0, 1))[np.newaxis, :, :, :].astype(np.float32)
            mask_tensor = mask_f[np.newaxis, np.newaxis, :, :].astype(np.float32)

            inputs = {}
            for name in self._input_names:
                lower_name = name.lower()
                if "image" in lower_name or "img" in lower_name or "input" in lower_name:
                    inputs[name] = img_tensor
                elif "mask" in lower_name:
                    inputs[name] = mask_tensor
                else:
                    if len(inputs) == 0:
                        inputs[name] = img_tensor
                    else:
                        inputs[name] = mask_tensor

            outputs = self._session.run([self._output_name], inputs)
            out_tensor = outputs[0][0]  # (3, H_padded, W_padded)

            if pad_h > 0 or pad_w > 0:
                out_tensor = out_tensor[:, :h, :w]

            out_rgb = np.transpose(out_tensor, (1, 2, 0))
            out_rgb = np.clip(out_rgb * 255.0, 0, 255).astype(np.uint8)
            out_bgr = out_rgb[:, :, ::-1]

        # Blend: chỉ lấy pixel từ out_bgr ở những nơi mask > 0 để bảo toàn 100% chi tiết vùng không xóa
        result = frame_bgr.copy()
        mask_binary = (mask[:h, :w] > 0)
        result[mask_binary] = out_bgr[mask_binary]

        return result

    def inpaint_video(
        self,
        video_path: str,
        output_path: str,
        regions: list[dict],
        device: str = "auto",
        progress_cb: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Inpaint toàn bộ video bằng streaming FFmpeg pipes."""
        if not regions:
            return video_path

        from autodub.media.retime import probe_video_info
        orig_dur, fps_str = probe_video_info(video_path)
        fps = float(eval(fps_str)) if fps_str and "/" in fps_str else (float(fps_str) if fps_str else 30.0)

        # Đọc width, height
        from autodub.media.video import probe_dimensions
        width, height = probe_dimensions(video_path)

        total_frames = max(1, int(round(orig_dur * fps)))

        # Tính toán ROI bounding box
        rx, ry, rw, rh = get_bounding_box_for_regions(regions, width, height, padding=16)
        full_mask = convert_normalized_regions_to_mask(regions, width, height)
        roi_mask = full_mask[ry : ry + rh, rx : rx + rw]

        logger.info(
            f"Bắt đầu Inpaint Video {width}x{height} ({total_frames} frames). "
            f"Khu vực ROI Bounding-Box: ({rx}, {ry}, {rw}, {rh})"
        )

        self._ensure_session(device=device)

        frame_bytes = width * height * 3

        # Lệnh FFmpeg giải mã frame BGR
        dec_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-",
        ]

        # Lệnh FFmpeg mã hóa video kết quả
        enc_cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{width}x{height}",
            "-r", f"{fps:.3f}",
            "-i", "-",
            "-i", video_path,
            "-map", "0:v",
            "-map", "1:a?",
            "-c:v", "libx264",
            "-crf", "17",
            "-preset", "fast",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        dec_proc = subprocess.Popen(
            dec_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=frame_bytes * 4,
        )
        enc_proc = subprocess.Popen(
            enc_cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=frame_bytes * 4,
        )

        frame_idx = 0
        import time
        t_start_inpaint = time.time()
        prev_patch = None
        prev_clean_patch = None
        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    logger.warning("Đã nhận tín hiệu HỦY inpaint video.")
                    raise RuntimeError("Inpaint video bị hủy bởi người dùng.")

                raw_frame = dec_proc.stdout.read(frame_bytes)
                if not raw_frame or len(raw_frame) < frame_bytes:
                    break

                # Chuyển raw bytes -> numpy BGR (H, W, 3)
                frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((height, width, 3)).copy()

                # Crop ROI patch
                patch = frame[ry : ry + rh, rx : rx + rw]

                # Tái sử dụng kết quả nếu patch giống hệt frame trước (tiết kiệm GPU với freeze-frame, slides, 24->30fps judder)
                if prev_patch is not None and prev_clean_patch is not None and np.array_equal(patch, prev_patch):
                    clean_patch = prev_clean_patch
                else:
                    clean_patch = self.inpaint_frame(patch, roi_mask)
                    prev_patch = patch.copy()
                    prev_clean_patch = clean_patch.copy()

                # Dán đè lại vào frame gốc
                frame[ry : ry + rh, rx : rx + rw] = clean_patch

                # Ghi vào encoder pipe
                enc_proc.stdin.write(frame.tobytes())

                frame_idx += 1
                if frame_idx == 1 or frame_idx % 30 == 0 or frame_idx == total_frames:
                    pct = min(1.0, frame_idx / total_frames)
                    elapsed = max(0.001, time.time() - t_start_inpaint)
                    fps_val = frame_idx / elapsed
                    eta_s = int((total_frames - frame_idx) / max(0.001, fps_val))
                    eta_str = f"{eta_s // 60}m{eta_s % 60:02d}s" if eta_s >= 60 else f"{eta_s}s"
                    msg = (
                        f"[AI-INPAINT] {int(pct * 100)}% "
                        f"({frame_idx}/{total_frames} frames | {fps_val:.1f} fps | ETA: ~{eta_str})"
                    )
                    logger.info(msg)
                    if progress_cb:
                        progress_cb(pct, msg)

        finally:
            if dec_proc.stdout:
                dec_proc.stdout.close()
            dec_proc.kill()

            if enc_proc.stdin:
                enc_proc.stdin.close()
            enc_proc.wait()

        if progress_cb:
            progress_cb(1.0, "[AI-INPAINT] Hoàn tất xóa phụ đề bằng AI.")

        return output_path
