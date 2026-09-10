"""Tests & benchmarks for subtitle alignment instrumentation and performance profiling."""
import json
import math
import os
import struct
import time
import wave
from pathlib import Path
import pytest

from autodub.speech.align import AlignmentStats, align_segments


def _write_tone(path: str, dur: float, rate: int = 16000):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(dur * rate)
        w.writeframes(struct.pack(
            f"<{n}h",
            *[int(8000 * math.sin(2 * math.pi * 440 * i / rate))
              for i in range(n)]))


def generate_benchmark_dataset(base_dir: Path, count: int = 50) -> tuple[list[dict], Path]:
    wav_dir = base_dir / f"wavs_{count}"
    wav_dir.mkdir(parents=True, exist_ok=True)

    short_samples = [
        "vâng ạ.", "đúng thế.", "chào bạn.", "rồi sao?", "tuyệt vời!",
        "khoan đã.", "đi thôi.", "đồng ý.", "cảm ơn.", "không thể nào."
    ]
    normal_samples = [
        "hôm nay thời tiết thật là đẹp và mát mẻ.",
        "chúng ta sẽ cùng nhau tìm hiểu về dự án này.",
        "hệ thống hoạt động với tốc độ cực kỳ ấn tượng.",
        "video sau khi render có chất lượng hình ảnh sắc nét.",
        "phụ đề tự động nhảy từng chữ theo giọng đọc chuẩn xác."
    ]
    long_samples = [
        "trong những năm gần đây công nghệ trí tuệ nhân tạo đã có những bước tiến vượt bậc mang lại rất nhiều giá trị thực tiễn.",
        "chúng tôi cam kết luôn mang đến những trải nghiệm tốt nhất cho người dùng thông qua các tính năng tự động hoá thông minh."
    ]

    segments = []
    curr_time = 0.0
    for i in range(1, count + 1):
        if i % 10 <= 3:  # 30% short
            text = short_samples[(i - 1) % len(short_samples)]
            dur = 0.45
            category = "short"
        elif i % 10 >= 8:  # 20% long
            text = long_samples[(i - 1) % len(long_samples)]
            dur = 3.8
            category = "long"
        else:  # 50% normal
            text = normal_samples[(i - 1) % len(normal_samples)]
            dur = 1.8
            category = "normal"

        wav_name = f"seg_{i:05d}.wav"
        wav_path = wav_dir / wav_name
        _write_tone(str(wav_path), dur)

        segments.append({
            "id": i,
            "start": round(curr_time, 3),
            "end": round(curr_time + dur, 3),
            "duration": dur,
            "text_vi": text,
            "category": category,
        })
        curr_time += dur + 0.2

    return segments, wav_dir


def test_alignment_stats_dataclass():
    stats = AlignmentStats()
    assert stats.total_segments == 0
    assert stats.cache_hits == 0
    assert stats.cache_misses == 0
    assert stats.total_time == 0.0
    assert stats.segments_per_sec == 0.0
    d = stats.to_dict()
    assert "segments_per_sec" in d
    assert "cache_hits" in d


def test_align_segments_instrumentation(tmp_path, monkeypatch):
    """Kiểm tra align_segments ghi nhận chính xác các chỉ số profiler."""
    segments, wav_dir = generate_benchmark_dataset(tmp_path, count=10)
    cache_file = tmp_path / "align_cache.json"

    # Mock model để chạy benchmark test nhanh
    class DummyWord:
        def __init__(self, w, s, e):
            self.word = w
            self.start = s
            self.end = e

    class DummySeg:
        def __init__(self, words):
            self.words = words

    class DummyModel:
        def transcribe(self, wav_path, **kwargs):
            words = [DummyWord(f"w{k}", k * 0.1, (k + 1) * 0.1) for k in range(30)]
            return [DummySeg(words)], None

    monkeypatch.setattr("autodub.speech.align._load_align_model", lambda: (DummyModel(), "cpu", 1))

    stats_cold = AlignmentStats()
    out1 = align_segments(segments, str(wav_dir), "text_vi",
                          cache_path=str(cache_file), stats=stats_cold)

    assert stats_cold.total_segments == 10
    assert stats_cold.cache_misses == 10
    assert stats_cold.cache_hits == 0
    assert stats_cold.total_time > 0
    assert stats_cold.model_load_time >= 0

    # Lượt 2: Phải có cache hits (Warm run)
    stats_warm = AlignmentStats()
    out2 = align_segments(segments, str(wav_dir), "text_vi",
                          cache_path=str(cache_file), stats=stats_warm)

    assert stats_warm.total_segments == 10
    assert stats_warm.cache_hits == 10
    assert stats_warm.cache_misses == 0
    assert stats_warm.total_time < stats_cold.total_time


