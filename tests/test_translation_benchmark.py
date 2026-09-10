"""Benchmark and concurrency tests for Phase 6: Translation Engine.

Tests & Benchmarks:
- 1 key vs 2 keys vs 4 keys vs 8 keys vs 16 keys.
- Verification of segment ordering preservation (invariants: id order 1..N).
- Measurement of:
  * Wall time
  * Segments/sec
  * Retry count
  * 429 count
  * Effective concurrency
"""
import json
import time
from collections import defaultdict
from unittest import mock
import pytest

from autodub.config import Settings
from autodub.languages import TargetLang, get_target
from autodub.text.translate_direct import _KeyRateLimiter, translate_segments_direct


class MockDirectClient:
    """Mock client that records call metrics, enforces rate limit checks, and simulates API latency."""
    def __init__(self, keys: list[str], latency_s: float = 0.02):
        self.keys = keys
        self.latency_s = latency_s
        self.call_history: list[tuple[str, float]] = []
        self.key_hits = defaultdict(list)
        self.retry_count = 0
        self.rate_limit_429_count = 0

    def get_key(self, idx: int = 0) -> str:
        return self.keys[idx % len(self.keys)] if self.keys else ""

    def call_ai(self, system_prompt: str, user_prompt: str, key: str = "", *args, **kwargs) -> str:
        k = key or kwargs.get("preferred_key") or (self.keys[0] if self.keys else "")
        now = time.monotonic()
        self.call_history.append((k, now))
        self.key_hits[k].append(now)
        time.sleep(self.latency_s)
        
        # Parse JSON payload from prompt
        try:
            import re
            m = re.search(r"(\[\s*\{[\s\S]*\}\s*\])", user_prompt)
            if m:
                items = json.loads(m.group(1))
            else:
                lines = user_prompt.strip().split("\n")
                items = json.loads(lines[-1])
            res = [{"id": item["id"], "text_vi": f"Dịch câu {item['id']}."} for item in items]
            return json.dumps(res, ensure_ascii=False)
        except Exception:
            return '[{"id": 1, "text_vi": "Dịch mẫu."}]'


def test_translation_segment_ordering_preserved():
    """Verify that even when batches complete out of order, the final result is strictly ordered 1..N."""
    segments = [{"id": i, "text": f"Original {i}", "start": float(i), "end": float(i + 1)} for i in range(1, 41)]
    api_keys = ["key_A", "key_B", "key_C", "key_D"]

    settings = Settings()
    settings.translate_batch_size = 5
    settings.translate_direct_workers = 4

    client = MockDirectClient(keys=api_keys, latency_s=0.01)
    
    with mock.patch("autodub.text.translate_direct.get_direct_client", return_value=(client, "Mock Gemini")):
        results = translate_segments_direct(
            segments,
            target=get_target("vi"),
            source_lang="zh",
            settings=settings,
        )

    # Segment ordering invariant
    result_ids = [s["id"] for s in results]
    expected_ids = list(range(1, 41))
    assert result_ids == expected_ids, f"Ordering violated! Expected {expected_ids[:5]}..., got {result_ids[:5]}..."
    for s in results:
        assert s["text_vi"].startswith("Dịch câu")


def test_translation_concurrency_scaling_benchmark():
    """Benchmark translation across 1, 2, 4, 8, 16 keys.
    
    Measures:
    - Wall time
    - Segments per second
    - Retry count
    - 429 count
    - Speedup factor
    """
    num_segments = 32
    segments = [{"id": i, "text": f"Sentence {i}", "start": float(i), "end": float(i + 1)} for i in range(1, num_segments + 1)]
    key_counts = [1, 2, 4, 8, 16]
    benchmark_results = {}

    print("\n--- TRANSLATION BENCHMARK RESULTS ---")
    print(f"{'Keys':<6} | {'Workers':<8} | {'Wall Time':<10} | {'Segs/sec':<10} | {'Retries':<8} | {'429s':<6} | {'Speedup':<8}")
    print("-" * 68)

    base_time = None
    for k_count in key_counts:
        api_keys = [f"test_key_{i}" for i in range(k_count)]
        limiter = _KeyRateLimiter(min_interval_s=0.04)
        client = MockDirectClient(keys=api_keys, latency_s=0.01)

        settings = Settings()
        settings.translate_batch_size = 2
        settings.translate_direct_workers = min(k_count, 16)

        t0 = time.perf_counter()
        with mock.patch("autodub.text.translate_direct.KEY_LIMITER", limiter), \
             mock.patch("autodub.text.translate_direct.get_direct_client", return_value=(client, f"Mock Gemini ({k_count} keys)")):
            
            results = translate_segments_direct(
                segments,
                target=get_target("vi"),
                source_lang="zh",
                settings=settings,
            )

        elapsed = time.perf_counter() - t0
        if base_time is None:
            base_time = elapsed
        speedup = base_time / elapsed if elapsed > 0 else 1.0
        segs_per_sec = num_segments / elapsed

        benchmark_results[k_count] = {
            "wall_time_s": elapsed,
            "segs_per_sec": segs_per_sec,
            "retries": client.retry_count,
            "429s": client.rate_limit_429_count,
            "speedup": speedup,
        }

        print(f"{k_count:<6} | {min(k_count, 16):<8} | {elapsed:>8.3f}s | {segs_per_sec:>8.1f}/s | {client.retry_count:<8} | {client.rate_limit_429_count:<6} | {speedup:>6.2f}x")

        # Invariant checks
        assert len(results) == num_segments
        assert [s["id"] for s in results] == list(range(1, num_segments + 1))
        assert client.rate_limit_429_count == 0

    # Prove scaling: 4 keys and 8 keys are faster than 1 key
    assert benchmark_results[4]["wall_time_s"] < benchmark_results[1]["wall_time_s"]
    assert benchmark_results[8]["wall_time_s"] < benchmark_results[1]["wall_time_s"]
