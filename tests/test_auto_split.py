import os
import subprocess

from autodub.media.auto_split import split_video


def test_auto_split_video(tmp_path, monkeypatch):
    v = str(tmp_path / "v_long.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=10:r=10",
            "-c:v",
            "libx264",
            v,
        ],
        capture_output=True,
    )
    segs = [
        {"id": 1, "dub_start": 0.0, "dub_end": 2.0},
        {"id": 2, "dub_start": 2.5, "dub_end": 5.0},
        {"id": 3, "dub_start": 6.0, "dub_end": 8.0},
        {"id": 4, "dub_start": 8.5, "dub_end": 9.5},
    ]

    monkeypatch.setattr(
        "autodub.media.video.probe_duration_s", lambda p: 10.0 if "v_long.mp4" in p else 5.0
    )

    # split every 4s => Should split at 5.5s (gap between 2.5-5.0 and 6.0-8.0)
    parts = split_video(v, segs, chunk_minutes=4.0 / 60.0, min_gap_s=0.2)
    assert len(parts) == 2
    assert os.path.exists(parts[0])
    assert os.path.exists(parts[1])


def test_auto_split_no_gap(tmp_path):
    v = str(tmp_path / "v_short.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=4:r=10",
            "-c:v",
            "libx264",
            v,
        ],
        capture_output=True,
    )
    segs = [
        {"id": 1, "dub_start": 0.0, "dub_end": 3.9},
    ]
    parts = split_video(v, segs, chunk_minutes=1.0 / 60.0, min_gap_s=0.2)
    assert len(parts) == 1
    assert parts[0] == v
