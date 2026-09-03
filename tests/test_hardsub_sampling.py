import os
import numpy as np
import pytest

from autodub.media.hardsub_detector import (
    extract_video_frames,
    FrameSample,
)


def test_extract_video_frames_missing_file():
    samples = extract_video_frames("non_existent_video.mp4")
    assert samples == []


def test_extract_video_frames_with_mock_opencv(tmp_path, monkeypatch):
    dummy_video = str(tmp_path / "mock.mp4")
    with open(dummy_video, "wb") as f:
        f.write(b"mock video bytes")

    class MockCap:
        def __init__(self, path):
            self.opened = True
        def isOpened(self):
            return self.opened
        def get(self, prop):
            return 720 if prop == 3 else (480 if prop == 4 else 0)
        def set(self, prop, val):
            pass
        def read(self):
            # Trả về frame ảnh màu 480x720x3
            img = np.full((480, 720, 3), 120, dtype=np.uint8)
            return True, img
        def release(self):
            self.opened = False

    from autodub.media import hardsub_detector
    monkeypatch.setattr(hardsub_detector.cv2, "VideoCapture", MockCap)
    monkeypatch.setattr("autodub.media.video.probe_duration_s", lambda p: 6.0)


    samples = extract_video_frames(dummy_video, sample_interval_s=2.0, max_samples=4)
    assert len(samples) > 0
    assert isinstance(samples[0], FrameSample)
    assert samples[0].image.shape == (360, 640)
    assert samples[0].timestamp > 0.0
