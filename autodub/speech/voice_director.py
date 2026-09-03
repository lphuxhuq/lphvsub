"""Smart Voice Director & Scoring Engine.

Đạo diễn lồng tiếng tự động: phân tích hồ sơ người nói (SpeakerProfile),
tính điểm tương thích (Compatibility Score) với kho giọng (UnifiedVoiceCatalog),
áp dụng phạt trùng lặp (Uniqueness Penalty) và tôn trọng lựa chọn thủ công (Manual Overrides).
"""
from __future__ import annotations

from autodub.speech.voice_catalog import UnifiedVoiceCatalog
from autodub.speech.voice_models import (
    CastingResult,
    SpeakerProfile,
    VoiceAssignment,
    VoiceProfile,
)
from autodub.utils import setup_logging

logger = setup_logging("autodub.voice_director")

# Trọng số chấm điểm tương thích
W_GENDER = 0.40
W_PITCH = 0.20
W_NARRATOR = 0.25
W_PROVIDER = 0.15
UNIQUENESS_PENALTY = 0.80


class VoiceDirector:
    """Động cơ phân vai và chấm điểm ghép giọng thông minh."""

    def __init__(self, catalog: UnifiedVoiceCatalog | None = None):
        self._catalog = catalog or UnifiedVoiceCatalog.create_default()

    def compute_score(
        self,
        speaker: SpeakerProfile,
        voice: VoiceProfile,
        preferred_provider: str | None = None,
        is_used: bool = False,
    ) -> float:
        """Tính điểm tương thích giữa một người nói và một giọng đọc (0.0 .. 1.0)."""
        # 1. Khớp giới tính
        if not speaker.gender or speaker.gender == "unknown" or not voice.gender:
            s_gender = 0.50
        elif speaker.gender == voice.gender:
            s_gender = 1.0
        else:
            s_gender = 0.0

        # 2. Khớp cao độ (Pitch Tag)
        s_pitch = 0.50
        if voice.pitch_tag:
            if speaker.gender == "male":
                if speaker.pitch_stats.pitch_median < 135.0 and voice.pitch_tag == "deep_male":
                    s_pitch = 1.0
                elif speaker.pitch_stats.pitch_median >= 135.0 and voice.pitch_tag == "young_male":
                    s_pitch = 1.0
                elif voice.gender == "male":
                    s_pitch = 0.80
            elif speaker.gender == "female":
                if voice.pitch_tag in ("female", "child_or_high"):
                    s_pitch = 1.0

        # 3. Khớp vai trò Dẫn chuyện
        if speaker.role == "narrator":
            s_narrator = voice.narrator_suitability
        else:
            s_narrator = 0.60

        # 4. Khớp provider ưa thích
        if preferred_provider:
            s_provider = 1.0 if voice.provider == preferred_provider else 0.50
        else:
            s_provider = 1.0

        # 5. Phạt trùng lặp (Uniqueness Penalty)
        penalty = UNIQUENESS_PENALTY if is_used else 0.0

        raw_score = (
            W_GENDER * s_gender
            + W_PITCH * s_pitch
            + W_NARRATOR * s_narrator
            + W_PROVIDER * s_provider
            - penalty
        )
        return float(max(0.0, min(1.0, raw_score)))

    def cast(
        self,
        profiles: dict[int, SpeakerProfile],
        current_voice: str | None = None,
        manual_overrides: dict[int, str] | None = None,
        auto_enabled: bool = True,
        provider_preference: str | None = None,
    ) -> CastingResult:
        """Thực hiện phân vai cho toàn bộ danh sách speaker."""
        default_voice = (current_voice or "nam_bac_1").strip()

        # Khi tính năng bị tắt (Toggle OFF) -> gán toàn bộ về default_voice
        if not auto_enabled or not profiles:
            assignments = {
                spk_id: VoiceAssignment(
                    speaker_id=spk_id,
                    voice_id=default_voice,
                    source="fallback",
                    score=1.0,
                    reason="Tự động phân vai bị tắt, sử dụng giọng mặc định",
                )
                for spk_id in profiles
            }
            return CastingResult(
                assignments=assignments,
                profiles=profiles,
                director_enabled=False,
            )

        all_voices = self._catalog.get_all_voices(provider=provider_preference)
        if not all_voices:
            # Fallback nếu catalog rỗng
            all_voices = self._catalog.get_all_voices()

        if not all_voices:
            # Nếu không có giọng nào khả dụng -> fallback
            assignments = {
                spk_id: VoiceAssignment(speaker_id=spk_id, voice_id=default_voice, source="fallback", score=1.0)
                for spk_id in profiles
            }
            return CastingResult(assignments=assignments, profiles=profiles, director_enabled=True)

        assigned: dict[int, VoiceAssignment] = {}
        used_voices: set[str] = set()

        # 1. Xử lý Manual Overrides trước
        manual_dict = manual_overrides or {}
        for spk_id, spk_prof in profiles.items():
            override_voice = manual_dict.get(spk_id, manual_dict.get(str(spk_id)))
            if override_voice and str(override_voice).strip():
                v_clean = str(override_voice).strip()
                assigned[spk_id] = VoiceAssignment(
                    speaker_id=spk_id,
                    voice_id=v_clean,
                    source="manual_override",
                    score=1.0,
                    reason="Người dùng chỉ định giọng thủ công",
                )
                used_voices.add(v_clean)

        # 2. Phân vai tự động cho các speaker còn lại (ưu tiên speaker thời lượng dài trước)
        unassigned_spks = [
            spk_id for spk_id in sorted(profiles.keys(), key=lambda k: profiles[k].total_duration_s, reverse=True)
            if spk_id not in assigned
        ]

        for spk_id in unassigned_spks:
            spk_prof = profiles[spk_id]

            best_voice: VoiceProfile | None = None
            best_score = -1.0

            for candidate in all_voices:
                is_used = candidate.voice_id in used_voices
                score = self.compute_score(
                    spk_prof, candidate, preferred_provider=provider_preference, is_used=is_used
                )
                if score > best_score:
                    best_score = score
                    best_voice = candidate

            if best_voice is None:
                best_voice = all_voices[0]
                best_score = 0.50

            assigned[spk_id] = VoiceAssignment(
                speaker_id=spk_id,
                voice_id=best_voice.voice_id,
                source="auto",
                score=round(best_score, 3),
                reason=f"AI phân vai: {spk_prof.gender} ({spk_prof.role})",
            )
            used_voices.add(best_voice.voice_id)

        logger.info(f"AI Voice Director hoàn thành phân vai cho {len(assigned)} người nói.")
        return CastingResult(assignments=assigned, profiles=profiles, director_enabled=True)


def cast_voices(
    profiles: dict[int, SpeakerProfile],
    catalog: UnifiedVoiceCatalog | None = None,
    current_voice: str | None = None,
    manual_overrides: dict[int, str] | None = None,
    auto_enabled: bool = True,
    provider_preference: str | None = None,
) -> CastingResult:
    """Hàm tiện ích thực hiện phân vai tự động."""
    director = VoiceDirector(catalog=catalog)
    return director.cast(
        profiles=profiles,
        current_voice=current_voice,
        manual_overrides=manual_overrides,
        auto_enabled=auto_enabled,
        provider_preference=provider_preference,
    )
