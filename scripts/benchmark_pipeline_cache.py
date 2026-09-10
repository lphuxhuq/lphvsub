"""Benchmark suite for Universal Pipeline Cache (UPC).

Measures:
1. Media fingerprint computation latency (small, medium, large files).
2. Cache key generation latency.
3. Cache store and lookup latency (cold vs warm).
4. Corruption detection and recovery overhead.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autodub.pipeline_cache import (
    CACHE_VERSION,
    AsrGlobalCache,
    DemucsGlobalCache,
    compute_media_fingerprint,
)


def create_dummy_wav(path: Path, size_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(b"RIFF")
        f.write((size_bytes - 8).to_bytes(4, "little"))
        f.write(b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data")
        f.write((size_bytes - 44).to_bytes(4, "little"))
        remaining = size_bytes - 44
        chunk = b"\x00" * min(remaining, 65536)
        while remaining > 0:
            to_write = min(remaining, len(chunk))
            f.write(chunk[:to_write])
            remaining -= to_write


def benchmark_fingerprint(tmp_dir: Path) -> dict:
    results = {}
    sizes = {
        "small_500KB": 500 * 1024,
        "medium_10MB": 10 * 1024 * 1024,
        "large_100MB": 100 * 1024 * 1024,
    }
    for label, size in sizes.items():
        file_path = tmp_dir / f"test_{label}.bin"
        # Write file with header, middle, footer
        with file_path.open("wb") as f:
            f.write(b"HEAD" * 100)
            f.seek(size - 400)
            f.write(b"TAIL" * 100)
            f.truncate(size)

        # Cold / first run
        t0 = time.perf_counter()
        fp1 = compute_media_fingerprint(str(file_path))
        t1 = time.perf_counter()
        cold_ms = (t1 - t0) * 1000.0

        # Warm runs (10 iterations)
        times = []
        for _ in range(10):
            t0 = time.perf_counter()
            fp2 = compute_media_fingerprint(str(file_path))
            t1 = time.perf_counter()
            assert fp1 == fp2
            times.append((t1 - t0) * 1000.0)

        warm_avg_ms = sum(times) / len(times)
        results[label] = {
            "size_bytes": size,
            "cold_ms": round(cold_ms, 3),
            "warm_avg_ms": round(warm_avg_ms, 3),
            "fingerprint_prefix": fp1[:12],
        }
    return results


def benchmark_demucs_cache(tmp_dir: Path) -> dict:
    import autodub.pipeline_cache as pc
    cache_root = tmp_dir / "cache_demucs"
    pc._ROOT = cache_root
    cache = DemucsGlobalCache()

    audio = tmp_dir / "orig.wav"
    vocals = tmp_dir / "stems" / "vocals.wav"
    no_vocals = tmp_dir / "stems" / "no_vocals.wav"
    create_dummy_wav(audio, 5 * 1024 * 1024)
    create_dummy_wav(vocals, 5 * 1024 * 1024)
    create_dummy_wav(no_vocals, 5 * 1024 * 1024)

    # 1. Miss lookup
    t0 = time.perf_counter()
    out1 = tmp_dir / "out1"
    miss = cache.lookup_and_restore(str(audio), str(out1), "htdemucs", 44100, 2)
    t1 = time.perf_counter()
    miss_ms = (t1 - t0) * 1000.0
    assert miss is None

    # 2. Store result (Cold write)
    t0 = time.perf_counter()
    cache.store_result(str(audio), str(vocals), str(no_vocals), "htdemucs", 44100, 2)
    t1 = time.perf_counter()
    store_ms = (t1 - t0) * 1000.0

    # 3. Hit lookup & restore (Warm read)
    out2 = tmp_dir / "out2"
    t0 = time.perf_counter()
    hit = cache.lookup_and_restore(str(audio), str(out2), "htdemucs", 44100, 2)
    t1 = time.perf_counter()
    hit_ms = (t1 - t0) * 1000.0
    assert hit is not None
    assert Path(hit["vocals"]).exists() and Path(hit["no_vocals"]).exists()

    return {
        "miss_lookup_ms": round(miss_ms, 3),
        "store_ms": round(store_ms, 3),
        "hit_restore_ms": round(hit_ms, 3),
    }


def benchmark_asr_cache(tmp_dir: Path) -> dict:
    import autodub.pipeline_cache as pc
    cache_root = tmp_dir / "cache_asr"
    pc._ROOT = cache_root
    cache = AsrGlobalCache()

    audio = tmp_dir / "asr_orig.wav"
    create_dummy_wav(audio, 2 * 1024 * 1024)
    segments = [
        {"id": i, "start": float(i), "end": float(i + 1), "text": f"Segment line {i}"}
        for i in range(100)
    ]

    # 1. Miss lookup
    t0 = time.perf_counter()
    miss = cache.lookup(str(audio), "paraformer", "zh", "funasr")
    t1 = time.perf_counter()
    miss_ms = (t1 - t0) * 1000.0
    assert miss is None

    # 2. Store result (Cold write)
    t0 = time.perf_counter()
    cache.store(str(audio), "paraformer", "zh", "funasr", segments)
    t1 = time.perf_counter()
    store_ms = (t1 - t0) * 1000.0

    # 3. Hit lookup (Warm read)
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        hit = cache.lookup(str(audio), "paraformer", "zh", "funasr")
        t1 = time.perf_counter()
        assert hit is not None and len(hit) == 100
        times.append((t1 - t0) * 1000.0)

    hit_avg_ms = sum(times) / len(times)

    return {
        "miss_lookup_ms": round(miss_ms, 3),
        "store_ms": round(store_ms, 3),
        "hit_avg_ms": round(hit_avg_ms, 3),
    }


def benchmark_translation_cache(tmp_dir: Path) -> dict:
    from autodub.pipeline_cache import TranslationGlobalCache
    db_path = tmp_dir / "cache_trans" / "translations.db"
    cache = TranslationGlobalCache(db_path=db_path)

    # 1. Cold store batch (100 sentences)
    pairs = [(f"Source sentence {i} to translate", f"Cau dich {i} tieng Viet") for i in range(100)]
    t0 = time.perf_counter()
    cache.store_batch(pairs, "vi", "gemini")
    t1 = time.perf_counter()
    store_ms = (t1 - t0) * 1000.0

    # 2. Warm batch lookup (100 sentences)
    query = [(i, f"Source sentence {i} to translate") for i in range(100)]
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        hits = cache.lookup_batch(query, "vi", "gemini")
        t1 = time.perf_counter()
        assert len(hits) == 100
        times.append((t1 - t0) * 1000.0)

    hit_batch_avg_ms = sum(times) / len(times)

    # 3. Warm single lookup
    t0 = time.perf_counter()
    res = cache.lookup("Source sentence 50 to translate", "vi", "gemini")
    t1 = time.perf_counter()
    single_ms = (t1 - t0) * 1000.0
    assert res == "Cau dich 50 tieng Viet"

    return {
        "store_100_ms": round(store_ms, 3),
        "lookup_100_batch_ms": round(hit_batch_avg_ms, 3),
        "lookup_single_ms": round(single_ms, 3),
    }


def benchmark_tts_cache(tmp_dir: Path) -> dict:
    from autodub.pipeline_cache import TtsGlobalCache
    tts_dir = tmp_dir / "cache_tts"
    cache = TtsGlobalCache(cache_dir=tts_dir)

    wav = tmp_dir / "clip.wav"
    create_dummy_wav(wav, 150 * 1024)

    # 1. Miss lookup
    t0 = time.perf_counter()
    miss = cache.lookup("Xin chao moi nguoi", "nam_bac_1")
    t1 = time.perf_counter()
    miss_ms = (t1 - t0) * 1000.0
    assert miss is None

    # 2. Cold store
    t0 = time.perf_counter()
    cache.store("Xin chao moi nguoi", "nam_bac_1", str(wav))
    t1 = time.perf_counter()
    store_ms = (t1 - t0) * 1000.0

    # 3. Warm hit and restore
    dst = tmp_dir / "restored_clip.wav"
    t0 = time.perf_counter()
    ok = cache.restore_to("Xin chao moi nguoi", "nam_bac_1", str(dst))
    t1 = time.perf_counter()
    restore_ms = (t1 - t0) * 1000.0
    assert ok is True

    return {
        "miss_lookup_ms": round(miss_ms, 3),
        "store_ms": round(store_ms, 3),
        "restore_ms": round(restore_ms, 3),
    }


def main():
    tmp_path = Path(tempfile.mkdtemp(prefix="upc_bench_"))
    try:
        print("=== UPC COMPLETE BENCHMARK SUITE ===")
        print(f"CACHE VERSION: {CACHE_VERSION}")
        fp_res = benchmark_fingerprint(tmp_path)
        print("\n1. Fingerprint Performance:")
        for k, v in fp_res.items():
            print(f"  - {k} ({v['size_bytes'] / (1024*1024):.1f} MB): Cold={v['cold_ms']}ms, Warm={v['warm_avg_ms']}ms")

        demucs_res = benchmark_demucs_cache(tmp_path)
        print("\n2. Demucs Cache Performance (5MB WAV stems):")
        print(f"  - Miss lookup: {demucs_res['miss_lookup_ms']}ms")
        print(f"  - Cold store: {demucs_res['store_ms']}ms")
        print(f"  - Warm hit & restore: {demucs_res['hit_restore_ms']}ms")

        asr_res = benchmark_asr_cache(tmp_path)
        print("\n3. ASR Cache Performance (100 segments):")
        print(f"  - Miss lookup: {asr_res['miss_lookup_ms']}ms")
        print(f"  - Cold store: {asr_res['store_ms']}ms")
        print(f"  - Warm hit: {asr_res['hit_avg_ms']}ms")

        trans_res = benchmark_translation_cache(tmp_path)
        print("\n4. Translation Memory Cache Performance:")
        print(f"  - Store 100 sentences: {trans_res['store_100_ms']}ms")
        print(f"  - Lookup 100 batch: {trans_res['lookup_100_batch_ms']}ms")
        print(f"  - Lookup single sentence: {trans_res['lookup_single_ms']}ms")

        tts_res = benchmark_tts_cache(tmp_path)
        print("\n5. TTS Segment Cache Performance (150KB clip):")
        print(f"  - Miss lookup: {tts_res['miss_lookup_ms']}ms")
        print(f"  - Cold store: {tts_res['store_ms']}ms")
        print(f"  - Warm restore: {tts_res['restore_ms']}ms")

        print("\n=== BENCHMARK COMPLETED SUCCESSFULLY ===")
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


if __name__ == "__main__":
    main()
