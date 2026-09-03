"""Gói AI Inpainting Subtitle Remover cho VoxDub / LPHVsub.
"""
from __future__ import annotations

import os
import threading
from typing import Callable

from autodub.media.inpaint.base import (
    BaseInpaintEngine,
    convert_normalized_regions_to_mask,
    get_bounding_box_for_regions,
)
from autodub.media.inpaint.cache import (
    compute_inpaint_hash,
    get_cached_clean_video,
    get_inpaint_cache_target,
)
from autodub.utils import setup_logging

logger = setup_logging("autodub.media.inpaint")


def get_inpaint_engine(engine_type: str = "lama_onnx", **kwargs) -> BaseInpaintEngine:
    """Khởi tạo engine inpainting theo loại chỉ định."""
    et = engine_type.strip().lower()
    if et in ("vsr", "vsr_cli", "vsr_bridge"):
        from autodub.media.inpaint.vsr_bridge import VSRBridgeEngine
        return VSRBridgeEngine(**kwargs)
    # Mặc định: LaMa ONNX
    from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine
    return LaMaOnnxEngine(**kwargs)


def inpaint_video_with_cache(
    video_path: str,
    regions: list[dict],
    cache_dir: str | None = None,
    engine_type: str = "lama_onnx",
    device: str = "auto",
    model_path: str | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    """Wrapper cấp cao: Xóa phụ đề video bằng AI và tận dụng bộ nhớ đệm (Cache).

    Nếu video sạch đã có trong cache và thông số không đổi, trả về ngay lập tức (0 giây).
    """
    if not regions:
        logger.info("Không có vùng ROI phụ đề nào cần xóa — giữ nguyên video gốc.")
        return video_path

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video không tồn tại: {video_path}")

    # 1. Tính toán cache key
    cache_key = compute_inpaint_hash(
        video_path=video_path,
        regions=regions,
        engine_name=engine_type,
        model_id=model_path or "",
    )

    # 2. Kiểm tra cache
    cached_path = get_cached_clean_video(cache_key, cache_dir=cache_dir)
    if cached_path:
        logger.info(f"Đã tìm thấy video sạch trong Cache ({cache_key[:12]}) — bỏ qua bước Inpaint.")
        if progress_cb:
            progress_cb(1.0, "Đã lấy video sạch từ bộ nhớ đệm.")
        return cached_path

    target_path = get_inpaint_cache_target(cache_key, cache_dir=cache_dir)
    temp_target = f"{target_path}.temp.mp4"

    logger.info(f"Bắt đầu xóa phụ đề bằng AI Inpaint ({engine_type}, device={device})...")
    engine = get_inpaint_engine(engine_type=engine_type, model_path=model_path)

    try:
        engine.inpaint_video(
            video_path=video_path,
            output_path=temp_target,
            regions=regions,
            device=device,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
        )
        if os.path.exists(temp_target) and os.path.getsize(temp_target) > 1024:
            if os.path.exists(target_path):
                try:
                    os.remove(target_path)
                except OSError:
                    pass
            os.rename(temp_target, target_path)
            logger.info(f"Đã hoàn thành AI Inpaint và lưu vào cache: {target_path}")
            return target_path
        else:
            raise RuntimeError("Quá trình Inpaint kết thúc nhưng không tạo ra video hợp lệ.")
    except Exception as e:
        if os.path.exists(temp_target):
            try:
                os.remove(temp_target)
            except OSError:
                pass
        raise e


__all__ = [
    "BaseInpaintEngine",
    "convert_normalized_regions_to_mask",
    "get_bounding_box_for_regions",
    "compute_inpaint_hash",
    "get_cached_clean_video",
    "get_inpaint_cache_target",
    "get_inpaint_engine",
    "inpaint_video_with_cache",
]
