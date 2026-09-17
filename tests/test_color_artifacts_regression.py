"""Tests to verify fix for green chroma artifacts and color scaling."""

from unittest.mock import MagicMock, patch

import numpy as np

from autodub.media.inpaint.lama_onnx import LaMaOnnxEngine
from autodub.media.render_plan import RenderPlan
from autodub.media.video import merge_video


def test_merge_video_no_hwaccel_in_filtergraph():
    """Verify that FFmpeg command for merge_video does NOT contain -hwaccel auto
    before the input, preventing DXVA2/D3D11VA chroma plane corruption (green patch).
    """
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        m = MagicMock()
        m.returncode = 0
        return m

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch("os.path.exists", return_value=True),
        patch("autodub.media.video.probe_dimensions", return_value=(1920, 1080)),
        patch("autodub.media.video.probe_duration_s", return_value=10.0),
        patch("autodub.media.video.video_encoder_name", return_value="NVIDIA NVENC (GPU)"),
        patch("autodub.media.video.video_codec_args", return_value=["-c:v", "h264_nvenc"]),
    ):
        merge_video(
            video_path="input.mp4",
            audio_path="input.mp3",
            srt_path=None,
            output_path="output.mp4",
            subtitle_mode="none",
            blur_regions=[{"x": 0.1, "y": 0.8, "w": 0.5, "h": 0.1}],
        )

    assert len(calls) > 0
    ffmpeg_cmd = calls[0]
    # Check that -hwaccel is not passed before -i
    assert "-hwaccel" not in ffmpeg_cmd
    # Check that hardware encoder is still used
    assert "h264_nvenc" in ffmpeg_cmd


def test_render_plan_reframe_even_coordinates():
    """Verify that RenderPlan reframe filters use even coordinate expressions for overlay and pad."""
    plan = RenderPlan.build(
        video_w=1920,
        video_h=1080,
        aspect_preset="tiktok_9_16",
        reframe_mode="blur",
    )
    res = plan.build_reframe_filter()
    assert res is not None
    flt, _, _ = res
    assert "overlay=trunc((W-w)/4)*2:trunc((H-h)/4)*2" in flt


def test_render_plan_banner_even_coordinates():
    """Verify that RenderPlan banner filter uses even coordinates for pad."""
    plan = RenderPlan.build(
        video_w=1920,
        video_h=1080,
        aspect_preset="tiktok_9_16",
        reframe_mode="pad",
    )
    res = plan.build_reframe_filter()
    assert res is not None
    flt, _, _ = res
    assert "pad=" in flt
    assert "trunc((ow-iw)/4)*2" in flt


def test_lama_onnx_scale_locking():
    """Verify that LaMaOnnxEngine locks scaling to prevent dark frames from blowing out to white."""
    engine = LaMaOnnxEngine()
    engine._session = MagicMock()
    engine._input_names = ["image", "mask"]
    engine._input_shapes = [[1, 3, 512, 512], [1, 1, 512, 512]]
    engine._output_name = "output"
    engine._fixed_h = 512
    engine._fixed_w = 512

    # Frame 1: normal frame with values in 0..255 (e.g. max 200.0)
    out_tensor_frame1 = np.ones((1, 3, 512, 512), dtype=np.float32) * 200.0
    engine._session.run.return_value = [out_tensor_frame1]

    frame1 = np.ones((100, 100, 3), dtype=np.uint8) * 100
    mask = np.ones((100, 100), dtype=np.uint8) * 255

    res1 = engine.inpaint_frame(frame1, mask)
    assert engine._out_is_255 is True
    # Output should not be multiplied by 255 again
    assert res1.max() <= 200

    # Frame 2: very dark frame where max value is 0.8 (which would falsely trigger <= 1.5 if not locked)
    out_tensor_frame2 = np.ones((1, 3, 512, 512), dtype=np.float32) * 0.8
    engine._session.run.return_value = [out_tensor_frame2]

    res2 = engine.inpaint_frame(frame1, mask)
    # Because engine._out_is_255 is locked to True, 0.8 is clipped to uint8(0 or 1), NOT multiplied by 255 to become 204
    assert res2[mask > 0].max() <= 1
