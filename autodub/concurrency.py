"""Điều phối tài nguyên và khóa đồng bộ GPU cho xử lý đa luồng (autodub.concurrency).

Cung cấp:
- GPU Semaphore: Tuần tự hóa các tác vụ ăn nhiều VRAM (Demucs, Whisper GPU)
  để chống lỗi CUDA OOM khi chạy 2–4 luồng song song.
- Tự động nhận diện cấu hình phần cứng (RAM, VRAM, CPU) để gợi ý mức luồng tối ưu.
"""
from __future__ import annotations

import contextlib
import os
import threading
from typing import Generator

from autodub.resources import GPU_LOCK


@contextlib.contextmanager
def gpu_resource_guard(enabled: bool = True) -> Generator[None, None, None]:
    """Context manager bảo vệ tài nguyên GPU khi nhiều luồng cùng gọi các tác vụ nặng (Demucs/Whisper)."""
    if not enabled:
        yield
        return
    with GPU_LOCK:
        yield


def detect_system_capabilities() -> dict[str, int | float | str]:
    """Nhận diện phần cứng hệ thống và đề xuất số luồng song song an toàn."""
    cpu_count = os.cpu_count() or 4
    has_cuda = False
    vram_gb = 0.0
    device_name = "CPU"

    try:
        import torch
        if torch.cuda.is_available():
            has_cuda = True
            device_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_gb = round(props.total_memory / (1024 ** 3), 1)
    except Exception:
        pass

    # Đề xuất số luồng tối ưu
    if has_cuda and vram_gb >= 8.0 and cpu_count >= 8:
        recommended_threads = 3
        max_threads = 4
    elif has_cuda and vram_gb >= 6.0:
        recommended_threads = 2
        max_threads = 3
    elif cpu_count >= 8:
        recommended_threads = 2
        max_threads = 3
    else:
        recommended_threads = 1
        max_threads = 2

    return {
        "cpu_count": cpu_count,
        "has_cuda": has_cuda,
        "device_name": device_name,
        "vram_gb": vram_gb,
        "recommended_threads": recommended_threads,
        "max_threads": max_threads,
    }
