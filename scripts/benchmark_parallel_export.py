"""Benchmark: Parallel Chunked Export vs 1-process encode.

Tạo video test dài (mặc định 240s @ 1080p30), chạy 2 đường và so sánh.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from autodub.media.video import video_codec_args, video_encoder_name
from autodub.media.parallel_export import parallel_chunked_export


def make_test_video(path: str, duration: int, size: str = "1280x720") -> None:
    if os.path.exists(path):
        return
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=size={size}:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000",
            "-t",
            str(duration),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "60",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            path,
        ],
        check=True,
    )


def main() -> None:
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 240
    tmp = BASE_DIR / ".artifacts" / "benchmarks" / "parallel_bench"
    tmp.mkdir(parents=True, exist_ok=True)
    src = str(tmp / f"src_{duration}s.mp4")
    audio = str(tmp / f"audio_{duration}s.wav")

    print(f"[*] Tạo video test {duration}s 1280x720@30 (keyframe mỗi 2s)...")
    make_test_video(src, duration)
    if not os.path.exists(audio):
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                str(duration),
                audio,
            ],
            check=True,
        )

    # filter graph mô phỏng burn phụ đề + reframe 9:16
    sub_file = str(tmp / "bench.ass")
    with open(sub_file, "w", encoding="utf-8-sig") as f:
        f.write(
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 512\nPlayResY: 288\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: S,Arial,22,&H00FFFFFF,&H00FFFFFF,&H00000000,&H66000000,-1,0,0,0,"
            "100,100,0,0,1,2,0,2,20,20,40,163\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
        )
        for i in range(0, duration, 4):
            f.write(
                f"Dialogue: 0,0:00:{i:02d}.00,0:00:{min(i + 4, duration):02d}.00,"
                f"S,,0,0,0,,Câu thử nghiệm số {i}\n"
            )

    escaped = sub_file.replace("\\", "/").replace(":", "\\:")
    # Filter graph mô phỏng: 9:16 blur reframe + 2 vùng che phụ đề + burn sub
    filter_complex = (
        "[0:v]split[asp_bg][asp_fg];"
        "[asp_bg]scale=120:213:force_original_aspect_ratio=increase,"
        "crop=120:213,boxblur=4:1,"
        "scale=720:1280:flags=bilinear,"
        "eq=brightness=-0.08:saturation=1.15[asp_bgb];"
        "[asp_fg]scale=720:1280:force_original_aspect_ratio=decrease[asp_fg_s];"
        "[asp_bgb][asp_fg_s]overlay=(W-w)/2:(H-h)/2[vasp];"
        "[vasp]split=3[bmain][br0] [br1];"
        "[br0]crop=720:100:0:1150,boxblur=8:2[bl0];"
        "[br1]crop=300:90:100:80,boxblur=6:2[bl1];"
        "[bmain][bl0]overlay=0:1150[vov0];"
        "[vov0][bl1]overlay=100:80[vov1];"
        f"[vov1]subtitles='{escaped}'[vout]"
    )

    codec_args = video_codec_args()
    print(f"[*] Encoder: {video_encoder_name()}")

    # ---- Đường 1: 1 process ----
    out_single = str(tmp / "out_single.mp4")
    cmd_single = [
        "ffmpeg",
        "-v",
        "error",
        "-hwaccel",
        "auto",
        "-threads",
        "0",
        "-i",
        src,
        "-i",
        audio,
        "-filter_complex",
        filter_complex,
        "-filter_complex_threads",
        "0",
        "-map",
        "[vout]",
        "-map",
        "1:a",
        *codec_args,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-y",
        out_single,
    ]
    print("\n[1/2] Encode 1 process...")
    t0 = time.perf_counter()
    subprocess.run(cmd_single, check=True)
    t_single = time.perf_counter() - t0

    # ---- Đường 2: parallel chunked ----
    out_parallel = str(tmp / "out_parallel.mp4")

    def build_chunk(src_p: str, start_s: float, end_s: float, chunk_out: str):
        return [
            "ffmpeg",
            "-v",
            "error",
            "-hwaccel",
            "auto",
            "-threads",
            "0",
            "-ss",
            f"{start_s:.3f}",
            "-to",
            f"{end_s:.3f}",
            "-i",
            src_p,
            "-i",
            audio,
            "-filter_complex",
            filter_complex,
            "-filter_complex_threads",
            "0",
            "-map",
            "[vout]",
            "-map",
            "1:a",
            *codec_args,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-y",
            chunk_out,
        ]

    print("\n[2/2] Encode song song theo chunk...")
    t0 = time.perf_counter()
    parallel_chunked_export(
        build_chunk, src, audio, out_parallel, duration_s=float(duration), fps=30.0
    )
    t_parallel = time.perf_counter() - t0

    speedup = t_single / t_parallel if t_parallel > 0 else 0
    size_s = os.path.getsize(out_single) / 1e6
    size_p = os.path.getsize(out_parallel) / 1e6
    print("\n" + "=" * 66)
    print(f" KẾT QUẢ BENCHMARK PARALLEL CHUNKED EXPORT ({duration}s video)")
    print(f" - 1 process : {t_single:7.1f}s  ({duration / t_single:5.1f}x realtime)")
    print(f" - Parallel  : {t_parallel:7.1f}s  ({duration / t_parallel:5.1f}x realtime)")
    print(f" - SPEEDUP   : {speedup:.2f}x")
    print(f" - Kích thước: single={size_s:.1f}MB parallel={size_p:.1f}MB")
    print("=" * 66)

    # dọn dẹp
    for p in (out_single, out_parallel, audio):
        try:
            os.remove(p)
        except OSError:
            pass


if __name__ == "__main__":
    main()
