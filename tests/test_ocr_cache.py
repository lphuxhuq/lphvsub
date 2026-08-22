"""Unit test cho cache + selective behavior của run_selective_ocr (TASK-3)."""
import json
import os

import pytest

import autodub.media.ocr as ocr
from autodub.config import Settings


class _Settings(Settings):
    """Settings test — không đụng env máy thật."""

    def __init__(self):
        super().__init__()
        self.ocr_fps = 3
        self.ocr_region_height = 0.18
        self.ocr_venv_python = "X:/fake/venv/python.exe"


_WORKER_MSGS = [
    {"frame": "", "lines": [{"text": "你为什么不告诉我", "score": 0.95,
                             "top_y": 1, "box": [[0, 0], [1, 1], [2, 2],
                                                 [3, 3]]}]},
]


def test_no_suspects_zero_cost(tmp_path, monkeypatch):
    """AC-6: không suspect → không gọi ffmpeg, không gọi worker."""
    calls = {"ffmpeg": 0, "worker": 0}
    monkeypatch.setattr(ocr, "_extract_frames",
                        lambda *a, **k: calls.__setitem__(
                            "ffmpeg", calls["ffmpeg"] + 1) or [])
    monkeypatch.setattr(ocr, "_run_ocr_worker",
                        lambda *a, **k: calls.__setitem__(
                            "worker", calls["worker"] + 1) or [])
    result = ocr.run_selective_ocr("video.mp4", [], _Settings(),
                                   str(tmp_path))
    assert result == []
    assert calls == {"ffmpeg": 0, "worker": 0}


def test_cache_hit_avoids_rework(tmp_path, monkeypatch):
    """NFR-6: cùng (video, windows, fps, region) → dùng cache, 0 ffmpeg."""
    calls = {"ffmpeg": 0, "worker": 0}
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)
    suspects = [{"start": 2.0, "end": 4.0}]

    def _fake_extract(video_path, start, end, fps, region, out_dir):
        calls["ffmpeg"] += 1
        os.makedirs(out_dir, exist_ok=True)
        p = os.path.join(out_dir, "frame_00001.jpg")
        with open(p, "wb") as f:
            f.write(b"jpg")
        return [(p, start)]

    def _fake_worker(paths, venv):
        calls["worker"] += 1
        return [dict(_WORKER_MSGS[0], frame=paths[0])]

    monkeypatch.setattr(ocr, "_extract_frames", _fake_extract)
    monkeypatch.setattr(ocr, "_run_ocr_worker", _fake_worker)
    monkeypatch.setattr(ocr, "_probe_duration", lambda v: 30.0)

    s = _Settings()
    first = ocr.run_selective_ocr(str(video), suspects, s, str(tmp_path))
    assert calls == {"ffmpeg": 1, "worker": 1}
    assert len(first) == 1
    assert first[0]["text"] == "你为什么不告诉我"

    second = ocr.run_selective_ocr(str(video), suspects, s, str(tmp_path))
    assert calls == {"ffmpeg": 1, "worker": 1}  # cache hit — không chạy lại
    assert second == first


def test_cache_invalidated_by_different_windows(tmp_path, monkeypatch):
    calls = {"ffmpeg": 0}
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)
    monkeypatch.setattr(
        ocr, "_extract_frames",
        lambda *a, **k: calls.__setitem__("ffmpeg", calls["ffmpeg"] + 1)
        or [])
    monkeypatch.setattr(ocr, "_run_ocr_worker", lambda *a, **k: [])
    monkeypatch.setattr(ocr, "_probe_duration", lambda v: 30.0)

    s = _Settings()
    ocr.run_selective_ocr(str(video), [{"start": 2.0, "end": 4.0}],
                          s, str(tmp_path))
    ocr.run_selective_ocr(str(video), [{"start": 10.0, "end": 12.0}],
                          s, str(tmp_path))
    assert calls["ffmpeg"] == 2  # window khác → cache miss


def test_worker_error_raises_for_caller(tmp_path, monkeypatch):
    """Worker chết → exception rõ ràng (pipeline TASK-6 sẽ catch)."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)

    def _boom(*a, **k):
        raise RuntimeError("OCR worker chết")

    monkeypatch.setattr(ocr, "_extract_frames",
                        lambda *a, **k: [("/tmp/x.jpg", 1.0)])
    monkeypatch.setattr(ocr, "_run_ocr_worker", _boom)
    monkeypatch.setattr(ocr, "_probe_duration", lambda v: 30.0)
    with pytest.raises(RuntimeError, match="OCR worker"):
        ocr.run_selective_ocr(str(video), [{"start": 2.0, "end": 4.0}],
                              _Settings(), str(tmp_path))


def test_cache_file_schema(tmp_path, monkeypatch):
    """File cache đúng vị trí data/ và schema {key, segments}."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"x" * 10)
    monkeypatch.setattr(ocr, "_extract_frames", lambda *a, **k: [])
    monkeypatch.setattr(ocr, "_probe_duration", lambda v: 30.0)
    ocr.run_selective_ocr(str(video), [{"start": 2.0, "end": 4.0}],
                          _Settings(), str(tmp_path))
    cache = tmp_path / "data" / "ocr_result.json"
    assert cache.exists()
    data = json.loads(cache.read_text(encoding="utf-8"))
    assert set(data) == {"key", "segments"}
