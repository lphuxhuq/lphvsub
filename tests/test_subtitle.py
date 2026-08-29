"""Tests for subtitle burning and region-blur filtergraph construction."""

from autodub.media.subtitle import (
    blur_filter,
    build_filter_complex,
    build_force_style,
    escape_subtitles_path,
    hex_to_ass_color,
)

W, H = 1920, 1080
FULL_WIDTH_BAND = {"x": 0.0, "y": 0.85, "w": 1.0, "h": 0.12}


# --------------------------- path escaping --------------------------- #

def test_escape_windows_path():
    out = escape_subtitles_path(r"C:\Users\me\out\sub.srt")
    assert out == "C\\:/Users/me/out/sub.srt"
    assert "\\U" not in out          # no stray backslash escapes


def test_escape_posix_path_only_touches_colon():
    assert escape_subtitles_path("/home/me/sub.srt") == "/home/me/sub.srt"


def test_escape_single_quote():
    # Inside ffmpeg single quotes a backslash is literal, so ' must use the
    # close-escape-reopen splice ('\'') — \' would end the quoted token.
    assert escape_subtitles_path("/tmp/bo's.srt") == "/tmp/bo'\\''s.srt"


# --------------------------- style --------------------------- #

def test_force_style_defaults_and_override():
    assert "FontSize=22" in build_force_style()
    assert "FontSize=40" in build_force_style({"font_size": 40})
    assert "Alignment=2" in build_force_style()      # bottom-centre


def test_force_style_position_maps_to_alignment():
    assert "Alignment=2" in build_force_style({"position": "bottom"})
    assert "Alignment=5" in build_force_style({"position": "middle"})
    assert "Alignment=8" in build_force_style({"position": "top"})


def test_hex_to_ass_color_bgr_order():
    # pure red #FF0000 → &H000000FF& (BGR, opaque alpha 00)
    assert hex_to_ass_color("#FF0000") == "&H000000FF&"
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF&"
    assert hex_to_ass_color("#000000") == "&H00000000&"
    assert hex_to_ass_color("bad") == "&H00FFFFFF&"    # invalid → white


def test_force_style_custom_colors():
    style = build_force_style({"color": "#FF0000", "outline_color": "#00FF00"})
    assert "PrimaryColour=&H000000FF&" in style       # red text
    assert "OutlineColour=&H0000FF00&" in style       # green outline


# --------------------------- no-op --------------------------- #

def test_no_filter_when_nothing_requested():
    assert build_filter_complex(None, W, H) is None
    assert build_filter_complex([], W, H, None) is None


# --------------------------- subtitles only --------------------------- #

def test_subtitles_only_graph():
    graph = build_filter_complex(None, W, H, "/tmp/vi.srt")
    assert graph.startswith("[0:v]subtitles='/tmp/vi.srt'")
    assert graph.endswith("[vout]")
    assert "crop" not in graph and "boxblur" not in graph


# --------------------------- blur only --------------------------- #

def test_blur_only_ends_at_vout_via_null():
    graph = build_filter_complex([FULL_WIDTH_BAND], W, H)
    assert "boxblur" in graph
    assert graph.endswith("null[vout]")
    assert "subtitles" not in graph


def test_blur_region_converted_to_pixels():
    graph = build_filter_complex([FULL_WIDTH_BAND], W, H)
    # y=0.85*1080=918, h=0.12*1080=129.6→130 (even), w=1920
    assert "crop=1920:130:0:918" in graph
    assert "overlay=0:918" in graph


def test_blur_dimensions_are_even():
    """Odd crop sizes break yuv420p chroma subsampling."""
    graph = build_filter_complex([{"x": 0, "y": 0, "w": 0.333, "h": 0.111}], W, H)
    crop = [p for p in graph.split(";") if "crop=" in p][0]
    w, h = crop.split("crop=")[1].split(",")[0].split(":")[:2]
    assert int(w) % 2 == 0 and int(h) % 2 == 0


def test_region_clamped_to_frame():
    """An oversized region must not crop outside the video."""
    graph = build_filter_complex([{"x": 0.9, "y": 0.9, "w": 0.5, "h": 0.5}], W, H)
    crop = [p for p in graph.split(";") if "crop=" in p][0]
    w, h, x, y = (int(v) for v in crop.split("crop=")[1].split(",")[0].split(":"))
    assert x + w <= W and y + h <= H


def test_multiple_regions_chain_sequentially():
    graph = build_filter_complex(
        [FULL_WIDTH_BAND, {"x": 0.0, "y": 0.0, "w": 0.3, "h": 0.1}], W, H)
    assert graph.count("boxblur") == 2
    assert "[v1]split[b1][b1c]" in graph      # second region consumes the first's output
    assert graph.endswith("[vout]")


def test_blur_radius_capped_for_small_regions():
    """ffmpeg rejects a radius >= plane/2; chroma is half-size in yuv420p.

    Regression: boxblur=10 on a 192x36 band failed with
    "Invalid chroma_param radius value 10, must be >= 0 and < 9".
    """
    assert blur_filter(1920, 130) == "boxblur=10:2"     # large: full strength
    assert blur_filter(192, 36) == "boxblur=8:2"        # 36//4-1 = 8
    assert blur_filter(20, 4) == "boxblur=1:2"          # tiny: floor at 1
    assert blur_filter(2, 2) == "boxblur=1:2"           # never 0


