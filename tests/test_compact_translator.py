import pytest
from unittest.mock import MagicMock, patch
from autodub.text.compact_translator import (
    estimate_vietnamese_syllable_count,
    is_translation_too_long,
    compact_vietnamese_text,
)

def test_estimate_vietnamese_syllable_count():
    assert estimate_vietnamese_syllable_count("Xin chào Việt Nam") == 4
    assert estimate_vietnamese_syllable_count("Hôm nay trời rất đẹp, chúng ta đi chơi nhé!") == 10

def test_is_translation_too_long():
    # Slot 1.0s: tốc độ nói bình thường ~3.5 âm tiết/giây
    # 4 âm tiết trong 1.0s -> vừa (không quá dài)
    assert not is_translation_too_long("Xin chào bạn", slot_duration_s=1.0, max_syllables_per_s=4.5)
    # 10 âm tiết trong 1.0s -> quá dài (10/1.0 = 10 > 4.5)
    assert is_translation_too_long("Hôm nay tôi cảm thấy vô cùng vui vẻ và hạnh phúc", slot_duration_s=1.0, max_syllables_per_s=4.5)

def test_compact_vietnamese_text_offline_heuristic():
    # Khi không có LLM connection, hàm heuristic rút gọn từ ngữ dư thừa
    long_text = "Thật sự là hôm nay tôi cảm thấy rất là vui vẻ"
    compacted = compact_vietnamese_text(long_text, max_syllables=6)
    assert estimate_vietnamese_syllable_count(compacted) <= estimate_vietnamese_syllable_count(long_text)
