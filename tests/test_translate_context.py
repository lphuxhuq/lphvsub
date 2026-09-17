"""Unit tests for Phase 0 video context analysis and 11 translation style presets."""

import json
from unittest.mock import MagicMock, patch

from autodub.config import Settings
from autodub.languages import get_target
from autodub.text.translate_browser import _build_browser_system_prompt
from autodub.text.translate_context import (
    analyze_transcript_context,
    apply_analysis,
    sample_transcript,
)
from autodub.text.translate_direct import _build_system_prompt
from autodub.text.translate_styles import (
    STYLE_PROMPTS,
    TRANSLATE_STYLE_DEFINITIONS,
    get_style_note,
    get_style_prompt,
)


def test_eleven_style_prompts_complete() -> None:
    """Tất cả 11 phong cách đều có định nghĩa và prompt hướng dẫn chi tiết."""
    assert len(TRANSLATE_STYLE_DEFINITIONS) == 11
    assert len(STYLE_PROMPTS) == 11
    for _label, key, note in TRANSLATE_STYLE_DEFINITIONS:
        prompt = get_style_prompt(key)
        assert prompt.strip()
        assert "### PHONG CÁCH:" in prompt
        assert note == get_style_note(key)


def test_style_prompt_fallback_to_natural() -> None:
    """Phong cách lạ hoặc rỗng thì fallback về 'natural'."""
    assert get_style_prompt("") == STYLE_PROMPTS["natural"]
    assert get_style_prompt("unknown_xyz") == STYLE_PROMPTS["natural"]


def test_sample_transcript_sampling_logic() -> None:
    """Lấy mẫu thông minh từ transcript: đầu, giữa, cuối."""
    assert sample_transcript([]) == []

    # Dưới 120 dòng: giữ nguyên toàn bộ
    segs_short = [{"text": f"Dòng {i}"} for i in range(50)]
    sampled_short = sample_transcript(segs_short, max_lines=120)
    assert len(sampled_short) == 50

    # Trên 120 dòng: trích xuất đầu, giữa, cuối
    segs_long = [{"text": f"Dòng {i}"} for i in range(300)]
    sampled_long = sample_transcript(segs_long, max_lines=120)
    assert len(sampled_long) <= 125
    assert "Dòng 0" in sampled_long
    assert "Dòng 299" in sampled_long
    assert any("đoạn giữa" in str(x) for x in sampled_long)


def test_apply_analysis_preserves_user_overrides() -> None:
    """Người dùng điền tay trường nào thì ưu tiên giữ nguyên trường đó."""
    base = Settings(
        translate_domain="Phim Khoa Học",
        translate_pronouns="Tôi - Quý vị",
    )
    analysis = {
        "domain": "Game Chiến Thuật",
        "summary": "Tóm tắt cốt truyện AI",
        "characters": "Nhân vật A, B",
        "pronouns": "Cậu - Tớ",
        "glossary": ["Term1 -> Nghĩa 1", "Term2 -> Nghĩa 2"],
        "style_notes": "Nhịp điệu dồn dập",
    }
    updated = apply_analysis(base, analysis)
    assert updated.translate_domain == "Phim Khoa Học"
    assert updated.translate_pronouns == "Tôi - Quý vị"
    assert "Tóm tắt cốt truyện AI" in updated.translate_context
    assert "Nhân vật A, B" in updated.translate_context
    assert "Term1 -> Nghĩa 1" in updated.translate_glossary
    assert updated.translate_style_notes == "Nhịp điệu dồn dập"


def test_analyze_transcript_uses_cache(tmp_path) -> None:
    """Nếu cache video_context.json đã tồn tại và hợp lệ, dùng lại không gọi AI."""
    cache_file = tmp_path / "video_context.json"
    cached_data = {
        "domain": "Review phim",
        "summary": "Tóm tắt phim kinh dị",
        "characters": "Kẻ sát nhân, cô gái",
        "pronouns": "Anh chàng - Cô gái",
        "glossary": ["Killer -> Kẻ sát nhân"],
        "style_notes": "Kịch tính, hồi hộp",
    }
    cache_file.write_text(json.dumps(cached_data, ensure_ascii=False), encoding="utf-8")

    settings = Settings(gemini_api_key="mock_key")
    result = analyze_transcript_context(
        segments=[{"text": "Hello"}],
        source_lang="zh",
        settings=settings,
        cache_path=str(cache_file),
    )
    assert result == cached_data


@patch("autodub.text.translate_direct.GeminiDirectClient")
def test_analyze_transcript_calls_gemini_and_saves_cache(mock_client_cls, tmp_path) -> None:
    """Gọi Gemini Direct phân tích và ghi cache video_context.json."""
    mock_instance = MagicMock()
    mock_instance.call_ai.return_value = json.dumps(
        {
            "domain": "Cổ trang tiên hiệp",
            "summary": "Tu chân phi thăng",
            "characters": "Sư phụ, Đồ nhi",
            "pronouns": "Sư phụ - Đồ nhi",
            "glossary": ["Trúc Cơ -> Trúc Cơ"],
            "style_notes": "Âm hưởng Hán Việt",
        }
    )
    mock_client_cls.return_value = mock_instance

    cache_file = tmp_path / "video_context.json"
    settings = Settings(gemini_api_key="AIzaTestKey123")
    result = analyze_transcript_context(
        segments=[{"text": "Ta muốn bái sư."}],
        source_lang="zh-CN",
        settings=settings,
        video_title="Tiêu Đề Phim Tu Chân",
        cache_path=str(cache_file),
    )

    assert result is not None
    assert result["domain"] == "Cổ trang tiên hiệp"
    assert cache_file.exists()
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["domain"] == "Cổ trang tiên hiệp"


def test_build_system_prompt_injects_style_prompt() -> None:
    """Direct API system prompt chứa hướng dẫn phong cách đã chọn."""
    settings_movie = Settings(translate_style="movie_review")
    prompt_movie = _build_system_prompt(settings=settings_movie)
    assert "REVIEW PHIM" in prompt_movie

    settings_wuxia = Settings(translate_style="wuxia")
    prompt_wuxia = _build_system_prompt(settings=settings_wuxia)
    assert "CỔ TRANG" in prompt_wuxia
    assert "tại hạ" in prompt_wuxia


def test_build_browser_system_prompt_injects_style_and_context() -> None:
    """AI Studio Browser system prompt chứa hướng dẫn phong cách và ngữ cảnh video."""
    target = get_target("vi")
    settings = Settings(
        translate_style="anime_manga",
        translate_video_title="One Piece Tập Mới",
        translate_pronouns="Cậu - Tớ",
    )
    prompt = _build_browser_system_prompt(target, "ja", settings=settings)
    assert "ANIME / MANGA" in prompt
    assert "One Piece Tập Mới" in prompt
    assert "Cậu - Tớ" in prompt
