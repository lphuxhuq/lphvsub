import time
import pytest
from autodub.utils import ProgressTracker, format_eta


def test_progress_tracker_sentence_mode():
    tracker = ProgressTracker(total=10, step_name="Dịch câu", unit="câu", log_step=2, min_log_interval=10.0)
    assert tracker.total == 10.0
    assert tracker.unit == "câu"

    # Bước 1: Mốc đầu tiên luôn log
    should_log, msg = tracker.step(1, detail="Câu #1: 'Xin chào'")
    assert should_log is True
    assert "Dịch câu: 1/10 câu (10.0%)" in msg
    assert "Câu #1: 'Xin chào'" in msg
    assert "câu/s" in msg

    # Bước 2: log_step = 2 (tổng = 2) -> milestone
    should_log, msg = tracker.step(1, detail="Câu #2: 'Tạm biệt'")
    assert should_log is True
    assert "Dịch câu: 2/10 câu (20.0%)" in msg

    # Bước 3: (tổng = 3) -> không phải milestone
    should_log, msg = tracker.step(1, detail="Câu #3")
    assert should_log is False
    assert msg == ""

    # Bước 4-10: nhảy đến 10
    should_log, msg = tracker.step(7, detail="Hoàn thành các câu còn lại")
    assert should_log is True
    assert "10/10 câu (100.0%)" in msg

    summary = tracker.summary()
    assert "Dịch câu hoàn tất: 10 câu" in summary
    assert "câu/s" in summary


def test_progress_tracker_seconds_mode():
    tracker = ProgressTracker(total=120.0, step_name="ASR Audio", unit="s", min_log_interval=10.0)
    assert tracker.unit == "s"

    # update_to 15s
    should_log, msg = tracker.update_to(15.0, detail="Đoạn [0s-15s]")
    assert should_log is True
    assert "ASR Audio: 15.0/120.0 s (12.5%)" in msg
    assert "x" in msg  # Speed formatted in x real-time

    # update_to 120s (forced complete)
    should_log, msg = tracker.update_to(120.0, detail="Hết audio")
    assert should_log is True
    assert "120.0/120.0 s (100.0%)" in msg

    summary = tracker.summary()
    assert "ASR Audio hoàn tất: 120.0 s" in summary
    assert "x" in summary


def test_progress_tracker_thread_safety():
    from concurrent.futures import ThreadPoolExecutor

    tracker = ProgressTracker(total=100, step_name="Song song", unit="câu")
    
    def worker(_):
        tracker.step(1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(100)))

    assert tracker.done == 100
    summary = tracker.summary()
    assert "100 câu" in summary
