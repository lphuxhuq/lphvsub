"""Script benchmark đo lường trực tiếp tốc độ render và burn phụ đề FFmpeg."""
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

from autodub.media.video import video_encoder_name, video_codec_args
from autodub.media.blur_strategy import BlurStrategy, BlurMode
from autodub.media.render_plan import RenderPlan


def run_benchmark():
    print("=" * 70)
    print(" BẮT ĐẦU BENCHMARK TỐC ĐỘ RENDER SUBTITLES & REFRAME BLUR")
    print("=" * 70)

    # 1. Thông tin phần cứng
    encoder_name = video_encoder_name()
    codec_args = video_codec_args("fast")
    print(f"[*] Encoder phát hiện: {encoder_name}")
    print(f"[*] Codec args       : {' '.join(codec_args)}")

    # 2. Tạo input giả lập 1080p 15s để đo tốc độ filtergraph thuần túy
    tmp_dir = BASE_DIR / ".artifacts" / "benchmarks" / "export_bench"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    input_video = str(tmp_dir / "bench_in.mp4")
    input_audio = str(tmp_dir / "bench_in.wav")
    sub_file = str(tmp_dir / "bench_sub.ass")

    print("\n[*] Chuẩn bị dữ liệu mẫu benchmark 15s (1080p @ 30fps)...")
    # Tạo video test 15s bằng lavfi color
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30",
        "-t", "15", "-c:v", "libx264", "-preset", "ultrafast", input_video
    ], check=True)

    # Tạo audio test 15s
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=24000",
        "-t", "15", input_audio
    ], check=True)

    # Tạo file phụ đề ASS mẫu
    ass_content = """[Script Info]
ScriptType: v4.00+
PlayResX: 512
PlayResY: 288

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kara,Arial,22,&H00FFFFFF,&H004AD5FF,&H00000000,&H66000000,-1,0,0,0,100,100,0,0,1,2,0,2,20,20,40,163

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    for i in range(15):
        s = f"0:00:{i:02d}.00"
        e = f"0:00:{i+1:02d}.00"
        ass_content += f"Dialogue: 0,{s},{e},Kara,,0,0,0,,{{\\fad(60,40)\\fscx82\\fscy82\\t(0,110,\\fscx100\\fscy100)}}Thử nghiệm hiệu năng cụm {i+1}\\N\n"

    with open(sub_file, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)

    escaped_sub = sub_file.replace("\\", "/").replace(":", "\\:")

    # 3. Kịch bản A: Baseline (Full-res boxblur không có downscale pyramid, không có -filter_complex_threads)
    out_baseline = str(tmp_dir / "bench_out_baseline.mp4")
    filter_baseline = (
        f"[0:v]split[asp_bg][asp_fg];"
        f"[asp_bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=10:2,eq=brightness=-0.08:saturation=1.15[asp_bgb];"
        f"[asp_fg]scale=1080:1920:force_original_aspect_ratio=decrease[asp_fg_s];"
        f"[asp_bgb][asp_fg_s]overlay=(W-w)/2:(H-h)/2[vasp];"
        f"[vasp]subtitles='{escaped_sub}'[vout]"
    )
    cmd_baseline = [
        "ffmpeg", "-v", "error", "-y",
        "-i", input_video, "-i", input_audio,
        "-filter_complex", filter_baseline,
        "-map", "[vout]", "-map", "1:a",
        *codec_args,
        "-pix_fmt", "yuv420p",
        out_baseline
    ]

    print("\n[1/2] Đang chạy kịch bản BASELINE (Full-Res Boxblur 1080x1920)...")
    t0 = time.perf_counter()
    subprocess.run(cmd_baseline, check=True)
    dur_baseline = time.perf_counter() - t0
    fps_baseline = 450.0 / dur_baseline  # 15s * 30fps = 450 frames
    print(f"  -> Hoàn thành trong: {dur_baseline:.2f}s | Tốc độ: {fps_baseline:.1f} FPS ({fps_baseline/30:.2f}x realtime)")

    # 4. Kịch bản B: Optimized (Downscale Blur Pyramid + -filter_complex_threads 0)
    out_opt = str(tmp_dir / "bench_out_opt.mp4")
    plan = RenderPlan.build(video_w=1920, video_h=1080, aspect_preset="tiktok_9_16", reframe_mode="blur", blur_mode=BlurMode.FAST)
    flt_reframe, _, _ = plan.build_reframe_filter()
    filter_opt = f"[0:v]{flt_reframe}[vasp];[vasp]subtitles='{escaped_sub}'[vout]"

    cmd_opt = [
        "ffmpeg", "-v", "error", "-y",
        "-i", input_video, "-i", input_audio,
        "-filter_complex", filter_opt,
        "-filter_complex_threads", "0",
        "-map", "[vout]", "-map", "1:a",
        *codec_args,
        "-pix_fmt", "yuv420p",
        out_opt
    ]

    print("\n[2/2] Đang chạy kịch bản OPTIMIZED (Downscale Blur Pyramid 180x320 + Multi-threading)...")
    t0 = time.perf_counter()
    subprocess.run(cmd_opt, check=True)
    dur_opt = time.perf_counter() - t0
    fps_opt = 450.0 / dur_opt
    print(f"  -> Hoàn thành trong: {dur_opt:.2f}s | Tốc độ: {fps_opt:.1f} FPS ({fps_opt/30:.2f}x realtime)")

    # 5. Báo cáo Tăng Tốc
    speedup = dur_baseline / dur_opt if dur_opt > 0 else 1.0
    print("\n" + "=" * 70)
    print(f" KẾT QUẢ TĂNG TỐC ĐỘ RENDER XUẤT VIDEO: {speedup:.2f}X NHANH HƠN")
    print(f" - Baseline:  {dur_baseline:.2f}s ({fps_baseline:.1f} FPS)")
    print(f" - Optimized: {dur_opt:.2f}s ({fps_opt:.1f} FPS)")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
