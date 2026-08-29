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


def find_prev_scene_boundary(current_time: float, scene_cuts: list[float] | None) -> float | None:
    """Tìm điểm chuyển cảnh gần nhất trước hoặc bằng `current_time`."""
    if not scene_cuts:
        return None
    idx = bisect_right(scene_cuts, current_time) - 1
    if 0 <= idx < len(scene_cuts):
        return scene_cuts[idx]
    return None


def snap_to_scene_boundaries(
    start: float,
    end: float,
    scene_cuts: list[float] | None,
    threshold_s: float = 0.45,
) -> tuple[float, float]:
    """Áp dụng Dual-Edge Scene Guard:

    1. Left-Edge Snapping:
       Nếu có điểm chuyển cảnh T_cut nằm ngay sau `start` (start < T_cut <= start + threshold_s)
       và câu thoại kéo dài sâu vào cảnh mới (end > T_cut + 0.25s), câu thoại chắc chắn
       thuộc về cảnh mới. Snap `start = T_cut + 0.02s` để phụ đề/giọng đọc không bị hiện/nói trước
       khi khung hình chuyển cảnh.

    2. Right-Edge Snapping:
       Nếu câu thoại kết thúc sau điểm chuyển cảnh T_next một khoảng rất nhỏ (end >= T_next và end - T_next <= 0.20s),
       clamp `end = T_next - 0.02s` để câu thoại kết thúc gọn gàng trong cảnh hiện tại.
    """
    if not scene_cuts:
        return start, end

    s = float(start)
    e = float(end)

    # 1. Left-Edge Guard: Chặn không cho nói trước cảnh
    next_cut = find_next_scene_boundary(s, scene_cuts)
    if next_cut is not None and (next_cut - s) <= threshold_s:
        # Nếu câu kéo dài qua điểm cut
        if e > next_cut + 0.25:
            s = next_cut + 0.02
            if s >= e:
                e = s + 0.2

    # 2. Right-Edge Guard: Chặn không cho đuôi câu tràn nhẹ qua cảnh kế
    prev_cut = find_prev_scene_boundary(e, scene_cuts)
    if prev_cut is not None and prev_cut > s + 0.3:
        if (e - prev_cut) <= 0.20:
            e = max(s + 0.2, prev_cut - 0.02)

    return round(s, 3), round(e, 3)


def load_or_detect_scene_cuts(
    video_path: str,
    work_dir: str | None = None,
    threshold: float = 0.35,
    timeout_s: float = 60.0,
) -> list[float]:
    """Nạp cache scene_cuts từ data/scene_cuts.json hoặc quét mới bằng FFmpeg."""
    import json
    import os

    if not video_path or not os.path.exists(video_path):
        return []

    cache_file = None
    if work_dir:
        cache_file = os.path.join(work_dir, "data", "scene_cuts.json")
        if os.path.isfile(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if isinstance(cached, list):
                    return [float(x) for x in cached]
            except Exception:
                pass

    cuts = detect_scene_cuts(video_path, threshold=threshold, timeout_s=timeout_s)

    if cache_file and cuts:
        try:
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cuts, f)
        except Exception:
            pass

    return cuts

