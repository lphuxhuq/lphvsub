"""Unified Voice Catalog & Providers cho VieNeu và CapCut TTS.

Cung cấp interface trừu tượng VoiceProvider để phân loại và truy vấn giọng đọc
thống nhất, phục vụ cho AI Voice Director.
"""
from __future__ import annotations

from typing import Protocol
from autodub.config import Settings
from autodub.speech.voice_models import VoiceProfile
from autodub.utils import setup_logging

logger = setup_logging("autodub.voice_catalog")


class VoiceProvider(Protocol):
    """Protocol trừu tượng cho một nhà cung cấp giọng đọc (TTS Provider)."""

    def get_voices(self) -> list[VoiceProfile]:
        """Trả về danh sách VoiceProfile của provider này."""
        ...

    def is_available(self) -> bool:
        """Kiểm tra provider có sẵn sàng hoạt động hay không."""
        ...


class VieNeuVoiceProvider:
    """Provider cho kho giọng VieNeu TTS (offline)."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()

    def is_available(self) -> bool:
        return self._settings.vieneu_configured()

    def get_voices(self) -> list[VoiceProfile]:
        from autodub.speech.tts import voices as catalog_module

        try:
            raw_voices = catalog_module.catalog(self._settings)
        except Exception as e:
            logger.warning(f"Không nạp được danh mục VieNeu: {e}")
            return []

        out: list[VoiceProfile] = []
        for v in raw_voices:
            if v.is_capcut:
                continue
            # Đánh giá độ phù hợp làm narrator dựa trên phong cách
            narrator_score = 0.90 if v.style in ("tin_tuc", "doc_truyen") else 0.70
            pitch_tag = "deep_male" if v.gender == "male" else ("female" if v.gender == "female" else "")

            out.append(VoiceProfile(
                voice_id=v.name,
                name=v.name,
                provider="vieneu",
                gender=v.gender,
                region=v.region,
                style=v.style,
                narrator_suitability=narrator_score,
                pitch_tag=pitch_tag,
            ))
        return out


class CapCutVoiceProvider:
    """Provider cho kho giọng CapCut TTS (online API)."""

    def __init__(self, settings: Settings | None = None):
        self._settings = settings or Settings()

    def is_available(self) -> bool:
        return True  # CapCut gọi qua API

    def get_voices(self) -> list[VoiceProfile]:
        from autodub.speech.tts import voices as catalog_module

        try:
            raw_voices = catalog_module.catalog(self._settings)
        except Exception as e:
            logger.warning(f"Không nạp được danh mục CapCut: {e}")
            return []

        out: list[VoiceProfile] = []
        for v in raw_voices:
            if not v.is_capcut:
                continue
            pitch_tag = "young_male" if v.gender == "male" else ("female" if v.gender == "female" else "")
            out.append(VoiceProfile(
                voice_id=v.name,
                name=v.name,
                provider="capcut",
                gender=v.gender,
                region=v.region,
                style=v.style,
                narrator_suitability=0.80,
                pitch_tag=pitch_tag,
            ))
        return out


class UnifiedVoiceCatalog:
    """Kho danh mục giọng đọc hợp nhất toàn hệ thống."""

    def __init__(self, providers: dict[str, VoiceProvider] | None = None):
        self._providers = providers or {}

    @classmethod
    def create_default(cls, settings: Settings | None = None) -> "UnifiedVoiceCatalog":
        cfg = settings or Settings()
        return cls(providers={
            "vieneu": VieNeuVoiceProvider(cfg),
            "capcut": CapCutVoiceProvider(cfg),
        })

    def get_all_voices(self, provider: str | None = None) -> list[VoiceProfile]:
        """Lấy tất cả giọng khả dụng (có thể lọc theo provider)."""
        if provider:
            p = self._providers.get(provider)
            return p.get_voices() if p else []

        all_v: list[VoiceProfile] = []
        for p in self._providers.values():
            all_v.extend(p.get_voices())
        return all_v

    def get_voice_by_id(self, voice_id: str) -> VoiceProfile | None:
        """Tìm VoiceProfile theo voice_id."""
        clean_id = (voice_id or "").strip()
        for v in self.get_all_voices():
            if v.voice_id == clean_id or v.name == clean_id:
                return v
        return None

    def find_matching_voices(
        self,
        gender: str | None = None,
        provider: str | None = None,
        style: str | None = None,
    ) -> list[VoiceProfile]:
        """Tìm các giọng khớp tiêu chí giới tính, provider hoặc phong cách."""
        candidates = self.get_all_voices(provider=provider)
        results = []
        for v in candidates:
            if gender and v.gender and v.gender != gender:
                continue
            if style and v.style and v.style != style:
                continue
            results.append(v)
        return results
