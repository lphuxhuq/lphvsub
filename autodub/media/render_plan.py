"""RenderPlan — DAG kiến trúc điều phối và sinh Filter Graph tối ưu cho FFmpeg export."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from autodub.media.blur_strategy import BlurMode, BlurStrategy
from autodub.media.encoder_profile import QualityMode
from autodub.media.output_profile import OutputProfile

logger = logging.getLogger(__name__)


@dataclass
class RenderPlan:
    """Kế hoạch dựng hình (Render Plan) hợp nhất toàn bộ pipeline."""

    video_w: int
    video_h: int
    output_profile: OutputProfile | None = None
    blur_mode: BlurMode = BlurMode.FAST
    quality_mode: QualityMode = QualityMode.FAST
    reframe_mode: str = "blur"
    banner_color: str = "#000000"
    banner_height_ratio: float = 0.16

    @classmethod
    def build(
        cls,
        video_w: int,
        video_h: int,
        aspect_preset: str | None = None,
        reframe_mode: str = "blur",
        quality_mode: str | QualityMode = QualityMode.FAST,
        blur_mode: str | BlurMode = BlurMode.FAST,
        banner_color: str = "#000000",
        banner_height_ratio: float = 0.16,
    ) -> RenderPlan:
        out_prof = OutputProfile.resolve(video_w, video_h, aspect_preset)
        bm = BlurMode(str(blur_mode).lower()) if not isinstance(blur_mode, BlurMode) else blur_mode
        qm = (
            QualityMode(str(quality_mode).lower())
            if not isinstance(quality_mode, QualityMode)
            else quality_mode
        )
        return cls(
            video_w=video_w,
            video_h=video_h,
            output_profile=out_prof,
            blur_mode=bm,
            quality_mode=qm,
            reframe_mode=reframe_mode,
            banner_color=banner_color,
            banner_height_ratio=banner_height_ratio,
        )

    def target_dimensions(self) -> tuple[int, int]:
        if self.output_profile:
            return self.output_profile.target_w, self.output_profile.target_h
        return self.video_w, self.video_h

    def build_reframe_filter(self) -> tuple[str, int, int] | None:
        if not self.output_profile:
            return None

        tw, th = self.output_profile.target_w, self.output_profile.target_h
        mode = (self.reframe_mode or "blur").strip().lower()
        is_banner = mode in ("banner", "solid_banner", "pad")

        curr_ratio = self.video_w / float(self.video_h)
        target_ratio = self.output_profile.aspect_ratio
        if abs(curr_ratio - target_ratio) < 0.02 and not is_banner:
            return None

        if is_banner:
            pad_col = (self.banner_color or "#000000").strip()
            if pad_col.startswith("#"):
                pad_col = "0x" + pad_col[1:]
            min_bar_h = int(th * self.banner_height_ratio)
            scale_limit_h = int(th * max(0.20, (1.0 - 2 * self.banner_height_ratio)))
            scaled_h = round(tw * float(self.video_h) / float(self.video_w))
            if (th - scaled_h) / 2 < min_bar_h:
                flt = f"scale={tw}:{scale_limit_h}:force_original_aspect_ratio=decrease,pad={tw}:{th}:trunc((ow-iw)/4)*2:trunc((oh-ih)/4)*2:color={pad_col}"
            else:
                flt = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:trunc((ow-iw)/4)*2:trunc((oh-ih)/4)*2:color={pad_col}"

        elif mode in ("center_crop", "crop", "fill"):
            flt = f"scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th}"

        elif mode in ("top_split", "top", "split"):
            bg_flt = BlurStrategy.build_background_filter(
                tw,
                th,
                mode=self.blur_mode,
                brightness=-0.12,
                saturation=1.2,
                in_tag="asp_bg",
                out_tag="asp_bgb",
            )
            flt = (
                f"split[asp_bg][asp_fg];"
                f"{bg_flt};"
                f"[asp_fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[asp_fg_s];"
                f"[asp_bgb][asp_fg_s]overlay=(W-w)/2:H*0.12"
            )
        else:  # blur (default)
            bg_flt = BlurStrategy.build_background_filter(
                tw,
                th,
                mode=self.blur_mode,
                brightness=-0.08,
                saturation=1.15,
                in_tag="asp_bg",
                out_tag="asp_bgb",
            )
            flt = (
                f"split[asp_bg][asp_fg];"
                f"{bg_flt};"
                f"[asp_fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[asp_fg_s];"
                f"[asp_bgb][asp_fg_s]overlay=trunc((W-w)/4)*2:trunc((H-h)/4)*2"
            )

        return flt, tw, th
