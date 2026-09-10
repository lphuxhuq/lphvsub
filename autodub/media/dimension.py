"""Centralized video dimension normalization module for LPH VSub / VoxDub.

Guarantees:
- Even width and even height (divisible by 2) for all re-encoded video streams.
- Aspect ratio of source content is preserved without unexpected crop or stretch.
- 100% compatible with YUV420p encoders (libx264, h264_nvenc, hevc_nvenc, QSV, AMF).
- Handles arbitrary portrait, landscape, and square video inputs.
"""
from __future__ import annotations


def make_even(dimension: int) -> int:
    """Round up an integer dimension to the nearest even number.
    
    Examples:
        make_even(1080) -> 1080
        make_even(1079) -> 1080
        make_even(721)  -> 722
        make_even(0)    -> 0
    """
    dim = int(dimension)
    return dim + (dim % 2)


def is_even_dimension(width: int, height: int) -> bool:
    """Return True if both width and height are divisible by 2."""
    return width % 2 == 0 and height % 2 == 0


def normalize_dimensions(width: int, height: int) -> tuple[int, int]:
    """Return (even_width, even_height) by rounding up odd values by 1 pixel."""
    return make_even(width), make_even(height)


def build_dimension_filter() -> str:
    """Generate an FFmpeg filter expression that pads width/height to even dimensions.
    
    Using `pad=ceil(iw/2)*2:ceil(ih/2)*2` ensures:
    - If already even (e.g. 1920x1080), ceil(1920/2)*2 == 1920 -> zero extra padding (no-op).
    - If odd (e.g. 1079x1920 or 721x1281), adds 1 pixel pad at the edge -> strictly even.
    - Content is never cropped, blurred, or stretched.
    """
    return "pad=ceil(iw/2)*2:ceil(ih/2)*2"


def build_even_scale_filter(height: int) -> str:
    """Generate an FFmpeg scale filter expression that caps height and ensures both dimensions are even."""
    return f"scale=-2:'trunc(min({int(height)},ih)/2)*2'"
