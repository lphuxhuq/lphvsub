"""Dọn dẹp và quản lý bộ nhớ đệm, tệp tải tạm và video xem trước."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from autodub.config import cache_dir
from autodub.pipeline_cache import PipelineCacheOrchestrator, cache_root

logger = logging.getLogger("autodub.cache_cleaner")


def clean_preview_videos(
    max_age_days: float = 3.0,
    max_size_mb: float = 2048.0,
) -> dict:
    """Xóa các video xem trước cũ hoặc khi dung lượng thư mục vượt quá ngưỡng."""
    preview_dir = Path(cache_dir()) / "preview_videos"
    if not preview_dir.is_dir():
        return {"removed": 0, "reclaimed_bytes": 0}

    now = time.time()
    max_age_seconds = max_age_days * 86400.0
    max_bytes = max_size_mb * 1024 * 1024

    removed = 0
    reclaimed = 0
    files_info = []

    for item in preview_dir.iterdir():
        if item.is_file():
            try:
                st = item.stat()
                age = now - st.st_mtime
                if age > max_age_seconds:
                    size = st.st_size
                    item.unlink(missing_ok=True)
                    removed += 1
                    reclaimed += size
                else:
                    files_info.append((st.st_mtime, st.st_size, item))
            except OSError:
                pass

    # Nếu tổng dung lượng các tệp còn lại vẫn vượt max_size_mb, xóa dần tệp cũ nhất
    files_info.sort(key=lambda x: x[0])  # Sắp xếp từ cũ tới mới
    current_total = sum(f[1] for f in files_info)
    for mtime, size, path in files_info:
        if current_total <= max_bytes:
            break
        try:
            path.unlink(missing_ok=True)
            current_total -= size
            removed += 1
            reclaimed += size
        except OSError:
            pass

    return {"removed": removed, "reclaimed_bytes": reclaimed}


def clean_temp_prefetch(max_age_hours: float = 12.0) -> dict:
    """Dọn dẹp thư mục tạm voxdub_prefetch trong temp hệ thống."""
    prefetch_dir = Path(tempfile.gettempdir()) / "voxdub_prefetch"
    if not prefetch_dir.is_dir():
        return {"removed": 0, "reclaimed_bytes": 0}

    now = time.time()
    max_age_sec = max_age_hours * 3600.0
    removed = 0
    reclaimed = 0

    for item in prefetch_dir.iterdir():
        try:
            st = item.stat()
            if (now - st.st_mtime) > max_age_sec:
                if item.is_dir():
                    size = sum(f.stat().st_size for f in item.glob("**/*") if f.is_file())
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    size = st.st_size
                    item.unlink(missing_ok=True)
                removed += 1
                reclaimed += size
        except OSError:
            pass

    return {"removed": removed, "reclaimed_bytes": reclaimed}


def purge_all_caches(output_dir: str | None = None) -> dict:
    """Dọn dẹp toàn diện 1-click: video preview, tệp prefetch, waveform peaks và cache hết hạn."""
    total_removed = 0
    total_reclaimed = 0

    # 1. Dọn video preview
    res_prev = clean_preview_videos(max_age_days=0.0, max_size_mb=0.0)
    total_removed += res_prev["removed"]
    total_reclaimed += res_prev["reclaimed_bytes"]

    # 2. Dọn prefetch temp
    res_pref = clean_temp_prefetch(max_age_hours=0.0)
    total_removed += res_pref["removed"]
    total_reclaimed += res_pref["reclaimed_bytes"]

    # 3. Dọn waveform peaks và thumbnail tạm trong output_dir nếu có
    if output_dir and os.path.isdir(output_dir):
        from autodub_gui.projects import INDEX_FILE, THUMB_FILE

        targets = {THUMB_FILE, INDEX_FILE}
        for root, _dirs, files in os.walk(output_dir):
            for name in files:
                if name in targets or (
                    name.startswith("waveform_peaks") and name.endswith(".json")
                ):
                    try:
                        p = os.path.join(root, name)
                        sz = os.path.getsize(p)
                        os.remove(p)
                        total_removed += 1
                        total_reclaimed += sz
                    except OSError:
                        pass

    # 4. Dọn pipeline cache (ASR, Demucs, TTS) cũ hơn 30 ngày
    try:
        pc = PipelineCacheOrchestrator(cache_root())
        res_pipe = pc.clean_cache(max_age_seconds=30 * 86400.0)
        total_removed += res_pipe["removed_entries"]
        total_reclaimed += res_pipe["reclaimed_bytes"]
    except Exception:
        pass

    return {"removed": total_removed, "reclaimed_bytes": total_reclaimed}
