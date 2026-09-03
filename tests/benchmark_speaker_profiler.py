import os
import time
import numpy as np
import pytest

from autodub.speech.speaker_profiler import profile_speakers


def test_benchmark_speaker_profiler_cpu_performance(tmp_path):
    """Benchmark: Đo hiệu năng phân tích F0 và Speaker Profile trên CPU thuần.

    Acceptance criteria:
    - Median time < 0.50s (500ms) cho 5 phút audio (300s).
    - P95 time < 0.75s (750ms).
    - CPU only (no GPU dependency).
    """
    sr = 16000
    duration_s = 300.0  # 5 phút audio
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # Audio tổng hợp 300s
    audio = 0.5 * np.sin(2 * np.pi * 140.0 * t).astype(np.float32)

    import wave
    audio_path = str(tmp_path / "bench_5min.wav")
    int16_audio = (audio * 32767).astype(np.int16)
    with wave.open(audio_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(int16_audio.tobytes())

    # 30 segments xen kẽ giữa 3 speaker
    segments = []
    seg_len = 10.0
    for i in range(30):
        segments.append({
            "id": i + 1,
            "speaker_id": i % 3,
            "start": round(i * seg_len, 2),
            "end": round((i + 1) * seg_len, 2),
            "text": f"Câu thoại thử nghiệm {i+1}",
        })

    # Warm-up 1 lần
    profile_speakers(audio_path, segments)

    # Đo 10 vòng lặp bằng time.perf_counter()
    iterations = 10
    timings = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        profile_speakers(audio_path, segments)
        t1 = time.perf_counter()
        timings.append(t1 - t0)

    median_time = float(np.median(timings))
    p95_time = float(np.percentile(timings, 95))

    print(f"\n[BENCHMARK] Speaker Profiler 5-min Audio CPU Time: Median = {median_time*1000:.1f}ms, P95 = {p95_time*1000:.1f}ms")

    # Kiểm tra ràng buộc
    assert median_time < 0.50, f"Expected median time < 500ms, got {median_time*1000:.1f}ms"
    assert p95_time < 0.75, f"Expected p95 time < 750ms, got {p95_time*1000:.1f}ms"
