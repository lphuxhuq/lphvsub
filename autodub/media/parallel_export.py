"""Xuất video song song theo chunk — tăng tốc re-encode video dài.

Thuật toán (Parallel Chunked Export):

1. ffprobe quét toàn bộ keyframe của video nguồn (``-skip_frame nokey``).
2. Chia timeline thành N chunk sao cho biên chunk rơi ĐÚNG vào keyframe
   → mỗi chunk decode độc lập không cần frame tham chiếu trước đó.
3. Mỗi chunk chạy 1 process FFmpeg riêng (filter graph + audio mix + NVENC)
   SONG SONG — số process = tối thiểu giữa số CPU logic / 2 và giới hạn
   NVENC session (mặc định 4, consumer GPU chặn 3-8).
4. Ghép các chunk bằng concat demuxer ``-c copy`` — ZERO re-encode.
   Audio được encode sẵn trong từng chunk nên chỉ cần copy ở bước ghép.

Chất lượng bit-identical với encode 1 process: cùng codec args, cùng filter
graph, cùng audio encode — chỉ khác ranh giới GOP.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional

from autodub.utils import setup_logging

logger = setup_logging("autodub.parallel_export")

#: Số NVENC session tối đa an toàn trên GPU consumer (gặp lỗi sẽ tự hạ).
_MAX_NVENC_SESSIONS = 4
#: Thời lượng chunk tối thiểu — chunk quá ngắn tốn overhead khởi động FFmpeg.
_MIN_CHUNK_S = 12.0
#: Frame rate dự phòng khi ffprobe không đọc được fps (để tính timeout).
_FALLBACK_FPS = 30.0


class ParallelExportError(RuntimeError):
    """Lỗi xuất video song song — caller nên fallback sang đường 1 process."""


def probe_keyframes(video_path: str, timeout: int = 600) -> List[float]:
    """Trả về danh sách mốc thời gian (giây) của TẤT CẢ keyframe video.

    Dùng ffprobe show_packets với flag ``K`` — nhanh và không phụ thuộc
    format log của ffmpeg (FFmpeg 8 đã đổi format dòng progress).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,flags",
        "-of", "csv=p=0", video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ParallelExportError(f"Không quét được keyframe: {e}") from e
    if result.returncode != 0:
        raise ParallelExportError(
            f"ffprobe quét keyframe thất bại: {(result.stderr or '')[-300:]}")
    frames: List[float] = []
    for line in (result.stdout or "").splitlines():
        # CSV: "12.345000,K__" — keyframe có flag K ở vị trí đầu
        parts = line.strip().split(",")
        if len(parts) < 2 or not parts[1].startswith("K"):
            continue
        try:
            frames.append(float(parts[0]))
        except ValueError:
            continue
    if not frames:
        raise ParallelExportError("Không tìm thấy keyframe nào trong video nguồn")
    return frames


