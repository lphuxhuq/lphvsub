"""Scene cut detector — nhận diện các điểm chuyển cảnh trong video bằng FFmpeg.

Giúp Voice Sync scheduler không để câu thoại của nhân vật này tràn qua
phân cảnh quay của nhân vật khác (Scene Drift Guard).
"""
from __future__ import annotations

import re
import subprocess
from bisect import bisect_right

from autodub.utils import setup_logging

logger = setup_logging("autodub.scene_detector")

_PTS_TIME_RE = re.compile(r"pts_time:([0-9.]+)")


def parse_scene_cut_timestamps(output_text: str) -> list[float]:
    """Phân tích danh sách timestamp (giây) từ log filter select scene của FFmpeg."""
    cuts: list[float] = []
    for match in _PTS_TIME_RE.finditer(output_text):
        try:
            t = float(match.group(1))
            cuts.append(t)
        except ValueError:
            continue
    cuts.sort()
    return cuts


def detect_scene_cuts(video_path: str, threshold: float = 0.35,
                       timeout_s: float = 60.0) -> list[float]:
    """Chạy FFmpeg scan điểm chuyển cảnh nhanh (không encode, chỉ đọc frame header)."""
    if not video_path:
        return []

    cmd = [
        "ffmpeg", "-hide_banner", "-nostats",
        "-i", video_path,
        "-filter:v", f"select='gt(scene,{threshold:.2f})',showinfo",
        "-f", "null", "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        # showinfo xuất log ra stderr
        cuts = parse_scene_cut_timestamps(res.stderr or "")
        logger.info(f"Phát hiện {len(cuts)} điểm chuyển cảnh trong video")
        return cuts
    except Exception as e:
        logger.warning(f"Không quét được chuyển cảnh video: {e}")
        return []


def find_next_scene_boundary(current_time: float, scene_cuts: list[float] | None) -> float | None:
    """Tìm điểm chuyển cảnh gần nhất sau `current_time`."""
    if not scene_cuts:
        return None
    idx = bisect_right(scene_cuts, current_time)
    if idx < len(scene_cuts):
        return scene_cuts[idx]
    return None
