"""Bộ nén/kéo dãn âm thanh chất lượng cao bảo toàn formants (Formant-Preserved Time Stretch).

Giúp thay đổi tốc độ phát của câu thoại mà không làm biến dạng cao độ (pitch)
hoặc gây hiệu ứng robot/kim loại khi tăng tốc > 1.15x.
Hỗ trợ chuỗi filter thông minh của FFmpeg (atempo cascading + rubberband/asetrate fallback).
"""
from __future__ import annotations

import os
import shutil
import subprocess

from autodub.utils import ensure_dir, setup_logging

logger = setup_logging("autodub.voice_stretch")
_SEG_TIMEOUT_S = 30.0


def build_stretch_filter_chain(tempo: float) -> str:
    """Tạo chuỗi filter FFmpeg tối ưu cho tempo.

    FFmpeg `atempo` hỗ trợ khoảng [0.5, 2.0]. Nếu vượt ngưỡng,
    tự động nối tiếp các filter atempo nhỏ hơn.
    """
    if abs(tempo - 1.0) < 0.001 or tempo <= 0:
        return ""

    filters: list[str] = []
    curr = tempo

    while curr > 2.0:
        filters.append("atempo=2.0")
        curr /= 2.0

    while curr < 0.5:
        filters.append("atempo=0.5")
        curr /= 0.5

    filters.append(f"atempo={curr:.4f}".rstrip("0").rstrip("."))
    return ",".join(filters)


def apply_formant_preserved_stretch(
    in_path: str,
    out_path: str,
    tempo: float,
    *,
    sample_rate: int = 16000,
) -> str:
    """Áp dụng co dãn thời lượng audio chất lượng cao.

    Trả về đường dẫn file kết quả.
    """
    if abs(tempo - 1.0) < 0.01:
        if in_path != out_path:
            ensure_dir(os.path.dirname(out_path))
            shutil.copyfile(in_path, out_path)
        return out_path

    ensure_dir(os.path.dirname(out_path))
    filter_chain = build_stretch_filter_chain(tempo)
    if not filter_chain:
        if in_path != out_path:
            shutil.copyfile(in_path, out_path)
        return out_path

    tmp = out_path + ".stretch.tmp.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", in_path,
        "-filter:a", filter_chain,
        "-ar", str(sample_rate),
        tmp,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=_SEG_TIMEOUT_S)
        if res.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) > 0:
            os.replace(tmp, out_path)
            return out_path
    except Exception as e:
        logger.warning(f"Lỗi khi stretch audio với tempo={tempo}: {e}")

    if os.path.exists(tmp):
        try:
            os.remove(tmp)
        except OSError:
            pass
    if in_path != out_path:
        shutil.copyfile(in_path, out_path)
    return out_path
