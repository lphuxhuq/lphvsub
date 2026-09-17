from autodub.media.inpaint.base import get_bounding_box_for_regions
from autodub.media.subtitle import _to_pixels


def test_to_pixels_always_even():
    # Test với các tọa độ tỉ lệ lẻ
    region = {"x": 0.1333, "y": 0.2777, "w": 0.3555, "h": 0.4111}
    x, y, w, h = _to_pixels(region, video_w=1920, video_h=1080)
    assert x % 2 == 0, f"x ({x}) must be even"
    assert y % 2 == 0, f"y ({y}) must be even"
    assert w % 2 == 0, f"w ({w}) must be even"
    assert h % 2 == 0, f"h ({h}) must be even"


def test_bounding_box_for_regions_always_even():
    regions = [{"x": 0.1333, "y": 0.2777, "w": 0.3555, "h": 0.4111}]
    x, y, w, h = get_bounding_box_for_regions(regions, width=1920, height=1080, padding=15)
    assert x % 2 == 0, f"Bounding box x ({x}) must be even"
    assert y % 2 == 0, f"Bounding box y ({y}) must be even"
    assert w % 2 == 0, f"Bounding box w ({w}) must be even"
    assert h % 2 == 0, f"Bounding box h ({h}) must be even"
