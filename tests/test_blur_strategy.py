from autodub.media.blur_strategy import BlurMode, BlurStrategy


def test_blur_strategy_fast():
    spec = BlurStrategy.get_spec(1080, 1920, BlurMode.FAST)
    assert spec.low_w == 180
    assert spec.low_h == 320
    assert spec.boxblur_radius == 4
    assert spec.boxblur_power == 1
    assert spec.upscale_flags == "bilinear"

    flt = BlurStrategy.build_background_filter(1080, 1920, BlurMode.FAST)
    assert "scale=180:320" in flt
    assert "boxblur=4:1" in flt
    assert "scale=1080:1920:flags=bilinear" in flt


def test_blur_strategy_balanced():
    spec = BlurStrategy.get_spec(1080, 1920, BlurMode.BALANCED)
    assert spec.low_w == 270
    assert spec.low_h == 480
    assert spec.boxblur_radius == 6
    assert spec.upscale_flags == "bicubic"


def test_blur_strategy_quality():
    spec = BlurStrategy.get_spec(1080, 1920, BlurMode.QUALITY)
    assert spec.low_w == 540
    assert spec.low_h == 960
    assert spec.boxblur_radius == 10
    assert spec.upscale_flags == "lanczos"
