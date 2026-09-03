"""Engine trích xuất và xuất bản video ngắn (Shorts / TikTok / Reels) 9:16.

Hỗ trợ cắt lát phụ đề ASS tương ứng theo khoảng thời gian [start_time, end_time],
dịch chuyển timestamp về 00:00:00.00, kết hợp Smart Auto-Reframe (9:16)
và mã hóa video chất lượng cao bằng FFmpeg.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from typing import Any

from autodub.media.subtitle import (
    build_aspect_ratio_filter,
    escape_subtitles_path,
)
from autodub.utils import ffmpeg_timeout_s, setup_logging

logger = setup_logging("autodub.media.clipper")


def _ass_time_to_seconds(time_str: str) -> float:
    """Đổi định dạng thời gian ASS 'H:MM:SS.cs' sang giây (float)."""
    match = re.match(r"(\d+):(\d{2}):(\d{2})\.(\d{2})", time_str.strip())
    if not match:
        return 0.0
    h, m, s, cs = match.groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(cs) / 100.0


def _seconds_to_ass_time(seconds: float) -> str:
    """Đổi số giây sang định dạng thời gian ASS 'H:MM:SS.cs'."""
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    s -= h * 3600
    m = int(s // 60)
    s -= m * 60
    sec = int(s)
    cs = int(round((s - sec) * 100))
    if cs >= 100:
        cs = 0
        sec += 1
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def slice_ass_subtitles(ass_text: str, start_time: float, end_time: float) -> str:
    """Cắt và dịch chuyển timestamp các dòng thoại ASS nằm trong khoảng [start_time, end_time].
    
    Các câu thoại bên ngoài khoảng thời gian sẽ bị loại bỏ.
    Các câu thoại bên trong sẽ được trừ đi `start_time` để đồng bộ hoàn hảo với video clip cắt con.
    """
    if not ass_text:
        return ""

    lines = ass_text.splitlines()
    output_lines = []
    in_events = False

    for line in lines:
        stripped = line.strip()
        if stripped.lower() == "[events]":
            in_events = True
            output_lines.append(line)
            continue
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_events = False
            output_lines.append(line)
            continue

        if not in_events:
            output_lines.append(line)
            continue

        if line.startswith("Format:"):
            output_lines.append(line)
            continue

        if line.startswith("Dialogue:"):
            # Cấu trúc: Dialogue: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
            parts = line.split(",", 9)
            if len(parts) == 10:
                t_start = _ass_time_to_seconds(parts[1])
                t_end = _ass_time_to_seconds(parts[2])

                # Kiểm tra xem dòng thoại có nằm trong khoảng [start_time, end_time] hay không
                if t_end <= start_time or t_start >= end_time:
                    continue  # Ngoài dải -> Bỏ qua

                # Cắt bớt nếu thoại chườm ra ngoài mốc cắt
                clipped_s = max(start_time, t_start)
                clipped_e = min(end_time, t_end)

                # Dịch chuyển mốc về 0
                shifted_s = clipped_s - start_time
                shifted_e = clipped_e - start_time

                if shifted_e > shifted_s:
                    parts[1] = _seconds_to_ass_time(shifted_s)
                    parts[2] = _seconds_to_ass_time(shifted_e)
                    output_lines.append(",".join(parts))
            else:
                output_lines.append(line)
        else:
            output_lines.append(line)

    return "\n".join(output_lines) + "\n"


def build_short_export_command(
    source_video: str,
    source_audio: str | None,
    ass_sub_path: str | None,
    start_time: float,
    end_time: float,
    output_path: str,
    aspect_preset: str = "tiktok_9_16",
    reframe_mode: str = "blur",
    video_w: int = 1920,
    video_h: int = 1080,
) -> list[str]:
    duration = max(1.0, end_time - start_time)

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", f"{start_time:.2f}",
        "-t", f"{duration:.2f}",
        "-i", source_video,
    ]

    has_separate_audio = source_audio and os.path.exists(source_audio)
    if has_separate_audio:
        cmd.extend([
            "-ss", f"{start_time:.2f}",
            "-t", f"{duration:.2f}",
            "-i", source_audio,
        ])

    # Xây dựng Video Filtergraph
    filter_chains = []
    
    # 1. Aspect Ratio / Reframe
    reframe_spec = build_aspect_ratio_filter(
        aspect_preset, video_w, video_h, reframe_mode=reframe_mode
    )
    if reframe_spec:
        f_str, tw, th = reframe_spec
        filter_chains.append(f_str)

    # 2. Burn ASS Subtitles
    if ass_sub_path and os.path.exists(ass_sub_path):
        escaped_ass = escape_subtitles_path(ass_sub_path)
        filter_chains.append(f"subtitles='{escaped_ass}'")

    if filter_chains:
        cmd.extend(["-vf", ",".join(filter_chains)])

    # Audio mapping
    if has_separate_audio:
        cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])
    else:
        cmd.extend(["-map", "0:v:0", "-map", "0:a:0?"])

    cmd.extend([
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ])

    return cmd


def export_short_clip(
    source_video: str,
    source_audio: str | None,
    ass_sub_path: str | None,
    start_time: float,
    end_time: float,
    output_path: str,
    aspect_preset: str = "tiktok_9_16",
    reframe_mode: str = "blur",
    video_w: int = 1920,
    video_h: int = 1080,
    reporter: Any = None,
) -> str:
    """Cắt và xuất file video ngắn hoàn chỉnh."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    cmd = build_short_export_command(
        source_video=source_video,
        source_audio=source_audio,
        ass_sub_path=ass_sub_path,
        start_time=start_time,
        end_time=end_time,
        output_path=output_path,
        aspect_preset=aspect_preset,
        reframe_mode=reframe_mode,
        video_w=video_w,
        video_h=video_h,
    )

    logger.info(f"Đang render clip ngắn ({start_time:.1f}s -> {end_time:.1f}s) -> {output_path}")
    if reporter:
        reporter.emit(10, f"Đang xuất clip ngắn: {os.path.basename(output_path)}")

    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if proc.returncode != 0:
        logger.error(f"Render clip ngắn thất bại: {proc.stderr[:400]}")
        raise RuntimeError(f"FFmpeg render clip ngắn lỗi: {proc.stderr[-300:]}")

    logger.info(f"Đã xuất thành công clip ngắn: {output_path}")
    return output_path
