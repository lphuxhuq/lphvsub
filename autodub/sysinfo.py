"""Đọc thông tin phần cứng (RAM/CPU) — không cần thư viện ngoài.

Dùng cho "bộ điều phối tài nguyên": máy ít RAM thì tự hạ số tiến trình giọng
đọc, tránh tràn bộ nhớ thay vì để hệ điều hành swap đến đứng máy. psutil KHÔNG
có trong venv chính nên đọc thẳng từ Windows API qua ctypes; máy POSIX (dev
chạy test trên CI) dùng os.sysconf. Mọi hàm trả ``None`` khi không đọc được —
bên gọi phải coi None là "không rõ" và giữ mặc định an toàn.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache

_BYTES_PER_GB = 1024 ** 3


def _windows_memory_status():
    """(total_bytes, avail_bytes) từ GlobalMemoryStatusEx, hoặc None."""
    import ctypes

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullTotalPhys, status.ullAvailPhys


def _posix_memory_status():
    """(total_bytes, avail_bytes) qua os.sysconf, hoặc None."""
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        total = os.sysconf("SC_PHYS_PAGES") * page
        avail = os.sysconf("SC_AVPHYS_PAGES") * page
        return total, avail
    except (ValueError, OSError, AttributeError):
        return None


def _memory_status():
    try:
        if sys.platform == "win32":
            return _windows_memory_status()
        return _posix_memory_status()
    except Exception:
        return None


@lru_cache(maxsize=1)
def total_ram_gb() -> float | None:
    """Tổng RAM vật lý (GB) — bất biến nên cache được."""
    status = _memory_status()
    if status is None:
        return None
    return status[0] / _BYTES_PER_GB


def available_ram_gb() -> float | None:
    """RAM còn trống (GB) — thay đổi liên tục, KHÔNG cache."""
    status = _memory_status()
    if status is None:
        return None
    return status[1] / _BYTES_PER_GB


def gpu_vram_status_gb() -> tuple[float, float] | None:
    """(total_vram_gb, free_vram_gb) từ PyTorch CUDA hoặc nvidia-smi, hoặc None."""
    # 1. Thử qua PyTorch nếu torch có sẵn và hỗ trợ CUDA
    try:
        import torch
        if torch.cuda.is_available():
            free_bytes, total_bytes = torch.cuda.mem_get_info()
            return total_bytes / _BYTES_PER_GB, free_bytes / _BYTES_PER_GB
    except Exception:
        pass

    # 2. Thử qua nvidia-smi trên Windows / Linux
    try:
        import subprocess
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total,memory.free",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
            creationflags=flags,
        )
        if out.returncode == 0 and out.stdout.strip():
            lines = out.stdout.strip().splitlines()
            if lines:
                parts = [float(x.strip()) for x in lines[0].split(",")]
                if len(parts) >= 2:
                    total_mb, free_mb = parts[0], parts[1]
                    return total_mb / 1024.0, free_mb / 1024.0
    except Exception:
        pass

    return None


def available_vram_gb() -> float | None:
    """VRAM khả dụng (GB); None nếu máy không có card NVIDIA / CUDA."""
    status = gpu_vram_status_gb()
    return status[1] if status is not None else None

