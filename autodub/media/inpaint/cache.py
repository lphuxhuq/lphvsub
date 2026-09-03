"""Quản lý bộ nhớ đệm (Cache) cho các video đã xóa phụ đề bằng AI Inpaint.
"""
from __future__ import annotations

import hashlib
import json
import os

from autodub.config import cache_dir as global_cache_dir
from autodub.utils import setup_logging

logger = setup_logging("autodub.media.inpaint.cache")


def get_inpaint_cache_dir(custom_dir: str | None = None) -> str:
    """Thư mục lưu video inpaint cache."""
    if custom_dir:
        base = custom_dir
    else:
        base = os.path.join(global_cache_dir(), "inpaint_videos")
    os.makedirs(base, exist_ok=True)
    return base



def compute_inpaint_hash(
    video_path: str,
    regions: list[dict],
    engine_name: str,
    model_id: str = "",
) -> str:
    """Tính mã băm SHA-256 duy nhất đại diện cho video nguồn, vùng ROI và model.

    Sử dụng dung lượng + thời gian sửa đổi + 64KB đầu/cuối của file video để
    đảm bảo tốc độ tức thì mà không cần đọc toàn bộ video lớn.
    """
    hasher = hashlib.sha256()

    # 1. Thông tin file video
    if os.path.exists(video_path):
        stat = os.stat(video_path)
        hasher.update(str(stat.st_size).encode("utf-8"))
        hasher.update(str(stat.st_mtime).encode("utf-8"))

        # Đọc 64KB đầu và 64KB cuối
        try:
            with open(video_path, "rb") as f:
                head = f.read(65536)
                hasher.update(head)
                if stat.st_size > 131072:
                    f.seek(-65536, os.SEEK_END)
                    tail = f.read(65536)
                    hasher.update(tail)
        except OSError as e:
            logger.warning(f"Không thể đọc một phần video để tính hash: {e}")
            hasher.update(video_path.encode("utf-8"))
    else:
        hasher.update(video_path.encode("utf-8"))

    # 2. Danh sách vùng ROI chuẩn hóa
    normalized_regions = []
    for r in regions or []:
        normalized_regions.append({
            "x": round(float(r.get("x", 0.0)), 4),
            "y": round(float(r.get("y", 0.0)), 4),
            "w": round(float(r.get("w", 0.0)), 4),
            "h": round(float(r.get("h", 0.0)), 4),
            "t_start": r.get("t_start"),
            "t_end": r.get("t_end"),
        })
    # Sort theo tọa độ để đảm bảo thứ tự không làm đổi hash
    normalized_regions.sort(key=lambda item: (item["x"], item["y"], item["w"], item["h"]))
    regions_json = json.dumps(normalized_regions, sort_keys=True)
    hasher.update(regions_json.encode("utf-8"))

    # 3. Model & Engine metadata
    hasher.update(engine_name.strip().lower().encode("utf-8"))
    hasher.update(model_id.strip().lower().encode("utf-8"))

    return hasher.hexdigest()


def get_inpaint_cache_target(cache_key: str, cache_dir: str | None = None) -> str:
    """Trả về đường dẫn tệp video kết quả trong thư mục cache."""
    cdir = get_inpaint_cache_dir(cache_dir)
    return os.path.join(cdir, f"clean_{cache_key}.mp4")


def get_cached_clean_video(cache_key: str, cache_dir: str | None = None) -> str | None:
    """Kiểm tra và trả về đường dẫn video sạch trong cache nếu hợp lệ (dung lượng > 1KB)."""
    target = get_inpaint_cache_target(cache_key, cache_dir)
    if os.path.exists(target):
        try:
            if os.path.getsize(target) > 1024:
                return target
        except OSError:
            pass
    return None