def test_build_cache_key_deterministic(tmp_path):
    from autodub.speech.align import build_cache_key, ALIGN_CACHE_VERSION, ALIGN_MODEL

    wav_file = tmp_path / "test.wav"
    _write_tone(str(wav_file), 1.0)

    key1 = build_cache_key(str(wav_file), "xin chào", ALIGN_MODEL, "vi", ALIGN_CACHE_VERSION)
    key2 = build_cache_key(str(wav_file), "xin chào", ALIGN_MODEL, "vi", ALIGN_CACHE_VERSION)

    # 1. Deterministic
    assert key1 == key2
    assert isinstance(key1, str)
    assert len(key1) >= 16

    # 2. Text thay đổi -> key khác
    key_diff_text = build_cache_key(str(wav_file), "xin chào bạn", ALIGN_MODEL, "vi", ALIGN_CACHE_VERSION)
    assert key1 != key_diff_text

    # 3. Model thay đổi -> key khác
    key_diff_model = build_cache_key(str(wav_file), "xin chào", "small", "vi", ALIGN_CACHE_VERSION)
    assert key1 != key_diff_model

    # 4. Version thay đổi -> key khác
    key_diff_version = build_cache_key(str(wav_file), "xin chào", ALIGN_MODEL, "vi", ALIGN_CACHE_VERSION + 1)
    assert key1 != key_diff_version

    # 5. Audio thay đổi -> key khác
    time.sleep(0.01)
    _write_tone(str(wav_file), 1.5)  # thay đổi kích thước và mtime
    key_diff_audio = build_cache_key(str(wav_file), "xin chào", ALIGN_MODEL, "vi", ALIGN_CACHE_VERSION)
    assert key1 != key_diff_audio


def test_adaptive_worker_scheduler(monkeypatch):
    """Xác minh bộ điều phối luồng tránh oversubscription và hỗ trợ cấu hình."""
    from autodub.speech.align import compute_align_workers_and_threads

    # 1. GPU: 4 workers song song tối ưu luồng CUDA
    w_gpu, th_gpu = compute_align_workers_and_threads(device="cuda", cpu_count=16)
    assert w_gpu == 4
    assert th_gpu == 1

    # 2. CPU 4 cores: worker * threads <= 4
    w_cpu4, th_cpu4 = compute_align_workers_and_threads(device="cpu", cpu_count=4)
    assert w_cpu4 >= 1
    assert th_cpu4 >= 1
    assert w_cpu4 * th_cpu4 <= 4

    # 3. CPU 8 cores: worker * threads <= 8
    w_cpu8, th_cpu8 = compute_align_workers_and_threads(device="cpu", cpu_count=8)
    assert w_cpu8 >= 1
    assert th_cpu8 >= 1
    assert w_cpu8 * th_cpu8 <= 8

    # 4. Tôn trọng biến môi trường override
    monkeypatch.setenv("ALIGN_WORKERS", "3")
    monkeypatch.setenv("ALIGN_CPU_THREADS", "2")
    w_env, th_env = compute_align_workers_and_threads(device="cpu", cpu_count=16)
    assert w_env == 3
    assert th_env == 2


def test_validate_alignment():
    """Kiểm tra Timing Validator bắt chặt chẽ các trường hợp timing bất hợp lệ."""
    from autodub.speech.align import validate_alignment

    text_words = ["xin", "chào", "bạn"]
    clip_start = 10.0
    clip_dur = 2.0

    # 1. Hợp lệ
    valid_words = [("xin", 10.0, 10.5), ("chào", 10.5, 11.2), ("bạn", 11.2, 11.8)]
    assert validate_alignment(valid_words, text_words, clip_start, clip_dur) is True

    # 2. Sai số lượng từ
    assert validate_alignment(valid_words[:2], text_words, clip_start, clip_dur) is False

    # 3. Đảo ngược thứ tự thời gian (t0 > t1)
    invalid_reverse = [("xin", 10.0, 10.5), ("chào", 11.2, 10.8), ("bạn", 11.2, 11.8)]
    assert validate_alignment(invalid_reverse, text_words, clip_start, clip_dur) is False

    # 4. Từ sau bắt đầu trước từ trước (nhảy lùi thời gian)
    invalid_overlap = [("xin", 10.5, 11.0), ("chào", 10.1, 11.2), ("bạn", 11.2, 11.8)]
    assert validate_alignment(invalid_overlap, text_words, clip_start, clip_dur) is False

    # 5. Timestamp âm
    invalid_neg = [("xin", -0.5, 0.2), ("chào", 0.2, 0.5), ("bạn", 0.5, 1.0)]
    assert validate_alignment(invalid_neg, text_words, clip_start, clip_dur) is False

    # 6. Vượt quá thời lượng clip cho phép
    invalid_overflow = [("xin", 10.0, 10.5), ("chào", 10.5, 11.2), ("bạn", 11.2, 13.5)]
    assert validate_alignment(invalid_overflow, text_words, clip_start, clip_dur) is False


def test_parallel_cache_io(tmp_path, monkeypatch):
    """Kiểm tra hai tiến trình/luồng cùng ghi cache không bị race condition hoặc corrupt file."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    class DummyWord:
        def __init__(self, w, s, e):
            self.word = w
            self.start = s
            self.end = e

    class DummySeg:
        def __init__(self, words):
            self.words = words

    class DummyModel:
        def transcribe(self, wav_path, **kwargs):
            words = [DummyWord(f"w{k}", k * 0.1, (k + 1) * 0.1) for k in range(10)]
            return [DummySeg(words)], None

    monkeypatch.setattr("autodub.speech.align._load_align_model", lambda: (DummyModel(), "cpu", 1))

    segs1, wav_dir1 = generate_benchmark_dataset(tmp_path / "p1", count=5)
    segs2, wav_dir2 = generate_benchmark_dataset(tmp_path / "p2", count=5)
    # Đổi ID của segs2 để không trùng segs1
    for s in segs2:
        s["id"] += 100

    shared_cache = tmp_path / "shared_cache.json"

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(align_segments, segs1, str(wav_dir1), "text_vi", str(shared_cache))
        f2 = pool.submit(align_segments, segs2, str(wav_dir2), "text_vi", str(shared_cache))
        res1 = f1.result()
        res2 = f2.result()

    assert shared_cache.exists()
    with open(shared_cache, encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert len(data) >= 5  # Cache phải chứa entries được merge an toàn




