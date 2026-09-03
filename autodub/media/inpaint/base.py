"""Lớp cơ sở (Base Class) và các hàm tiện ích cho AI Inpainting Subtitle Remover.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Callable
import numpy as np

from autodub.utils import setup_logging

logger = setup_logging("autodub.media.inpaint")


def convert_normalized_regions_to_mask(
    regions: list[dict],
    width: int,
    height: int,
) -> np.ndarray:
    """Tạo ma trận mask nhị phân 2D (uint8 0 hoặc 255) từ danh sách vùng chuẩn hóa 0..1.

    Giá trị 255 đại diện cho vùng cần xóa (inpaint), 0 là vùng giữ nguyên.
    """
    mask = np.zeros((height, width), dtype=np.uint8)
    for r in regions:
        rx = float(r.get("x", 0.0))
        ry = float(r.get("y", 0.0))
        rw = float(r.get("w", 0.0))
        rh = float(r.get("h", 0.0))

        x = int(round(rx * width))
        y = int(round(ry * height))
        w = int(round(rw * width))
        h = int(round(rh * height))

        x = max(0, min(x, width - 1))
        y = max(0, min(y, height - 1))
        w = max(1, min(w, width - x))
        h = max(1, min(h, height - y))

        mask[y : y + h, x : x + w] = 255

    return mask


def get_bounding_box_for_regions(
    regions: list[dict],
    width: int,
    height: int,
    padding: int = 16,
) -> tuple[int, int, int, int]:
    """Tìm bounding box bao quanh tất cả các vùng ROI chuẩn hóa.

    Trả về (x, y, w, h) chuẩn pixel chẵn, kèm padding để mở rộng vùng biên.
    """
    if not regions:
        return 0, 0, width, height

    min_x = width
    min_y = height
    max_x = 0
    max_y = 0

    for r in regions:
        rx = float(r.get("x", 0.0))
        ry = float(r.get("y", 0.0))
        rw = float(r.get("w", 0.0))
        rh = float(r.get("h", 0.0))

        x1 = int(round(rx * width))
        y1 = int(round(ry * height))
        x2 = x1 + int(round(rw * width))
        y2 = y1 + int(round(rh * height))

        min_x = min(min_x, x1)
        min_y = min(min_y, y1)
        max_x = max(max_x, x2)
        max_y = max(max_y, y2)

    min_x = max(0, min_x - padding)
    min_y = max(0, min_y - padding)
    max_x = min(width, max_x + padding)
    max_y = min(height, max_y + padding)

    # Đảm bảo chia hết cho 2
    min_x = min_x - (min_x % 2)
    min_y = min_y - (min_y % 2)
    w = max_x - min_x
    h = max_y - min_y
    w = w + (w % 2)
    h = h + (h % 2)
    w = min(w, width - min_x)
    h = min(h, height - min_y)

    return min_x, min_y, max(2, w), max(2, h)


class BaseInpaintEngine(ABC):
    """Abstract class cho các engine inpainting xóa phụ đề."""

    @abstractmethod
    def inpaint_frame(self, frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
        """Inpaint một khung hình đơn lẻ.

        Args:
            frame_bgr: Ma trận ảnh BGR (H, W, 3) uint8.
            mask: Ma trận nhị phân (H, W) uint8 (255 là vùng xóa).

        Returns:
            Ma trận ảnh BGR (H, W, 3) đã xóa vật thể.
        """
        pass

    @abstractmethod
    def inpaint_video(
        self,
        video_path: str,
        output_path: str,
        regions: list[dict],
        device: str = "auto",
        progress_cb: Callable[[float, str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> str:
        """Inpaint toàn bộ video theo vùng chỉ định.

        Args:
            video_path: Đường dẫn video nguồn.
            output_path: Đường dẫn video xuất kết quả.
            regions: Danh sách vùng ROI chuẩn hóa (0..1).
            device: Thiết bị xử lý ("auto", "cuda", "directml", "cpu").
            progress_cb: Callback cập nhật tiến độ (progress 0..1, message).
            cancel_event: Event báo hiệu dừng khẩn cấp.

        Returns:
            Đường dẫn video kết quả (output_path).
        """
        pass