def test_small_region_graph_uses_reduced_radius():
    graph = build_filter_complex([{"x": 0, "y": 0, "w": 0.1, "h": 0.03}], W, H)
    assert "boxblur=7:2" in graph                       # 32//4-1 = 7


def test_time_window_adds_enable_expression():
    region = {**FULL_WIDTH_BAND, "t_start": 1.5, "t_end": 4.0}
    graph = build_filter_complex([region], W, H)
    assert "enable='between(t,1.5,4.0)'" in graph


def test_no_enable_without_full_time_window():
    graph = build_filter_complex([{**FULL_WIDTH_BAND, "t_start": 1.0}], W, H)
    assert "enable" not in graph


# --------------------------- combined --------------------------- #

def test_blur_then_subtitles_order():
    """Subtitles must draw on top of the blur, not underneath it."""
    graph = build_filter_complex([FULL_WIDTH_BAND], W, H, "/tmp/vi.srt")
    assert graph.index("boxblur") < graph.index("subtitles")
    assert graph.endswith("[vout]")
    assert "null[vout]" not in graph


# --------------------------- logo overlay --------------------------- #

def test_build_filter_complex_with_logo_top_right():
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        logo_path="D:/assets/logo.png",
        logo_position="top_right",
        logo_scale=0.15,
        logo_opacity=0.8,
        logo_margin=30,
    )
    assert graph is not None
    assert "movie=" in graph
    assert "scale=288:-1" in graph
    assert "colorchannelmixer=aa=0.80" in graph
    assert "overlay=main_w-overlay_w-30:30" in graph
    assert graph.endswith("null[vout]")


def test_build_filter_complex_with_logo_bottom_left_and_subtitles():
    graph = build_filter_complex(
        blur_regions=[FULL_WIDTH_BAND],
        video_w=1920,
        video_h=1080,
        srt_path="/tmp/vi.srt",
        logo_path="D:/logo.png",
        logo_position="bottom_left",
        logo_scale=0.10,
        logo_opacity=0.9,
        logo_margin=20,
    )
    assert "boxblur" in graph
    assert "movie=" in graph
    assert "overlay=20:main_h-overlay_h-20" in graph
    assert "subtitles=" in graph
    # Thứ tự đúng: blur trước -> logo -> subtitles trên cùng
    assert graph.index("boxblur") < graph.index("movie=")
    assert graph.index("movie=") < graph.index("subtitles=")
    assert graph.endswith("[vout]")


# --------------------------- dynamic moving watermark --------------------------- #

def test_build_filter_complex_with_dynamic_bouncing_watermark():
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        watermark_text="@PhimHayMoiNgay",
        watermark_opacity=0.30,
        watermark_font_size=28,
        watermark_color="#FFFFFF",
        watermark_speed=45,
        watermark_motion="bounce",
    )
    assert graph is not None
    assert "drawtext=" in graph
    assert "@PhimHayMoiNgay" in graph
    assert "fontsize=28" in graph
    assert "fontcolor=FFFFFF@0.30" in graph
    assert "abs(mod(t*45" in graph
    assert graph.endswith("null[vout]")


def test_build_filter_complex_with_bouncing_logo():
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        logo_path="D:/logo.png",
        logo_motion="bounce",
        watermark_speed=50,
    )
    assert graph is not None
    assert "movie=" in graph
    assert "abs(mod(t*50" in graph
    assert graph.endswith("null[vout]")


# --------------------------- anti-content ID filters --------------------------- #

def test_build_filter_complex_with_smart_flip_and_subtitles():
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        srt_path="/tmp/vi.srt",
        smart_flip=True,
    )
    assert graph is not None
    assert "hflip" in graph
    assert "subtitles=" in graph
    # Thứ tự đúng: hflip trước -> subtitles sau cùng (để chữ không bị ngược)
    assert graph.index("hflip") < graph.index("subtitles=")
    assert graph.endswith("[vout]")


def test_build_filter_complex_with_micro_zoom_and_color_grading():
    graph = build_filter_complex(
        blur_regions=[],
        video_w=1920,
        video_h=1080,
        micro_zoom=True,
        color_filter="teal_orange",
    )
    assert graph is not None
    assert "scale=1.03*iw:1.03*ih" in graph
    assert "colorbalance=" in graph
    assert graph.index("scale=1.03") < graph.index("colorbalance=")
    assert graph.endswith("null[vout]")


def test_build_aspect_ratio_filter_reframe_modes():
    from autodub.media.subtitle import build_aspect_ratio_filter

    # 1. Blur mode 9:16
    res_blur = build_aspect_ratio_filter("tiktok_9_16", 1920, 1080, reframe_mode="blur")
    assert res_blur is not None
    flt_blur, tw, th = res_blur
    assert "boxblur" in flt_blur
    assert abs((tw / th) - (9.0 / 16.0)) < 0.02

    # 2. Top-Split mode 9:16
    res_top = build_aspect_ratio_filter("tiktok_9_16", 1920, 1080, reframe_mode="top_split")
    assert res_top is not None
    flt_top, tw_top, th_top = res_top
    assert "overlay=(W-w)/2:H*0.12" in flt_top
    assert abs((tw_top / th_top) - (9.0 / 16.0)) < 0.02

    # 3. Center Crop mode 9:16
    res_crop = build_aspect_ratio_filter("tiktok_9_16", 1920, 1080, reframe_mode="center_crop")
    assert res_crop is not None
    flt_crop, tw_crop, th_crop = res_crop
    assert "crop=" in flt_crop
    assert abs((tw_crop / th_crop) - (9.0 / 16.0)) < 0.02






