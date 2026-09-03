"""Data models cho AI Multi-Speaker Smart Voice Director.

Chứa các dataclass bất biến và mô hình dữ liệu trung chuyển:
- PitchStats: Thống kê cao độ F0 (median, p10, p90, std, voiced_ratio, confidence).
- SpeakerProfile: Hồ sơ người nói (giới tính xác suất, vai trò, thời lượng).
- VoiceProfile: Hồ sơ giọng đọc từ kho VieNeu hoặc CapCut.
- VoiceAssignment: Kết quả gán giọng (auto, manual_override, fallback).
- CastingResult: Kết quả phân vai toàn bộ dự án.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PitchStats:
    """Thống kê cao độ F0 và độ tin cậy âm học của một người nói."""
    pitch_median: float          # Cao độ trung vị (Hz)
    pitch_p10: float             # Phân vị 10% (Hz)
    pitch_p90: float             # Phân vị 90% (Hz)
    pitch_std: float             # Độ lệch chuẩn cao độ (Hz)
    voiced_ratio: float          # Tỷ lệ frame có tiếng / tổng frame (0.0 .. 1.0)
    confidence: float            # Độ tin cậy của ước lượng F0 (0.0 .. 1.0)


@dataclass
class SpeakerProfile:
    """Hồ sơ âm học và cấu trúc của một người nói (Speaker)."""
    speaker_id: int
    gender: str                  # "male" | "female" | "unknown"
    gender_confidence: float     # 0.0 .. 1.0
    pitch_stats: PitchStats
    role: str                    # "narrator" | "character" | "unknown"
    role_confidence: float       # 0.0 .. 1.0
    total_duration_s: float      # Tổng thời lượng nói (giây)
    segment_count: int           # Tổng số câu thoại
    timeline_coverage: float     # Độ bao phủ timeline (0.0 .. 1.0)
    avg_segment_duration_s: float  # Thời lượng trung bình mỗi câu (giây)


@dataclass(frozen=True)
class VoiceProfile:
    """Hồ sơ một giọng đọc khả dụng từ kho giọng (VieNeu / CapCut)."""
    voice_id: str                # Mã định danh giọng
    name: str                    # Tên hiển thị
    provider: str                # "vieneu" | "capcut"
    gender: str = ""             # "male" | "female" | ""
    region: str = ""             # "bac" | "trung" | "nam" | ""
    style: str = "tu_nhien"      # "tu_nhien" | "tin_tuc" | "doc_truyen"
    narrator_suitability: float = 0.5  # Độ phù hợp làm người dẫn chuyện (0.0 .. 1.0)
    pitch_tag: str = ""          # "deep_male" | "young_male" | "female" | "child_or_high" | ""


@dataclass
class VoiceAssignment:
    """Kết quả phân bổ giọng cho một người nói."""
    speaker_id: int
    voice_id: str
    source: str = "auto"         # "auto" | "manual_override" | "fallback"
    score: float = 1.0           # Điểm tương thích (0.0 .. 1.0)
    reason: str = ""             # Giải thích lý do phân vai


@dataclass
class CastingResult:
    """Kết quả phân vai toàn bộ dự án lồng tiếng."""
    assignments: dict[int, VoiceAssignment] = field(default_factory=dict)
    profiles: dict[int, SpeakerProfile] = field(default_factory=dict)
    director_enabled: bool = True
