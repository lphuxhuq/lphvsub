import pytest
from autodub.media.output_profile import OutputProfile
from autodub.media.blur_strategy import BlurStrategy, BlurMode
from autodub.media.encoder_profile import EncoderProfile, QualityMode
from autodub.media.render_plan import RenderPlan
from autodub.media.render_profiler import RenderProfiler
from autodub.media.subtitle import build_filter_complex, build_aspect_ratio_filter


def test_full_pipeline_render_plan_9_16():
    # 1. OutputProfile: 1920x1080 -> 9:16 = 1080x1920
    plan = RenderPlan.build(
        video_w=1920,
        video_h=1080,
        aspect_preset="tiktok_9_16",
        reframe_mode="blur",
        blur_mode=BlurMode.FAST,
    )
    tw, th = plan.target_dimensions()
    assert tw == 1080
    assert th == 1920

    res = plan.build_reframe_filter()
    assert res is not None
    flt, r_w, r_h = res
    assert r_w == 1080 and r_h == 1920
    assert "boxblur=4:1" in flt
    assert "scale=180:320" in flt
    assert "flags=bilinear" in flt


def test_full_pipeline_render_plan_top_split():
    plan = RenderPlan.build(
        video_w=1920,
        video_h=1080,
        aspect_preset="tiktok_9_16",
        reframe_mode="top_split",
        blur_mode=BlurMode.BALANCED,
    )
    res = plan.build_reframe_filter()
    assert res is not None
    flt, tw, th = res
    assert "overlay=(W-w)/2:H*0.12" in flt
    assert "boxblur=6:2" in flt
    assert "scale=270:480" in flt


def test_build_filter_complex_with_render_plan():
    # Kiểm tra toàn bộ filter complex tích hợp mượt mà
    fc = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        aspect_preset="tiktok_9_16",
        reframe_mode="blur",
        srt_path="output/test.ass",
    )
    assert fc is not None
    assert "scale=180:320" in fc
    assert "boxblur=4:1" in fc
    assert "subtitles='output/test.ass'" in fc
    assert fc.endswith("[vout]")
