"""Tests for MediaValidator component."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autodub.media.download.validator import MediaValidator, ValidationResult


@pytest.fixture
def validator():
    return MediaValidator()


def test_validator_nonexistent_file(validator, tmp_path):
    res = validator.validate(tmp_path / "does_not_exist.mp4")
    assert not res.valid
    assert "does not exist" in res.error_message


def test_validator_too_small_file(validator, tmp_path):
    small_file = tmp_path / "small.mp4"
    small_file.write_bytes(b"hello world")
    res = validator.validate(small_file, min_bytes=1024)
    assert not res.valid
    assert "File size too small" in res.error_message


def test_validator_corrupt_content(validator, tmp_path):
    corrupt_file = tmp_path / "corrupt.mp4"
    corrupt_file.write_bytes(b"A" * 2048)
    res = validator.validate(corrupt_file)
    assert not res.valid
    assert "Corrupt or invalid container" in res.error_message or "failed" in res.error_message


def test_validator_mocked_valid_stream(validator, tmp_path):
    dummy_file = tmp_path / "mock.mp4"
    dummy_file.write_bytes(b"0" * 2000)

    mock_ffprobe_data = {
        "format": {
            "duration": "12.500",
            "size": "2000",
            "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        },
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
            }
        ]
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(mock_ffprobe_data)

    with patch("subprocess.run", return_value=mock_proc):
        res = validator.validate(dummy_file, require_video=True, require_audio=True)
        assert res.valid
        assert res.duration == 12.5
        assert res.width == 1920
        assert res.height == 1080
        assert res.fps == 30.0
        assert res.video_codec == "h264"
        assert res.audio_codec == "aac"
        assert res.has_video
        assert res.has_audio


def test_validator_missing_audio_when_required(validator, tmp_path):
    dummy_file = tmp_path / "mock_silent.mp4"
    dummy_file.write_bytes(b"0" * 2000)

    mock_ffprobe_data = {
        "format": {"duration": "10.0"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1280,
                "height": 720,
                "r_frame_rate": "24/1",
            }
        ]
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(mock_ffprobe_data)

    with patch("subprocess.run", return_value=mock_proc):
        # Audio required -> should fail
        res = validator.validate(dummy_file, require_audio=True)
        assert not res.valid
        assert "Audio stream required but missing" in res.error_message

        # Audio not required -> should pass
        res_no_audio = validator.validate(dummy_file, require_audio=False)
        assert res_no_audio.valid


def test_validator_real_ffmpeg_generated_media(validator, tmp_path):
    """Generate a real 1-second MP4 test file via ffmpeg and validate with actual ffprobe."""
    test_media = tmp_path / "real_test.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(test_media)
    ]
    sub_res = subprocess.run(cmd, capture_output=True)
    if sub_res.returncode != 0:
        pytest.skip("ffmpeg not capable of synthetic media creation on this host")

    assert test_media.exists()
    res = validator.validate(test_media, require_video=True, require_audio=True)
    assert res.valid
    assert res.width == 320
    assert res.height == 240
    assert res.fps == 30.0
    assert res.duration >= 0.9
    assert res.has_video
    assert res.has_audio