def probe_fps(video_path: str) -> float:
    """FPS trung bình của stream video (fallback 30 nếu không đọc được)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate", "-of", "json", video_path],
            capture_output=True, text=True, timeout=60,
        )
        ratio = json.loads(result.stdout)["streams"][0]["r_frame_rate"]  # "30000/1001"
        num, den = ratio.split("/")
        fps = float(num) / float(den)
        return fps if fps > 0 else _FALLBACK_FPS
    except Exception:
        return _FALLBACK_FPS


def plan_chunk_boundaries(
    keyframes: List[float],
    duration_s: float,
    target_chunks: int,
    min_chunk_s: float = _MIN_CHUNK_S,
) -> List[float]:
    """Chọn mốc cắt từ danh sách keyframe — trả về list [0, c1, c2, ..., dur].

    Chia đều ``duration / target`` rồi snap về keyframe gần nhất (chỉ snap
    LÙI để không cắt giữa 2 keyframe gây mất/giữ frame lặp). Đảm bảo:
    - Biên tăng dần nghiêm ngặt, cách nhau >= min_chunk_s
    - Biên cuối luôn == duration_s
    - Biên đầu luôn == 0
    """
    if target_chunks < 1:
        target_chunks = 1
    bounds = [0.0]
    if target_chunks <= 1 or duration_s <= min_chunk_s * target_chunks:
        return [0.0, float(duration_s)]

    kfs = sorted(set(kf for kf in keyframes if 0 < kf < duration_s))
    if not kfs:
        return [0.0, float(duration_s)]

    ideal_step = duration_s / target_chunks
    cursor = 0.0
    for i in range(1, target_chunks):
        ideal = i * ideal_step
        # Snap về keyframe gần nhất > cursor + min_chunk
        candidates = [kf for kf in kfs
                      if kf > cursor + min_chunk_s and kf < duration_s - min_chunk_s]
        if not candidates:
            break
        # Chọn keyframe gần ideal nhất
        best = min(candidates, key=lambda kf: abs(kf - ideal))
        if best <= cursor:
            continue
        bounds.append(best)
        cursor = best
    bounds.append(float(duration_s))
    return bounds


def _default_worker_count(encoder_name: str) -> int:
    """Số chunk render song song: giới hạn bởi CPU và NVENC session."""
    cpu_threads = os.cpu_count() or 4
    cpu_cap = max(2, cpu_threads // 2)
    if "NVENC" in encoder_name or "VideoToolbox" in encoder_name:
        return max(2, min(cpu_cap, _MAX_NVENC_SESSIONS))
    if "QSV" in encoder_name or "QuickSync" in encoder_name \
            or "AMF" in encoder_name or "VAAPI" in encoder_name:
        return max(2, min(cpu_cap, 3))
    # CPU libx264 — tự scale theo core, nhưng không quá 6 process (RAM/filter)
    return max(2, min(cpu_cap, 6))


def _run_chunk(
    cmd: List[str],
    timeout_s: int,
    label: str,
) -> None:
    """Chạy 1 lệnh ffmpeg chunk — raise ParallelExportError nếu fail."""
    no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_s,
            creationflags=no_win,
        )
    except subprocess.TimeoutExpired as e:
        raise ParallelExportError(f"Chunk {label} treo quá {timeout_s}s") from e
    if result.returncode != 0:
        tail = (result.stderr or "")[-1500:]
        raise ParallelExportError(f"Chunk {label} fail (code {result.returncode}): {tail}")


def _write_concat_list(chunk_paths: List[str], list_path: str) -> None:
    """Ghi file concat demuxer — path tuyệt đối dạng file URI an toàn.

    Windows path ``C:/a/b.mp4`` → ``file:C:/a/b.mp4`` (concat demuxer chấp
    nhận trực tiếp, không thêm slash đầu vì ``/C:/...`` là URI không hợp lệ).
    """
    with open(list_path, "w", encoding="utf-8") as f:
        for p in chunk_paths:
            abs_p = os.path.abspath(p).replace("\\", "/")
            uri = abs_p if abs_p.startswith("/") else "file:" + abs_p
            # escape single quotes cho concat demuxer
            uri = uri.replace("'", "'\\''")
            f.write(f"file '{uri}'\n")


def parallel_chunked_export(
    build_chunk_cmd: Callable[[str, float, float, str], List[str]],
    video_path: str,
    audio_path: str,
    output_path: str,
    duration_s: float,
    progress_cb: Optional[Callable[[float, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    max_workers: Optional[int] = None,
    min_chunk_s: float = _MIN_CHUNK_S,
    fps: Optional[float] = None,
    randomize_metadata_fn: Optional[Callable[[], None]] = None,
) -> str:
    """Xuất video song song theo chunk rồi ghép bằng concat copy.

    Tham số:
        build_chunk_cmd: callback (video, start_s, end_s, chunk_out) -> argv
            — caller dựng lệnh ffmpeg cho 1 chunk (giữ nguyên encoder args,
            filter graph, audio map). Chunk N dùng ``-ss start -to end``.
        duration_s: tổng thời lượng video.
        max_workers: số chunk render song song (None = tự tính).

    Trả về ``output_path``. Raise ``ParallelExportError`` — caller nên
    fallback về đường encode 1 process.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if duration_s <= 0:
        raise ParallelExportError("Thời lượng video không hợp lệ")

    from autodub.media.video import video_encoder_name
    encoder_name = video_encoder_name()
    workers = max_workers or _default_worker_count(encoder_name)

    # Không đáng chia nhỏ: video ngắn hoặc worker=1 → caller tự dùng đường thường
    if duration_s < min_chunk_s * workers:
        raise ParallelExportError(
            f"Video quá ngắn ({duration_s:.0f}s) cho {workers} chunk — dùng đường 1 process")

    t0 = time.time()
    keyframes = probe_keyframes(video_path)
    bounds = plan_chunk_boundaries(keyframes, duration_s, workers, min_chunk_s)
    n_chunks = len(bounds) - 1
    if n_chunks < 2:
        raise ParallelExportError("Không chia được chunk hợp lệ từ keyframe")

    logger.info(
        f"[ParallelExport] {duration_s:.0f}s → {n_chunks} chunks × "
        f"{workers} workers (encoder: {encoder_name})")

    tmp_dir = tempfile.mkdtemp(prefix="autodub_pexport_")
    chunk_paths: List[str] = []
    cmds: List[List[str]] = []
    labels: List[str] = []
    try:
        fps_val = fps or probe_fps(video_path)
        total_frames = max(1.0, duration_s * fps_val)

        for i in range(n_chunks):
            start_s, end_s = bounds[i], bounds[i + 1]
            chunk_out = os.path.join(tmp_dir, f"chunk_{i:04d}.mp4")
            chunk_paths.append(chunk_out)
            cmds.append(build_chunk_cmd(video_path, start_s, end_s, chunk_out))
            labels.append(f"#{i + 1}/{n_chunks}")

        # ---- Render song song ----
        done_frames = 0.0
        lock = threading.Lock()

        def _update(chunk_dur: float, label: str) -> None:
            nonlocal done_frames
            with lock:
                done_frames += chunk_dur * fps_val
                if progress_cb is not None:
                    pct = min(0.98, done_frames / total_frames)
                    progress_cb(pct, f"Render song song {label}: {int(pct * 100)}%")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for cmd, label, (start_s, end_s) in zip(cmds, labels,
                                                    zip(bounds, bounds[1:])):
                if cancel_event is not None and cancel_event.is_set():
                    raise ParallelExportError("Đã hủy xuất video")
                chunk_dur = end_s - start_s
                futures[pool.submit(_run_chunk, cmd,
                                    max(300, int((chunk_dur * 8) + 120)),
                                    label)] = (label, chunk_dur)
            for fut in as_completed(futures):
                label, chunk_dur = futures[fut]
                if cancel_event is not None and cancel_event.is_set():
                    raise ParallelExportError("Đã hủy xuất video")
                fut.result()  # raise ParallelExportError nếu chunk fail
                _update(chunk_dur, label)

        # ---- Ghép bằng concat demuxer — zero re-encode ----
        concat_list = os.path.join(tmp_dir, "concat.txt")
        _write_concat_list(chunk_paths, concat_list)
        concat_out = os.path.join(tmp_dir, "concat_out.mp4")
        concat_cmd = [
            "ffmpeg", "-v", "error", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy", "-movflags", "+faststart", concat_out,
        ]
        _run_chunk(concat_cmd, max(300, int(duration_s * 2)), "concat")

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        import shutil
        shutil.move(concat_out, output_path)

        # randomize metadata TRÊN FILE CUỐI — cùng semantics đường 1 process
        if randomize_metadata_fn is not None:
            try:
                randomize_metadata_fn()
            except Exception:
                pass

        elapsed = time.time() - t0
        speed = duration_s / elapsed if elapsed > 0 else 0
        logger.info(
            f"[ParallelExport] Xong {duration_s:.0f}s video trong {elapsed:.1f}s "
            f"({speed:.1f}x realtime, {n_chunks} chunks)")
        return output_path
    finally:
        # Dọn tmp chunk
        import shutil
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
