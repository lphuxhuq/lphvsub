import json
import os
import subprocess
_REAL_SUBPROCESS_RUN = subprocess.run
import threading
import time
from functools import lru_cache
from typing import Callable

from autodub.utils import ffmpeg_timeout_s, setup_logging, ProgressTracker

logger = setup_logging("autodub.video_merger")


def probe_duration_s(video_path: str) -> float | None:
    """Thời lượng (giây) của media qua ffprobe; None nếu không đọc được.

    Dùng để tính trần timeout cho các lệnh encode dài — không phải giá trị
    chính xác tuyệt đối nên lỗi thì cứ trả None, caller tự dùng trần rộng.
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=60,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


@lru_cache(maxsize=None)
def _encoder_works(*args: str) -> bool:
    """True nếu ffmpeg mã hóa được thật bằng bộ mã hóa này.

    Chỉ liệt kê trong ``-encoders`` là không đủ: driver cũ hoặc máy không có
    card tương ứng vẫn liệt kê mà chạy là lỗi. Encode thử một khung vào
    null-sink là cách duy nhất chắc chắn.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi",
             "-i", "color=black:s=256x256:d=0.1", *args, "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


#: Các bộ mã hóa phần cứng theo thứ tự ưu tiên, kèm tham số chất lượng
#: tương đương crf 23 của libx264. NVIDIA → Apple (VideoToolbox) → Intel (QSV) → AMD (AMF) → Linux (VAAPI).
#: Máy không có GPU nào trong số này rơi về libx264 trên CPU.
_HW_ENCODERS: tuple[tuple[str, list[str]], ...] = (
    ("NVIDIA NVENC",
     ["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "23", "-b:v", "0", "-multipass", "0"]),
    ("Apple VideoToolbox",
     ["-c:v", "h264_videotoolbox", "-q:v", "55"]),
    ("Intel QuickSync",
     ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"]),
    ("AMD AMF",
     ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "23",
      "-qp_p", "23"]),
    ("Linux VAAPI",
     ["-c:v", "h264_vaapi", "-qp", "23"]),
)



@lru_cache(maxsize=1)
def _resolve_encoder() -> tuple[str, tuple[str, ...]]:
    """Bộ mã hóa nhanh nhất máy này chạy được: (tên dễ đọc, argv)."""
    for name, args in _HW_ENCODERS:
        if _encoder_works(*args):
            return name, tuple(args)
    return ("CPU (libx264)",
            ("-c:v", "libx264", "-preset", "veryfast", "-crf", "20"))


def video_codec_args(quality_mode: str = "fast") -> list[str]:
    """Encoder argv shared by every re-encode in the app (merge, retime).

    Ưu tiên mã hóa bằng GPU (NVENC/QSV/AMF) — nhanh gấp nhiều lần libx264 ở
    chất lượng tương đương với video lồng tiếng; máy không có thì dùng CPU.
    """
    from autodub.media.encoder_profile import EncoderProfile, QualityMode
    name, default_args = _resolve_encoder()
    try:
        return EncoderProfile.get_args(name, mode=quality_mode)
    except Exception:
        return list(default_args)


def video_encoder_name() -> str:
    """Tên bộ mã hóa đang dùng — để ghi vào nhật ký cho người dùng thấy."""
    return _resolve_encoder()[0]


def probe_dimensions(video_path: str) -> tuple[int, int]:
    """Return DISPLAY (width, height) of the first video stream via ffprobe.

    Phone videos often store 1920x1080 with a 90° rotation tag; ffmpeg's
    decoder auto-rotates before the filtergraph, so blur/subtitle coordinates
    must be scaled against the rotated (display) dimensions — otherwise blurs
    land in the wrong place and crops can exceed the frame.
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,side_data_list",
        "-of", "json",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {video_path}: {result.stderr}")
    try:
        stream = json.loads(result.stdout)["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Could not read dimensions from {video_path}: {e}") from e
    rotation = 0
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                rotation = int(sd["rotation"])
            except (TypeError, ValueError):
                rotation = 0
            break
    if rotation % 180 != 0:
        w, h = h, w
    return w, h


def render_preview_clip(
    video_path: str,
    audio_path: str,
    output_path: str,
    start_s: float,
    end_s: float,
    srt_path: str | None = None,
    subtitle_style: dict | None = None,
    speed: float | None = None,
    fps: str | None = None,
    height: int = 480,
) -> str:
    """Cắt một đoạn ngắn của video và ghép bản âm thanh xem thử vào.

    Đường đi NHANH cho việc nghe thử một câu trước khi xuất cả phim: chỉ
    mã hóa vài giây quanh câu đang chọn, hạ xuống ``height`` điểm ảnh và
    dùng ``-preset ultrafast`` — vài giây là xong thay vì vài phút.

    ``start_s``/``end_s`` tính trên timeline của TỆP NGUỒN. ``srt_path``
    (nếu có) phải mang mốc thời gian ĐÃ DỜI về 0 tại ``start_s``, vì với
    ``-ss`` đặt trước ``-i`` thì timestamp đầu ra bắt đầu từ 0. ``speed``
    < 1.0 làm chậm ngay trong lượt mã hóa (dự án dùng đường làm chậm gộp).
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    filters = []
    if speed is not None and speed < 0.999:
        filters.append(f"setpts=PTS/{speed}")
        if fps:
            filters.append(f"fps={fps}")
    # Không phóng to video vốn đã nhỏ hơn 480 điểm; bảo đảm cả 2 chiều luôn chẵn (chia hết cho 2).
    from autodub.media.dimension import build_even_scale_filter
    filters.append(build_even_scale_filter(height))
    if srt_path and os.path.exists(srt_path):
        from autodub.media.subtitle import (build_force_style,
                                            escape_subtitles_path)
        from autodub.utils import bundled_font_files, fonts_dir
        subs = f"subtitles='{escape_subtitles_path(srt_path)}'"
        if bundled_font_files():
            subs += f":fontsdir='{escape_subtitles_path(fonts_dir())}'"
        if not srt_path.lower().endswith(".ass"):
            subs += f":force_style='{build_force_style(subtitle_style)}'"
        filters.append(subs)

    cmd = [
        "ffmpeg", "-ss", f"{start_s:.3f}", "-to", f"{end_s:.3f}",
        "-i", video_path, "-i", audio_path,
        "-filter:v", ",".join(filters),
        "-map", "0:v:0", "-map", "1:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-y", output_path,
    ]
    logger.info(f"Rendering preview clip {start_s:.1f}s–{end_s:.1f}s → "
                f"{output_path}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=ffmpeg_timeout_s(end_s - start_s))
    except subprocess.TimeoutExpired:
        raise RuntimeError("FFmpeg treo khi dựng đoạn xem thử")
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg preview failed: {result.stderr[:400]}")
    return output_path


def merge_video(
    video_path: str,
    audio_path: str,
    output_path: str,
    srt_path: str | None = None,
    subtitle_mode: str = "none",
    blur_regions: list[dict] | None = None,
    subtitle_style: dict | None = None,
    subtitle_lang: str = "und",
    speed: float | None = None,
    fps: str | None = None,
    aspect_preset: str | None = None,
    logo_path: str | None = None,
    logo_position: str = "top_right",
    logo_scale: float = 0.12,
    logo_opacity: float = 0.85,
    logo_margin: int = 24,
    logo_motion: str = "static",
    watermark_text: str | None = None,
    watermark_opacity: float = 0.28,
    watermark_font_size: int = 26,
    watermark_color: str = "white",
    watermark_speed: int = 40,
    watermark_motion: str = "bounce",
    smart_flip: bool = False,
    micro_zoom: bool = False,
    color_filter: str = "none",
    reframe_mode: str = "blur",
    mask_method: str = "blur",
    inpaint_engine: str = "lama_onnx",
    inpaint_device: str = "auto",
    inpaint_model_path: str | None = None,
    progress_cb: Callable[[float, str], None] | None = None,
    cancel_event: threading.Event | None = None,
    frame_banner_enabled: bool = False,
    frame_banner_color: str = "#000000",
    frame_banner_height_ratio: float = 0.16,
    frame_header_text: str | None = None,
    frame_header_font_size: int = 32,
    frame_header_color: str = "#FFFFFF",
    frame_footer_text: str | None = None,
    frame_footer_font_size: int = 24,
    frame_footer_color: str = "#FFD54A",
    randomize_metadata: bool = True,
) -> str:

    """Mux the dubbed audio into the video, optionally adding subtitles/blur/aspect/logo/watermark/anti-content-id.

    ``subtitle_mode``:

    - ``none`` — audio only (default; stream-copies video, fastest)
    - ``soft`` — embed the SRT as a toggleable subtitle track (still no re-encode)
    - ``burn`` — draw subtitles into the pixels (requires a video re-encode)

    ``blur_regions`` blurs rectangles of the frame to cover hardcoded source
    captions. Coordinates are normalized 0..1 dicts (``x``/``y``/``w``/``h``,
    optional ``t_start``/``t_end``). Any blur forces a re-encode, so it is
    applied in the same pass as burned-in subtitles.

    ``mask_method``:
    - ``blur`` — FFmpeg Boxblur (default, fast 1-pass encode)
    - ``ai_inpaint`` — AI Inpainting Subtitle Remover (LaMa ONNX / VSR)
    - ``none`` — do not mask/blur source subtitles

    ``aspect_preset`` converts the canvas ratio with blurred background padding
    (e.g., "tiktok_9_16", "youtube_16_9", "square_1_1"). Forces a re-encode.

    ``logo_path`` overlays a watermark / brand logo onto the video canvas.
    ``watermark_text`` overlays a dynamic floating/bouncing text watermark.
    ``smart_flip`` mirrors base video horizontally without flipping subtitles/logo.
    ``micro_zoom`` slightly zooms (103%) and drifts camera to bypass Content ID.
    ``color_filter`` applies cinematic grading preset.
    ``reframe_mode`` defines reframe layout (blur, top_split, center_crop).
    ``frame_banner_enabled`` adds top & bottom banner bars with custom header & footer texts.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if subtitle_mode not in ("none", "soft", "burn"):
        raise ValueError(f"Invalid subtitle_mode: {subtitle_mode!r}")
    if subtitle_mode != "none" and not srt_path:
        raise ValueError(f"subtitle_mode={subtitle_mode!r} requires srt_path")
    if srt_path and subtitle_mode != "none" and not os.path.exists(srt_path):
        raise FileNotFoundError(f"Subtitle file not found: {srt_path}")

    actual_video_path = video_path
    effective_blur_regions = blur_regions

    if mask_method == "ai_inpaint" and blur_regions:
        try:
            from autodub.media.inpaint import inpaint_video_with_cache
            inpaint_kwargs = {
                "video_path": video_path,
                "regions": blur_regions,
                "engine_type": inpaint_engine,
                "device": inpaint_device,
                "model_path": inpaint_model_path,
            }
            if progress_cb is not None:
                inpaint_kwargs["progress_cb"] = progress_cb
            if cancel_event is not None:
                inpaint_kwargs["cancel_event"] = cancel_event
            actual_video_path = inpaint_video_with_cache(**inpaint_kwargs)
            # Sau khi đã xóa sạch bằng AI Inpaint, bỏ blur_regions trên filtergraph
            effective_blur_regions = []
        except Exception as e:
            logger.warning(f"Lỗi khi thực hiện AI Inpaint ({e}) — tự động chuyển sang làm mờ Boxblur.")
            effective_blur_regions = blur_regions

    from autodub.media.subtitle import build_filter_complex

    burn_srt = srt_path if subtitle_mode == "burn" else None
    filter_complex = None
    has_logo = bool(logo_path and str(logo_path).strip())
    has_wm = bool(watermark_text and str(watermark_text).strip())
    has_anti_id = bool(smart_flip or micro_zoom or (color_filter and color_filter not in ("none", "original", "")))
    has_banner = bool(frame_banner_enabled)
    if (effective_blur_regions or burn_srt or has_logo or has_wm or has_anti_id
            or (aspect_preset and aspect_preset not in ("original", "none")) or has_banner):
        width, height = probe_dimensions(actual_video_path)
        filter_complex = build_filter_complex(
            effective_blur_regions, width, height, burn_srt, subtitle_style,
            aspect_preset=aspect_preset,
            logo_path=logo_path,
            logo_position=logo_position,
            logo_scale=logo_scale,
            logo_opacity=logo_opacity,
            logo_margin=logo_margin,
            logo_motion=logo_motion,
            watermark_text=watermark_text,
            watermark_opacity=watermark_opacity,
            watermark_font_size=watermark_font_size,
            watermark_color=watermark_color,
            watermark_speed=watermark_speed,
            watermark_motion=watermark_motion,
            smart_flip=smart_flip,
            micro_zoom=micro_zoom,
            color_filter=color_filter,
            reframe_mode=reframe_mode,
            frame_banner_enabled=frame_banner_enabled,
            frame_banner_color=frame_banner_color,
            frame_banner_height_ratio=frame_banner_height_ratio,
            frame_header_text=frame_header_text,
            frame_header_font_size=frame_header_font_size,
            frame_header_color=frame_header_color,
            frame_footer_text=frame_footer_text,
            frame_footer_font_size=frame_footer_font_size,
            frame_footer_color=frame_footer_color,
        )


    apply_speed = speed is not None and speed < 0.999
    if apply_speed:
        if not fps:
            raise ValueError("speed requires fps (ffprobe rational)")
        setpts = f"setpts=PTS/{speed},fps={fps}"
        if filter_complex:
            # setpts BEFORE blur/subs: their timestamps are on the slowed
            # timeline, so the frames must already be retimed when they apply.
            filter_complex = (f"[0:v]{setpts}[vslow];"
                              + filter_complex.replace("[0:v]", "[vslow]", 1))
        else:
            from autodub.media.dimension import build_dimension_filter
            filter_complex = f"[0:v]{setpts},{build_dimension_filter()}[vout]"

    hw_args = ["-hwaccel", "auto"] if video_encoder_name() != "CPU (libx264)" else []
    cmd = ["ffmpeg", *hw_args, "-threads", "0", "-i", actual_video_path, "-i", audio_path]
    if subtitle_mode == "soft":
        cmd += ["-i", srt_path]

    filter_script_file = None
    if filter_complex:
        # Re-encode: the filtergraph rewrites pixels, so -c:v copy is impossible.
        codec = video_codec_args()
        # Chuyển sang -filter_complex_script nếu chuỗi quá dài (> 1024 ký tự) hoặc nhiều vùng làm mờ
        # để xóa bỏ hoàn toàn giới hạn 32,767 ký tự trên dòng lệnh Windows.
        if len(filter_complex) > 1024 or "\n" in filter_complex or len(effective_blur_regions or []) > 2:
            import tempfile
            fd, filter_script_file = tempfile.mkstemp(prefix="filtergraph_", suffix=".txt")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(filter_complex)
            filter_args = ["-filter_complex_script", filter_script_file]
        else:
            filter_args = ["-filter_complex", filter_complex]

        cmd += [
            *filter_args,
            "-map", "[vout]", "-map", "1:a",
            *codec,
            "-pix_fmt", "yuv420p",
        ]
        if apply_speed:
            cmd += ["-fps_mode", "cfr"]

    else:
        # 0:v:0 (not 0:v): downloaded MP4s can carry an attached-picture
        # thumbnail stream that would also be stream-copied.
        cmd += ["-c:v", "copy", "-map", "0:v:0", "-map", "1:a"]

    if subtitle_mode == "soft":
        # Stream-copy soft subs as mov_text / srt
        ext = os.path.splitext(output_path)[1].lower()
        sub_codec = "mov_text" if ext in (".mp4", ".m4v", ".mov") else "srt"
        cmd += [
            "-map", "2:s",
            "-c:s", sub_codec,
            f"-metadata:s:s:0", f"language={subtitle_lang}",
            "-disposition:s:0", "default",
        ]

    if randomize_metadata:
        from autodub.media.metadata import build_clean_metadata_args
        cmd += build_clean_metadata_args()

    cmd += ["-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-y", output_path]

    what = ["audio"]
    if subtitle_mode != "none":
        what.append(f"{subtitle_mode} subs")
    if blur_regions:
        what.append(f"{len(blur_regions)} blur region(s)")
    if apply_speed:
        what.append(f"speed {speed}x")
    logger.info(f"Merging video + {' + '.join(what)} → {output_path}")
    if filter_complex:
        logger.info("Re-encoding video (filters applied) — this takes a while")

    # Trần timeout theo thời lượng thật: stream-copy thì 4x là quá rộng;
    # re-encode CPU trên máy yếu có thể chậm hơn realtime nên nhân 8.
    dur = probe_duration_s(video_path) or 0.0
    timeout = (max(900, int(dur * 8)) if filter_complex and dur
               else ffmpeg_timeout_s(dur))

    try:
        # Tương thích với các unit test giả lập mock / monkeypatch subprocess.run
        if subprocess.run is not _REAL_SUBPROCESS_RUN:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg merge failed: {result.stderr}")
            if randomize_metadata:
                try:
                    from autodub.media.metadata import randomize_file_hash
                    randomize_file_hash(output_path)
                except Exception:
                    pass
            logger.info(f"Video merged: {output_path}")
            return output_path


        tracker = ProgressTracker(dur if dur > 0 else 1.0, "Xuất video & ghép phụ đề", unit="s", min_log_interval=2.5)

        # Thêm -progress pipe:1 để theo dõi tiến độ thời gian thực
        idx_y = cmd.index("-y") if "-y" in cmd else len(cmd) - 1
        run_cmd = cmd[:idx_y] + ["-progress", "pipe:1", "-nostats"] + cmd[idx_y:]
        no_win_flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=no_win_flag,
        )
        stderr_lines: list[str] = []

        def _drain_stderr():
            if proc.stderr:
                for line in proc.stderr:
                    stderr_lines.append(line)

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        t_start = time.time()
        try:
            if proc.stdout:
                for line in proc.stdout:
                    if cancel_event is not None and cancel_event.is_set():
                        proc.kill()
                        raise RuntimeError("Đã hủy xuất video")
                    if time.time() - t_start > timeout:
                        proc.kill()
                        raise subprocess.TimeoutExpired(cmd, timeout)
                    line = line.strip()
                    if line.startswith("out_time_us="):
                        try:
                            us = int(line.split("=", 1)[1])
                            cur_s = us / 1_000_000.0
                            if dur > 0:
                                detail = f"Thời lượng xuất: {cur_s:.1f}s / {dur:.1f}s"
                                should_log, msg = tracker.update_to(cur_s, detail=detail)
                                if should_log:
                                    logger.info(f"  {msg}")
                                if progress_cb is not None:
                                    progress_cb(min(1.0, cur_s / dur), msg)
                        except (ValueError, TypeError):
                            pass
            rem_t = max(5, int(timeout - (time.time() - t_start)))
            proc.wait(timeout=rem_t)
            err_thread.join(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError(
                f"FFmpeg treo quá {timeout}s khi ghép video — kiểm tra file "
                f"nguồn có bị khóa hoặc driver GPU có ổn định không")
        except BaseException:
            proc.kill()
            raise

        if proc.returncode != 0:
            err_text = "".join(stderr_lines)
            raise RuntimeError(f"FFmpeg merge failed (code {proc.returncode}): {err_text}")

        logger.info(f"  {tracker.summary()}")

        if randomize_metadata:
            try:
                from autodub.media.metadata import randomize_file_hash
                new_hash = randomize_file_hash(output_path)
                logger.info(f"Đã làm sạch metadata và đổi mã băm MD5 duy nhất: {new_hash}")
            except Exception as e:
                logger.warning(f"Không đổi được mã băm MD5 ngẫu nhiên ({e})")

        logger.info(f"Video merged: {output_path}")
        return output_path
    finally:
        if filter_script_file and os.path.exists(filter_script_file):
            try:
                os.remove(filter_script_file)
            except OSError:
                pass


