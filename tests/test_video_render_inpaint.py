import os
from unittest.mock import MagicMock, patch
import pytest

from autodub.media.video import merge_video


@pytest.fixture
def dummy_media(tmp_path):
    vid = tmp_path / "sample.mp4"
    aud = tmp_path / "sample.wav"
    out = tmp_path / "out.mp4"

    vid.write_bytes(b"dummy video data")
    aud.write_bytes(b"dummy audio data")

    return str(vid), str(aud), str(out)


@patch("autodub.media.video.subprocess.run")
@patch("autodub.media.video.probe_dimensions", return_value=(1280, 720))
@patch("autodub.media.video.probe_duration_s", return_value=10.0)
@patch("autodub.media.subtitle.build_filter_complex")

def test_merge_video_blur_mode(mock_build_filter, mock_dur, mock_dims, mock_run, dummy_media):
    vid, aud, out = dummy_media
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    mock_build_filter.return_value = "boxblur_filter_string"

    regions = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15}]

    res = merge_video(
        video_path=vid,
        audio_path=aud,
        output_path=out,
        blur_regions=regions,
        mask_method="blur",
    )

    assert res == out
    # Ở chế độ blur, build_filter_complex nhận regions gốc
    mock_build_filter.assert_called_once()
    called_regions = mock_build_filter.call_args[0][0]
    assert called_regions == regions


@patch("autodub.media.video.subprocess.run")
@patch("autodub.media.video.probe_dimensions", return_value=(1280, 720))
@patch("autodub.media.video.probe_duration_s", return_value=10.0)
@patch("autodub.media.subtitle.build_filter_complex")

@patch("autodub.media.inpaint.inpaint_video_with_cache")
def test_merge_video_ai_inpaint_mode(mock_inpaint, mock_build_filter, mock_dur, mock_dims, mock_run, dummy_media, tmp_path):
    vid, aud, out = dummy_media
    clean_vid = str(tmp_path / "clean_cached.mp4")
    with open(clean_vid, "wb") as f:
        f.write(b"clean video data")

    mock_inpaint.return_value = clean_vid
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    mock_build_filter.return_value = None

    regions = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15}]

    res = merge_video(
        video_path=vid,
        audio_path=aud,
        output_path=out,
        blur_regions=regions,
        mask_method="ai_inpaint",
        inpaint_engine="lama_onnx",
        inpaint_device="cuda",
    )

    assert res == out
    # Kiểm tra inpaint_video_with_cache được gọi
    mock_inpaint.assert_called_once_with(
        video_path=vid,
        regions=regions,
        engine_type="lama_onnx",
        device="cuda",
        model_path=None,
    )

    # Kiểm tra lệnh ffmpeg nhận clean_vid làm input thay vì video gốc
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert clean_vid in cmd


@patch("autodub.media.video.subprocess.run")
@patch("autodub.media.video.probe_dimensions", return_value=(1280, 720))
@patch("autodub.media.video.probe_duration_s", return_value=10.0)
@patch("autodub.media.subtitle.build_filter_complex")
@patch("autodub.media.inpaint.inpaint_video_with_cache")

def test_merge_video_ai_inpaint_fallback_on_error(mock_inpaint, mock_build_filter, mock_dur, mock_dims, mock_run, dummy_media):
    vid, aud, out = dummy_media
    mock_inpaint.side_effect = RuntimeError("GPU out of memory")
    mock_run.return_value = MagicMock(returncode=0, stderr="")
    mock_build_filter.return_value = "fallback_boxblur"

    regions = [{"x": 0.1, "y": 0.8, "w": 0.8, "h": 0.15}]

    res = merge_video(
        video_path=vid,
        audio_path=aud,
        output_path=out,
        blur_regions=regions,
        mask_method="ai_inpaint",
    )

    assert res == out
    # Khi inpaint lỗi, hệ thống tự động fallback truyền regions gốc vào build_filter_complex để làm mờ
    mock_build_filter.assert_called_once()
    called_regions = mock_build_filter.call_args[0][0]
    assert called_regions == regions
