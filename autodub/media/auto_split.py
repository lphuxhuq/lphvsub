"""Auto-Splitter Engine.

Tự động chia nhỏ video dài thành các phần nhỏ (ví dụ 10 phút)
chuẩn xác theo ranh giới câu thoại.
Sử dụng FFmpeg stream copy (-c copy) nên tốc độ cực nhanh (vài giây), không giảm chất lượng.
"""

from __future__ import annotations

import os
import subprocess

from autodub.utils import setup_logging

logger = setup_logging("autodub.auto_split")


def split_video(
    video_path: str,
    segments: list[dict],
    chunk_minutes: int = 10,
    min_gap_s: float = 0.3,
) -> list[str]:
    """Chia video thành nhiều tệp nhỏ.

    Args:
        video_path: Đường dẫn video gốc đã render xong.
        segments: Mảng segments chứa mốc thời gian dub_start, dub_end.
        chunk_minutes: Thời lượng mong muốn mỗi phần (phút).
        min_gap_s: Tìm khoảng im lặng tối thiểu giữa 2 câu để làm điểm cắt.

    Returns:
        Danh sách đường dẫn các file đã cắt.
    """
    if not os.path.isfile(video_path):
        return []
    if not segments or chunk_minutes <= 0:
        return [video_path]

    target_duration_s = chunk_minutes * 60.0

    # Lọc các đoạn có thoại hợp lệ và sắp xếp
    valid_segs = sorted(
        [s for s in segments if "dub_start" in s and "dub_end" in s],
        key=lambda x: x["dub_start"],
    )
    if not valid_segs:
        return [video_path]

    split_points = [0.0]
    current_start = 0.0

    for i in range(len(valid_segs) - 1):
        curr = valid_segs[i]
        nxt = valid_segs[i + 1]

        # Thời lượng phần hiện tại nếu cắt sau câu này
        current_len = curr["dub_end"] - current_start

        # Nếu đã đạt/vượt thời lượng mong muốn
        if current_len >= target_duration_s:
            gap = nxt["dub_start"] - curr["dub_end"]
            if gap >= min_gap_s:
                # Cắt ở giữa khoảng im lặng
                split_point = curr["dub_end"] + (gap / 2.0)
                split_points.append(round(split_point, 3))
                current_start = split_point

    # Lấy tổng thời lượng video từ FFmpeg hoặc từ segments
    try:
        from autodub.media.video import probe_duration_s

        total_dur = probe_duration_s(video_path)
    except Exception:
        total_dur = None

    if not total_dur or total_dur <= 0:
        total_dur = valid_segs[-1]["dub_end"] + 5.0

    split_points.append(round(total_dur, 3))

    # Nếu chỉ có 1 phần thì không cần cắt
    if len(split_points) <= 2:
        logger.info(
            f"Video {total_dur:.1f}s ngắn hơn ngưỡng chia phần ({target_duration_s}s), bỏ qua."
        )
        return [video_path]

    output_files = []
    base_dir = os.path.dirname(os.path.abspath(video_path))
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    ext = os.path.splitext(video_path)[1]

    logger.info(f"Auto-Splitter: Chia video thành {len(split_points) - 1} phần.")

    for i in range(len(split_points) - 1):
        start_t = split_points[i]
        end_t = split_points[i + 1]

        out_path = os.path.join(base_dir, f"{base_name}_part_{i + 1}{ext}")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-ss",
            str(start_t),
            "-to",
            str(end_t),
            "-c",
            "copy",
            out_path,
        ]

        # Chạy ẩn không hiện cửa sổ CMD trên Windows
        no_window = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            subprocess.run(cmd, check=True, capture_output=True, creationflags=no_window)
            output_files.append(out_path)
            logger.info(f"Đã cắt Phần {i + 1}: {start_t:.2f}s -> {end_t:.2f}s ({out_path})")
        except subprocess.CalledProcessError as e:
            logger.error(f"Lỗi khi cắt Phần {i + 1}: {e.stderr.decode('utf-8', errors='ignore')}")

    return output_files
