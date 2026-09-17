"""Kiểm thử sáu phong cách dịch.

Phong cách được truyền vào lõi xử lý bằng cách nối thêm ghi chú vào phần
hướng dẫn dịch mà lõi đã đọc sẵn, nên không phải sửa gì trong lõi.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from autodub.config import Settings
from autodub_gui.dub_constants import TRANSLATE_STYLES, style_note


def _apply(settings: Settings, key: str) -> Settings:
    """Ghép ghi chú phong cách vào cấu hình, đúng như trang Tạo dự án làm."""
    note = style_note(key)
    if not note:
        return settings
    merged = (settings.translate_style_notes + "\n" + note).strip()
    return replace(settings, translate_style_notes=merged)


def test_eleven_styles_available() -> None:
    assert len(TRANSLATE_STYLES) == 11


def test_style_keys_are_unique() -> None:
    keys = [key for _label, key, _note in TRANSLATE_STYLES]
    assert len(set(keys)) == len(keys)


def test_natural_adds_nothing() -> None:
    """Phong cách mặc định phải giữ nguyên hướng dẫn dịch của người dùng."""
    assert style_note("natural") == ""


def test_unknown_key_adds_nothing() -> None:
    assert style_note("khong_ton_tai") == ""


@pytest.mark.parametrize(
    "key",
    [
        "movie_review",
        "wuxia",
        "anime_manga",
        "humorous",
        "social",
        "formal",
        "commercial",
        "tech_documentary",
        "creative",
        "literal",
    ],
)
def test_each_style_has_a_note(key: str) -> None:
    assert style_note(key).strip()


def test_all_labels_and_notes_are_vietnamese() -> None:
    """Nhãn và ghi chú đều phải viết tiếng Việt có dấu."""
    marks = "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
    for label, key, note in TRANSLATE_STYLES:
        assert any(ch in marks for ch in label.lower()), label
        if key != "natural":
            assert any(ch in marks for ch in note.lower()), key


def test_note_is_appended_to_existing_instructions() -> None:
    """Ghi chú của người dùng không bị mất khi chọn phong cách."""
    base = Settings(translate_style_notes="Giữ tên nhân vật Hán Việt.")
    merged = _apply(base, "formal")
    assert "Giữ tên nhân vật Hán Việt." in merged.translate_style_notes
    assert style_note("formal") in merged.translate_style_notes


def test_natural_leaves_settings_untouched() -> None:
    base = Settings(translate_style_notes="Ghi chú riêng.")
    assert _apply(base, "natural").translate_style_notes == "Ghi chú riêng."


def test_applying_style_to_empty_notes_has_no_leading_newline() -> None:
    merged = _apply(Settings(translate_style_notes=""), "social")
    assert merged.translate_style_notes == style_note("social")


def test_core_reads_style_notes_in_prompt() -> None:
    """Lõi dựng câu lệnh dịch phải thực sự dùng tới phần ghi chú này."""
    from autodub.languages import get_target
    from autodub.text import translate_hint

    settings = _apply(Settings(), "humorous")
    prompt = translate_hint.build_translation_prompt(get_target("vi"), "zh-CN", settings=settings)
    assert style_note("humorous") in prompt


def test_settings_fields_has_translate_style() -> None:
    """Trang Dịch thuật (Cài đặt / Tool Page) có trường TRANSLATE_STYLE với 11 phong cách."""
    from autodub_gui.pages import settings_fields as spec

    field = next((f for f in spec.FIELDS if f.key == "TRANSLATE_STYLE"), None)
    assert field is not None
    assert field.tab == spec.TAB_TRANSLATE
    assert field.kind == spec.COMBO
    assert len(field.options) == 11


def test_apply_analysis_updates_translate_style() -> None:
    """apply_analysis cập nhật translate_style từ video_context.json vào settings."""
    from autodub.text.translate_context import apply_analysis

    base = Settings(translate_style="natural")
    updated = apply_analysis(base, {"translate_style": "cinematic"})
    assert updated.translate_style == "cinematic"


def test_editor_panels_context_handles_translate_style(qapp) -> None:
    """OverviewPanel trong Editor đọc và phát ra đúng translate_style."""
    from autodub_gui.pages.editor_panels import OverviewPanel

    panel = OverviewPanel()
    panel.set_context({"translate_style": "movie_review", "summary": "Video review phim gay cấn"})

    emitted_data = {}
    panel.context_saved.connect(lambda d: emitted_data.update(d))
    panel._emit_context()

    assert emitted_data["translate_style"] == "movie_review"
    assert emitted_data["summary"] == "Video review phim gay cấn"
