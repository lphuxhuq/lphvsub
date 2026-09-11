"""Chiến lược làm mờ nền thích ứng (Adaptive Blur Strategy) cho LPHVSub."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BlurMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"


@dataclass(frozen=True)
class BlurSpec:
    """Đặc tả thông số làm mờ nền dạng Downscale Pyramid."""

    low_w: int
    low_h: int
    boxblur_radius: int
    boxblur_power: int
    upscale_flags: str


class BlurStrategy:
    """Sinh bộ lọc làm mờ nền thích ứng dựa trên resolution và chế độ chất lượng."""

    @staticmethod
    def get_spec(target_w: int, target_h: int, mode: BlurMode | str = BlurMode.FAST) -> BlurSpec:
        if isinstance(mode, BlurMode):
            m = mode
        else:
            val = str(mode).strip().lower()
            if val.startswith("blurmode."):
                val = val.split(".", 1)[1]
            try:
                m = BlurMode(val)
            except ValueError:
                m = BlurMode.FAST
        if m == BlurMode.FAST:
            # Thu nhỏ 6 lần: giảm 36x số pixel tính toán
            div = 6
            r, p = 4, 1
            flags = "bilinear"
        elif m == BlurMode.BALANCED:
            # Thu nhỏ 4 lần: giảm 16x số pixel tính toán
            div = 4
            r, p = 6, 2
            flags = "bicubic"
        else:  # QUALITY
            # Thu nhỏ 2 lần: giảm 4x số pixel
            div = 2
            r, p = 10, 2
            flags = "lanczos"

        low_w = max(16, (target_w // div) + ((target_w // div) % 2))
        low_h = max(16, (target_h // div) + ((target_h // div) % 2))
        return BlurSpec(
            low_w=low_w,
            low_h=low_h,
            boxblur_radius=r,
            boxblur_power=p,
            upscale_flags=flags,
        )

    @classmethod
    def build_background_filter(
        cls,
        target_w: int,
        target_h: int,
        mode: BlurMode | str = BlurMode.FAST,
        brightness: float = -0.08,
        saturation: float = 1.15,
        in_tag: str = "asp_bg",
        out_tag: str = "asp_bgb",
    ) -> str:
        """Tạo chuỗi filter FFmpeg hoàn chỉnh cho lớp nền mờ nghệ thuật."""
        spec = cls.get_spec(target_w, target_h, mode=mode)
        return (
            f"[{in_tag}]scale={spec.low_w}:{spec.low_h}:force_original_aspect_ratio=increase,"
            f"crop={spec.low_w}:{spec.low_h},"
            f"boxblur={spec.boxblur_radius}:{spec.boxblur_power},"
            f"scale={target_w}:{target_h}:flags={spec.upscale_flags},"
            f"eq=brightness={brightness:.2f}:saturation={saturation:.2f}[{out_tag}]"
        )
