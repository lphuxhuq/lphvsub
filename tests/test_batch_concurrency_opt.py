"""Unit tests for optimized batch concurrency, GPU guard, and flat export."""
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from autodub.batch import BatchItem, _build_item_request, _copy_to_export_dir, run_batch
from autodub.concurrency import detect_system_capabilities, gpu_resource_guard
from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest, DubResult


def test_detect_system_capabilities():
    caps = detect_system_capabilities()
    assert "cpu_count" in caps
    assert "recommended_threads" in caps
    assert caps["recommended_threads"] >= 1
    assert caps["max_threads"] >= caps["recommended_threads"]


def test_gpu_resource_guard():
    import threading
    import time

    executed = []

    def task(i):
        with gpu_resource_guard():
            executed.append(f"start_{i}")
            time.sleep(0.05)
            executed.append(f"end_{i}")

    t1 = threading.Thread(target=task, args=(1,))
    t2 = threading.Thread(target=task, args=(2,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(executed) == 4
    # Ensure one task completed before the other started (serialized)
    assert (executed[0] == "start_1" and executed[1] == "end_1") or (
        executed[0] == "start_2" and executed[1] == "end_2"
    )


def test_copy_to_export_dir(tmp_path):
    export_dir = tmp_path / "unified_export"
    export_dir.mkdir()

    src_video = tmp_path / "dubbed_video.mp4"
    src_video.write_bytes(b"dummy video content")

    report = {
        "title": "My Awesome Video",
        "dubbed_video": str(src_video),
        "session_id": "20260831_test",
    }

    _copy_to_export_dir(report, str(export_dir))

    copied_files = list(export_dir.glob("*.mp4"))
    assert len(copied_files) == 1
    assert copied_files[0].name == "My Awesome Video.mp4"
    assert copied_files[0].read_bytes() == b"dummy video content"


def test_batch_concurrent_with_export_dir(tmp_path):
    export_dir = tmp_path / "export_all"
    export_dir.mkdir()

    settings = Settings()
    settings.output_dir = str(tmp_path / "output")
    req_template = DubRequest(voice="Trúc Ly")

    item1 = BatchItem(url="https://example.com/video1")
    item2 = BatchItem(url="https://example.com/video2", voice="Minh Đức")

    with patch.object(DubPipeline, "run") as mock_run:
        def fake_run(req):
            video_file = tmp_path / f"fake_{req.url.split('/')[-1]}.mp4"
            video_file.write_bytes(b"fake mp4")
            return DubResult(
                status="completed",
                work_dir=str(tmp_path),
                report={
                    "title": f"Title {req.url.split('/')[-1]}",
                    "dubbed_video": str(video_file),
                    "session_id": req.url.split("/")[-1],
                },
            )

        mock_run.side_effect = fake_run

        summary = run_batch(
            [item1, item2],
            settings,
            req_template,
            concurrency=2,
            export_dir=str(export_dir),
        )

        assert summary.total == 2
        assert summary.success == 2
        assert summary.failed == 0

        # Check export directory
        copied = list(export_dir.glob("*.mp4"))
        assert len(copied) == 2
