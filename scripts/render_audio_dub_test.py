# -*- coding: utf-8 -*-
"""Render video test dubbing thực tế (AUDIO_DUB spec Phase 14).

Cắt cửa sổ 60s của video thật → ASR thật (Paraformer) lấy speech segments
→ "giọng VI" là tone đặt đúng speech_start (qua ĐÚNG merge_segments + duck
mới) → mux bằng merge_video. Đo: duck depth theo speech, onset VI, peak.

Chạy:  py scripts/render_audio_dub_test.py [video.mp4] [--start 20] [--dur 60]
Kết quả: output/audio_dub_test/dub_test.mp4 + measurements in stdout/JSON.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OUT_DIR = os.path.join(ROOT, "output", "audio_dub_test")


def _run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd[:3])}...\n{r.stderr[:300]}")
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", nargs="?",
                    default=os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                         "Temp", "voxdub_prefetch",
                                         "BV16f3K67EAk.mp4"))
    ap.add_argument("--start", type=float, default=20.0)
    ap.add_argument("--dur", type=float, default=60.0)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="dubtest_")
    src = os.path.join(OUT_DIR, "source_slice.mp4")
    _run(["ffmpeg", "-y", "-v", "error", "-ss", str(args.start),
          "-t", str(args.dur), "-i", args.video, "-c", "copy", src])

    # Audio cho ASR (16k) và cho mix (44.1k)
    wav16 = os.path.join(tmp, "asr.wav")
    wav44 = os.path.join(tmp, "mix.wav")
    _run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ar", "16000",
          "-ac", "1", "-acodec", "pcm_s16le", wav16])
    _run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ar", "44100",
          "-ac", "1", "-acodec", "pcm_s16le", wav44])

    # ASR thật: Paraformer worker lấy speech segments
    worker = os.path.join(ROOT, "autodub", "speech", "asr_paraformer_worker.py")
    venv_py = os.path.join(ROOT, ".venv-asr", "Scripts", "python.exe")
    r = subprocess.run([venv_py, worker, "--audio", wav16,
                        "--model-dir", os.path.join(ROOT, "models", "paraformer-zh"),
                        "--no-punct"], capture_output=True, text=True)
    segs = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            m = json.loads(line)
            if m.get("seg") and m["end"] - m["start"] >= 1.5:
                segs.append((m["start"], m["end"]))
    if len(segs) < 2:
        raise RuntimeError(f"ASR chỉ bắt được {len(segs)} đoạn — chọn cửa sổ khác")
    segs = segs[:10]
    print(f"Speech segments (ASR thật): {len(segs)} đoạn")
    for s, e in segs:
        print(f"   {s:6.2f} → {e:6.2f}")

    # "Giọng VI": tone 1kHz dài 1.0s đặt đúng speech_start (đường đi thật)
    from autodub.config import Settings
    from autodub.media.audio import merge_segments
    settings = Settings.load()
    seg_dir = os.path.join(tmp, "segs")
    os.makedirs(seg_dir)
    rate = 44100
    t = np.arange(int(1.0 * rate)) / rate
    tone = (0.5 * np.sin(2 * np.pi * 1000 * t) * 32767).astype(np.int16)
    mix_segs = []
    for i, (s, e) in enumerate(segs, start=1):
        p = os.path.join(seg_dir, f"seg_{i:03d}.wav")
        with wave.open(p, "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
            w.writeframes(tone.tobytes())
        mix_segs.append({"id": i, "start": round(s, 3), "end": round(s + 1.0, 3),
                         "duration": 1.0, "speech_start": round(s, 3),
                         "speech_end": round(e, 3)})

    dur = args.dur
    mixed = os.path.join(OUT_DIR, "dub_test.wav")
    dip = min(0.0, settings.original_voice_duck_db - 0.0)  # nền tĩnh 0dB
    merge_segments(mix_segs, seg_dir, mixed, dur,
                   background_path=wav44, background_gain_db=0.0,
                   speech_intervals=segs, speech_duck_db=dip,
                   duck_attack_s=settings.duck_attack_ms / 1000.0,
                   duck_release_s=settings.duck_release_ms / 1000.0)

    # Mux bằng merge_video (đường thật, không sub/blur/speed)
    from autodub.media.video import merge_video
    out_mp4 = os.path.join(OUT_DIR, "dub_test.mp4")
    merge_video(src, mixed, out_mp4)

    # ---- Đo lường ----------------------------------------------------- #
    # Đ duck CHÍNH XÁC: so cùng cửa sổ giữa bản GỐC chưa duck (wav44) và
    # bản mix — cùng nội dung, khác đúng gain duck. (So với vùng im lặng
    # sẽ sai: tiếng TQ đã duck vẫn nằm ở dải thoại.)
    with wave.open(wav44) as w:
        orate = w.getframerate()
        ox = np.frombuffer(w.readframes(w.getnframes()),
                           dtype=np.int16).astype(np.float32) / 32768
    with wave.open(mixed) as w:
        mr = w.getframerate()
        x = np.frombuffer(w.readframes(w.getnframes()),
                          dtype=np.int16).astype(np.float32) / 32768
    assert orate == mr

    def rms(arr, r, t0, t1):
        return float(np.sqrt((arr[int(t0 * r):int(t1 * r)] ** 2).mean()))

    dips = []
    for s, e in segs:
        t0, t1 = s + 1.25, min(e - 0.05, s + 2.5)   # trong speech, tone dứt
        if t1 - t0 >= 0.3:
            dips.append(20 * np.log10(rms(ox, orate, t0, t1)
                                      / rms(x, mr, t0, t1)))

    # onset tone 1kHz quanh speech_start
    onset_errs = []
    for s, e in segs:
        a, b = int((s - 0.2) * mr), int((s + 0.4) * mr)
        win = x[a:b]
        hop = int(0.01 * mr)
        n = len(win) // hop
        rms_w = np.sqrt((win[:n * hop].reshape(n, hop) ** 2).mean(axis=1))
        k = int(0.2 / 0.01)
        above = np.nonzero(rms_w[k:] > 0.25)[0]
        if len(above):
            onset_errs.append(above[0] * 0.01)

    vd = _run(["ffmpeg", "-i", mixed, "-af", "volumedetect", "-f", "null", "-"])
    peak = next((l for l in vd.stderr.splitlines() if "max_volume" in l), "?")
    probe = _run(["ffprobe", "-v", "error", "-show_entries",
                  "stream=codec_type,duration", "-of", "json", out_mp4])
    n_audio = probe.stdout.count('"audio"')

    report = {
        "speech_segments": len(segs),
        "duck_depth_db_measured": round(float(np.mean(dips)), 1) if dips else None,
        "target_total_db": settings.original_voice_duck_db,
        "vn_onset_err_ms": round(float(np.median(onset_errs)) * 1000, 0) if onset_errs else None,
        "audio_streams_in_mp4": n_audio,
        "video_speed": 1.0,
        "peak_line": peak.split("] ")[-1] if peak != "?" else "?",
        "output": out_mp4,
    }
    print("\n=== MEASUREMENTS ===")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
