"""Output profile và chuẩn hóa resolution cho video export trong LPHVSub."""
from __future__ import annotations

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Ngưỡng pixel mặc định: Full-HD (1920x1080 hoặc 1080x1920 = 2,073,600 px)
DEFAULT_MAX_PIXELS = 2_073_600


@dataclass(frozen=True)
class OutputProfile:
    """Hồ sơ định dạng và kích thước khung hình xuất video."""
    aspect_preset: str
    target_w: int
    target_h: int
    pixel_budget: int = DEFAULT_MAX_PIXELS

    @property
    def aspect_ratio(self) -> float:
        return self.target_w / float(self.target_h)

    @classmethod
    def resolve(
        cls,
        video_w: int,
        video_h: int,
        aspect_preset: str | None,
        custom_w: int | None = None,
        custom_h: int | None = None,
        max_pixels: int = DEFAULT_MAX_PIXELS,
    ) -> OutputProfile | None:
        """Tính toán kích thước canvas xuất ra chuẩn hóa, tránh phình bất thường."""
        if not aspect_preset or str(aspect_preset).strip().lower() in ("original", "none", ""):
            return None

        preset = str(aspect_preset).strip().lower()
        if preset in ("tiktok_9_16", "9:16", "vertical", "shorts"):
            target_ratio = 9.0 / 16.0
        elif preset in ("youtube_16_9", "16:9", "horizontal"):
            target_ratio = 16.0 / 9.0
        elif preset in ("square_1_1", "1:1", "square"):
            target_ratio = 1.0
        elif preset == "custom" and custom_w and custom_h:
            cw = int(custom_w) + (int(custom_w) % 2)
            ch = int(custom_h) + (int(custom_h) % 2)
            return cls(aspect_preset="custom", target_w=cw, target_h=ch, pixel_budget=max_pixels)
        else:
            return None

        # Tính toán theo tỷ lệ chuẩn và budget
        if target_ratio < 1.0:  # 9:16
            if video_h >= video_w:
                th = min(1920, video_h)
                th = th + (th % 2)
                tw = int(round(th * target_ratio))
                tw = tw + (tw % 2)
            else:
                tw = min(1080, max(720, video_h))
                tw = tw + (tw % 2)
                th = int(round(tw / target_ratio))
                th = th + (th % 2)
        elif target_ratio > 1.0:  # 16:9
            if video_w >= video_h:
                tw = min(1920, video_w)
                tw = tw + (tw % 2)
                th = int(round(tw / target_ratio))
                th = th + (th % 2)
            else:
                th = min(1080, max(720, video_w))
                th = th + (th % 2)
                tw = int(round(th * target_ratio))
                tw = tw + (tw % 2)
        else:  # 1:1
            dim = min(1080, max(video_w, video_h))
            dim = dim + (dim % 2)
            tw = th = dim

        # Kiểm tra và bảo vệ pixel budget
        if tw * th > max_pixels:
            scale = (max_pixels / float(tw * th)) ** 0.5
            tw = int(tw * scale)
            tw = tw - (tw % 2)
            th = int(round(tw / target_ratio))
            th = th + (th % 2)
            while tw * th > max_pixels and tw > 16:
                tw -= 2
                th = int(round(tw / target_ratio))
                th = th + (th % 2)

        return cls(aspect_preset=preset, target_w=tw, target_h=th, pixel_budget=max_pixels)
