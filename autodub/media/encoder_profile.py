"""Hồ sơ mã hóa phần cứng và phần mềm (Encoder Profile) cho LPHVSub."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class QualityMode(str, Enum):
    FAST = "fast"
    BALANCED = "balanced"
    QUALITY = "quality"


@dataclass(frozen=True)
class EncoderConfig:
    name: str
    codec_args: tuple[str, ...]


class EncoderProfile:
    """Xác định tham số encoder tối ưu theo phần cứng và hồ sơ chất lượng."""

    @classmethod
    def get_args(cls, encoder_name: str, mode: QualityMode | str = QualityMode.FAST) -> list[str]:
        if isinstance(mode, QualityMode):
            m = mode
        else:
            val = str(mode).strip().lower()
            if val.startswith("qualitymode."):
                val = val.split(".", 1)[1]
            try:
                m = QualityMode(val)
            except ValueError:
                m = QualityMode.FAST

        enc = str(encoder_name).strip()
        if "NVIDIA" in enc or "nvenc" in enc.lower():
            if m == QualityMode.FAST:
                return ["-c:v", "h264_nvenc", "-preset", "p1", "-cq", "23", "-b:v", "0", "-multipass", "0"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "h264_nvenc", "-preset", "p2", "-cq", "22", "-b:v", "0", "-multipass", "0"]
            else:  # QUALITY
                return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", "-b:v", "0", "-multipass", "1"]

        elif "Intel" in enc or "qsv" in enc.lower():
            if m == QualityMode.FAST:
                return ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "23"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "22"]
            else:
                return ["-c:v", "h264_qsv", "-preset", "medium", "-global_quality", "20"]

        elif "Apple" in enc or "videotoolbox" in enc.lower():
            if m == QualityMode.FAST:
                return ["-c:v", "h264_videotoolbox", "-q:v", "65"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "h264_videotoolbox", "-q:v", "55"]
            else:
                return ["-c:v", "h264_videotoolbox", "-q:v", "45"]

        elif "vaapi" in enc.lower():
            if m == QualityMode.FAST:
                return ["-c:v", "h264_vaapi", "-qp", "24"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "h264_vaapi", "-qp", "22"]
            else:
                return ["-c:v", "h264_vaapi", "-qp", "20"]

        elif "AMD" in enc or "amf" in enc.lower():
            if m == QualityMode.FAST:
                return ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "23", "-qp_p", "23"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "cqp", "-qp_i", "22", "-qp_p", "22"]
            else:
                return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "20", "-qp_p", "20"]


        else:  # CPU libx264
            if m == QualityMode.FAST:
                return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
            elif m == QualityMode.BALANCED:
                return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"]
            else:
                return ["-c:v", "libx264", "-preset", "fast", "-crf", "20"]
