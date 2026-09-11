from autodub.media.output_profile import DEFAULT_MAX_PIXELS, OutputProfile


def test_output_profile_9_16_normalization():
    # Video 1920x1080 chuyển sang 9:16 phải ra chuẩn 1080x1920 (không phải 1920x3414)
    profile = OutputProfile.resolve(1920, 1080, "tiktok_9_16")
    assert profile is not None
    assert profile.target_w == 1080
    assert profile.target_h == 1920
    assert profile.target_w * profile.target_h <= DEFAULT_MAX_PIXELS
    assert abs(profile.aspect_ratio - (9.0 / 16.0)) < 0.01


def test_output_profile_16_9_normalization():
    profile = OutputProfile.resolve(1080, 1920, "youtube_16_9")
    assert profile is not None
    assert profile.target_w == 1920
    assert profile.target_h == 1080
    assert profile.target_w * profile.target_h <= DEFAULT_MAX_PIXELS
    assert abs(profile.aspect_ratio - (16.0 / 9.0)) < 0.01


def test_output_profile_square():
    profile = OutputProfile.resolve(1920, 1080, "square_1_1")
    assert profile is not None
    assert profile.target_w == 1080
    assert profile.target_h == 1080
    assert profile.target_w == profile.target_h


def test_output_profile_original_none():
    assert OutputProfile.resolve(1920, 1080, "original") is None
    assert OutputProfile.resolve(1920, 1080, None) is None


def test_pixel_budget_enforcement():
    # Thử yêu cầu độ phân giải lớn vượt budget
    profile = OutputProfile.resolve(3840, 2160, "tiktok_9_16", max_pixels=1_000_000)
    assert profile is not None
    assert profile.target_w * profile.target_h <= 1_000_000
    assert profile.target_w % 2 == 0
    assert profile.target_h % 2 == 0
