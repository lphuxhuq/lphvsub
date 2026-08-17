import os
import pytest
from autodub.text.glossary import (
    apply_glossary,
    apply_glossary_to_segments,
    batch_replace_segments,
    load_glossary_file,
    save_glossary_file,
)


def test_apply_glossary_single_and_multiple():
    glossary = {
        "Hạ công tử": "Công tử Hạ",
        "tiên dược": "thần dược",
        "Đại Minh": "triều Đại Minh",
    }
    text = "Đa tạ Hạ công tử ban tiên dược cứu người ở Đại Minh!"
    result = apply_glossary(text, glossary)
    assert result == "Đa tạ Công tử Hạ ban thần dược cứu người ở triều Đại Minh!"


def test_apply_glossary_order_preference():
    """Cụm từ dài hơn phải được thay thế trước cụm từ ngắn hơn."""
    glossary = {
        "Hạ công tử": "Công tử Hạ",
        "Hạ": "Mùa Hè",
    }
    text = "Hạ công tử đến vào mùa Hạ."
    result = apply_glossary(text, glossary)
    assert result == "Công tử Hạ đến vào mùa Mùa Hè."


def test_apply_glossary_to_segments():
    segments = [
        {"id": 1, "text_vi": "Chào Hạ công tử."},
        {"id": 2, "text_vi": "Hôm nay trời rất đẹp."},
    ]
    glossary = {"Hạ công tử": "Tiên sinh họ Hạ"}
    updated, changed_count = apply_glossary_to_segments(segments, glossary)
    assert changed_count == 1
    assert updated[0]["text_vi"] == "Chào Tiên sinh họ Hạ."
    assert updated[1]["text_vi"] == "Hôm nay trời rất đẹp."


def test_batch_replace_segments_case_and_word_boundary():
    segments = [
        {"id": 1, "text_vi": "Con trâu này là Trâu Vương."},
        {"id": 2, "text_vi": "Đây là con trâu con."},
    ]
    # Toàn bộ từ 'trâu' -> 'bò' (không phân biệt hoa thường)
    updated, changed = batch_replace_segments(
        segments, "trâu", "bò", case_sensitive=False, whole_word=True
    )
    assert changed == 2
    assert updated[0]["text_vi"] == "Con bò này là bò Vương."
    assert updated[1]["text_vi"] == "Đây là con bò con."


def test_load_and_save_glossary(tmp_path):
    path = str(tmp_path / "glossary.json")
    data = {"Đại ca": "Huynh trưởng", "Sư phụ": "Thầy"}
    save_glossary_file(data, path)
    assert os.path.isfile(path)

    loaded = load_glossary_file(path)
    assert loaded == data
