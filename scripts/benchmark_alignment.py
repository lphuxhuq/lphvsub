"""Script benchmark hiệu năng và đo lường thời gian canh phụ đề (Alignment Profiling).

Chạy đo:
- Dataset 10 câu (short <= 0.6s)
- Dataset 50 câu (normal 0.6 - 3s)
- Dataset 100 câu (hỗn hợp short/normal/long)
Lưu kết quả vào .artifacts/benchmarks/baseline_metrics.json.
"""
import json
import os
import shutil
import sys
import time
from pathlib import Path

# Thêm thư mục gốc dự án vào sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from autodub.speech.align import AlignmentStats, align_segments
from tests.test_align_benchmark import generate_benchmark_dataset


def run_benchmark_suite():
    out_dir = BASE_DIR / ".artifacts" / "benchmarks"
    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / "temp_bench"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    test_counts = [10, 50, 100]

    print("=" * 70)
    print(" BẮT ĐẦU CHẠY BENCHMARK INSTRUMENTATION & BASELINE")
    print("=" * 70)

    for count in test_counts:
        print(f"\n[Dataset {count} câu]")
        segments, wav_dir = generate_benchmark_dataset(temp_dir, count=count)
        cache_path = str(temp_dir / f"cache_{count}.json")

        # 1. Cold run (chưa có cache)
        stats_cold = AlignmentStats()
        t0 = time.perf_counter()
        out_cold = align_segments(segments, str(wav_dir), "text_vi",
                                  cache_path=cache_path, stats=stats_cold)
        dur_cold = time.perf_counter() - t0

        # 2. Warm run (đã có cache)
        stats_warm = AlignmentStats()
        t0 = time.perf_counter()
        out_warm = align_segments(segments, str(wav_dir), "text_vi",
                                  cache_path=cache_path, stats=stats_warm)
        dur_warm = time.perf_counter() - t0

        speedup_cache = (dur_cold / dur_warm) if dur_warm > 0 else 0.0

        results[f"dataset_{count}"] = {
            "total_segments": count,
            "cold_run": stats_cold.to_dict(),
            "warm_run": stats_warm.to_dict(),
            "cache_speedup": round(speedup_cache, 2),
        }

        print(f"  - Cold run: {dur_cold:.3f}s ({stats_cold.segments_per_sec:.1f} câu/s)")
        print(f"  - Warm run: {dur_warm:.3f}s ({stats_warm.segments_per_sec:.1f} câu/s)")
        print(f"  - Tăng tốc nhờ Cache: {speedup_cache:.1f}x")

    # Lưu kết quả baseline
    baseline_file = out_dir / "baseline_metrics.json"
    with open(baseline_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print(f" ĐÃ GHI KẾT QUẢ BASELINE VÀO: {baseline_file}")
    print("=" * 70)

    # Dọn dẹp
    shutil.rmtree(temp_dir, ignore_errors=True)
    return results


if __name__ == "__main__":
    run_benchmark_suite()
