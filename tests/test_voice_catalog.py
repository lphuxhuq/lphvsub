import pytest
from unittest.mock import MagicMock, patch

from autodub.config import Settings
from autodub.speech.voice_catalog import (
    VieNeuVoiceProvider,
    CapCutVoiceProvider,
    UnifiedVoiceCatalog,
)
from autodub.speech.voice_models import VoiceProfile


def test_unified_voice_catalog_mock_providers():
    mock_vieneu_voices = [
        VoiceProfile(voice_id="nam_bac_1", name="Nam Bắc 1", provider="vieneu", gender="male", region="bac", style="tin_tuc", narrator_suitability=0.9, pitch_tag="deep_male"),
        VoiceProfile(voice_id="nu_bac_1", name="Nữ Bắc 1", provider="vieneu", gender="female", region="bac", style="tu_nhien", narrator_suitability=0.7, pitch_tag="female"),
    ]
    mock_capcut_voices = [
        VoiceProfile(voice_id="capcut_male_1", name="CapCut Nam 1", provider="capcut", gender="male", region="bac", style="tu_nhien", narrator_suitability=0.8, pitch_tag="young_male"),
        VoiceProfile(voice_id="capcut_female_1", name="CapCut Nữ 1", provider="capcut", gender="female", region="nam", style="tu_nhien", narrator_suitability=0.75, pitch_tag="female"),
    ]

    p_vieneu = MagicMock()
    p_vieneu.get_voices.return_value = mock_vieneu_voices
    p_vieneu.is_available.return_value = True

    p_capcut = MagicMock()
    p_capcut.get_voices.return_value = mock_capcut_voices
    p_capcut.is_available.return_value = True

    catalog = UnifiedVoiceCatalog(providers={"vieneu": p_vieneu, "capcut": p_capcut})

    all_voices = catalog.get_all_voices()
    assert len(all_voices) == 4

    # Lọc theo provider
    vieneu_only = catalog.get_all_voices(provider="vieneu")
    assert len(vieneu_only) == 2
    assert all(v.provider == "vieneu" for v in vieneu_only)

    # Lọc theo giới tính
    females = catalog.find_matching_voices(gender="female")
    assert len(females) == 2
    assert all(v.gender == "female" for v in females)

    # Tìm theo voice_id
    v = catalog.get_voice_by_id("capcut_male_1")
    assert v is not None
    assert v.name == "CapCut Nam 1"


def test_vieneu_and_capcut_real_providers_smoke():
    settings = Settings()
    catalog = UnifiedVoiceCatalog.create_default(settings)
    voices = catalog.get_all_voices()
    # Smoke test: kho giọng hợp nhất lấy được danh sách (ít nhất có giọng VieNeu hoặc CapCut)
    assert isinstance(voices, list)
