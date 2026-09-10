"""Regression tests for _KeyRateLimiter (BUG-001 fix).

Proves that:
1. Single key respects min_interval_s.
2. Different keys can execute concurrently (no cross-key blocking).
3. Same-key contention serialises correctly.
4. Many workers × many keys scale.
"""
from __future__ import annotations

import threading
import time

import pytest

from autodub.text.translate_direct import _KeyRateLimiter


class TestKeyRateLimiterSingleKey:
    """One key — basic rate limiting works."""

    def test_first_acquire_immediate(self):
        limiter = _KeyRateLimiter(min_interval_s=1.0)
        t0 = time.monotonic()
        limiter.acquire("k")
        assert time.monotonic() - t0 < 0.1

    def test_second_acquire_waits(self):
        limiter = _KeyRateLimiter(min_interval_s=0.3)
        limiter.acquire("k")
        t0 = time.monotonic()
        limiter.acquire("k")
        elapsed = time.monotonic() - t0
        # Must wait ~0.3s (allow tolerance)
        assert elapsed >= 0.2


class TestKeyRateLimiterMultiKey:
    """BUG-001 regression: different keys MUST NOT block each other."""

    def test_different_keys_concurrent(self):
        """Two threads using different keys should finish in ~interval, not ~2×interval."""
        limiter = _KeyRateLimiter(min_interval_s=0.4)
        # Pre-acquire both keys so second acquire must wait
        limiter.acquire("A")
        limiter.acquire("B")

        results: dict[str, float] = {}
        barrier = threading.Barrier(2)

        def worker(key: str):
            barrier.wait()
            t0 = time.monotonic()
            limiter.acquire(key)
            results[key] = time.monotonic() - t0

        threads = [threading.Thread(target=worker, args=(k,)) for k in ("A", "B")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Both should complete in ~0.4s (parallel), not ~0.8s (serial)
        assert results["A"] < 0.6, f"Key A took {results['A']:.3f}s (should be ~0.4)"
        assert results["B"] < 0.6, f"Key B took {results['B']:.3f}s (should be ~0.4)"

    def test_four_keys_parallel(self):
        """4 distinct keys should all resolve in roughly 1 interval, not 4."""
        limiter = _KeyRateLimiter(min_interval_s=0.3)
        keys = ["K1", "K2", "K3", "K4"]
        for k in keys:
            limiter.acquire(k)

        results: dict[str, float] = {}
        barrier = threading.Barrier(len(keys))

        def worker(key: str):
            barrier.wait()
            t0 = time.monotonic()
            limiter.acquire(key)
            results[key] = time.monotonic() - t0

        threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # Wall time should be ~0.3s (parallel), not ~1.2s (serial)
        max_wait = max(results.values())
        assert max_wait < 0.6, f"Max wait {max_wait:.3f}s — keys are blocking each other"


class TestKeyRateLimiterSameKeyContention:
    """Same key, multiple threads — must serialise correctly."""

    def test_same_key_serialised(self):
        limiter = _KeyRateLimiter(min_interval_s=0.2)
        n_threads = 4
        timestamps: list[float] = []
        lock = threading.Lock()
        barrier = threading.Barrier(n_threads)

        def worker():
            barrier.wait()
            limiter.acquire("SAME")
            with lock:
                timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(timestamps) == n_threads
        timestamps.sort()
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            # Each successive acquire should wait ~0.2s
            assert gap >= 0.15, f"Gap {i}: {gap:.3f}s — same-key rate not enforced"


class TestKeyRateLimiterStress:
    """Mixed workload: some keys shared, some unique."""

    def test_mixed_keys_8_workers(self):
        limiter = _KeyRateLimiter(min_interval_s=0.15)
        keys = ["shared", "shared", "uniq1", "uniq2", "shared", "uniq3", "uniq4", "uniq5"]
        results: list[tuple[str, float]] = []
        lock = threading.Lock()
        barrier = threading.Barrier(len(keys))

        def worker(key: str):
            barrier.wait()
            t0 = time.monotonic()
            limiter.acquire(key)
            elapsed = time.monotonic() - t0
            with lock:
                results.append((key, elapsed))

        threads = [threading.Thread(target=worker, args=(k,)) for k in keys]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(results) == len(keys)
        # Unique keys should resolve fast
        unique_waits = [e for k, e in results if k != "shared"]
        for w in unique_waits:
            assert w < 0.4, f"Unique key waited {w:.3f}s — should be near-instant"
