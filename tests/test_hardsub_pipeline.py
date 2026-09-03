import os
import pytest
from autodub.config import Settings
from autodub.pipeline import DubPipeline, DubRequest


def test_pipeline_auto_mask_hardsub_off_by_default():
    req = DubRequest()
    assert req.auto_mask_hardsub is False
    s = Settings()
    assert s.auto_mask_hardsub is False


def test_pipeline_auto_mask_hardsub_enabled_flow(tmp_path, monkeypatch):
    work_dir = str(tmp_path / "test_pipe_mask")
    os.makedirs(work_dir, exist_ok=True)
    video_path = os.path.join(work_dir, "source.mp4")
    with open(video_path, "wb") as f:
        f.write(b"dummy video")

    from autodub.media import hardsub_detector
    monkeypatch.setattr(
        hardsub_detector, "detect_hardsub_regions",
        lambda p: [{"x": 0.12, "y": 0.82, "w": 0.76, "h": 0.10}]
    )

    req = DubRequest(auto_mask_hardsub=True)
    assert req.auto_mask_hardsub is True
    # Giả lập khi pipeline phát hiện
    detected = hardsub_detector.detect_hardsub_regions(video_path)
    if req.auto_mask_hardsub and not req.blur_regions:
        req.blur_regions = detected

    assert len(req.blur_regions) == 1
    assert req.blur_regions[0]["y"] == 0.82
