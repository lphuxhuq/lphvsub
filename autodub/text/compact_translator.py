"""AI Semantic Compactor — tự động nhận diện và rút gọn câu dịch khi quá dài so với slot video.

Khi câu tiếng Việt dịch ra có số lượng âm tiết vượt quá tốc độ phát âm tự nhiên
(> 4.5 âm tiết/giây), module này sẽ tự động cô đọng câu thoại để diễn viên đọc
khớp thời lượng mà không bị tăng tốc độ quá cao.
"""
from __future__ import annotations

import re
from autodub.utils import setup_logging

logger = setup_logging("autodub.compact_translator")

_WORDS_RE = re.compile(r"[a-zA-Zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệđìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ\w]+", re.UNICODE)

# Danh sách từ đệm có thể lược bỏ khi cần cô đọng nhanh offline
_REDUNDANT_FILLERS = [
    r"\bthật sự là\b",
    r"\brất là\b",
    r"\brõ ràng là\b",
    r"\bchính là vì\b",
    r"\bcó thể nói là\b",
    r"\bngay lập tức\b",
    r"\bở tại nơi này\b",
]


def estimate_vietnamese_syllable_count(text: str) -> int:
    """Đếm số âm tiết (từ đơn) trong câu tiếng Việt."""
    if not text:
        return 0
    words = _WORDS_RE.findall(text)
    return len(words)


def is_translation_too_long(
    text: str,
    slot_duration_s: float,
    *,
    max_syllables_per_s: float = 4.5,
) -> bool:
    """Kiểm tra xem câu dịch có bị quá dài so với thời lượng slot hay không."""
    if slot_duration_s <= 0 or not text:
        return False
    syllables = estimate_vietnamese_syllable_count(text)
    syllables_per_s = syllables / slot_duration_s
    return syllables_per_s > max_syllables_per_s


def compact_vietnamese_text(
    text: str,
    max_syllables: int,
    *,
    gemini_key: str = "",
    model: str = "gemini-2.5-flash",
) -> str:
    """Rút gọn câu tiếng Việt để vừa vặn với số âm tiết tối đa."""
    if not text:
        return ""

    curr_syllables = estimate_vietnamese_syllable_count(text)
    if curr_syllables <= max_syllables:
        return text

    # 1. Thử gọi LLM nếu có API key
    if gemini_key:
        try:
            from autodub.text.translate_gemini import translate_with_gemini
            prompt = (
                f"Hãy rút gọn câu thoại sau thành bản tiếng Việt súc tích tối đa {max_syllables} từ, "
                f"giữ nguyên 100% nội dung cốt lõi và cảm xúc: \"{text}\". "
                f"Chỉ trả về đúng câu đã rút gọn, không thêm bất kỳ giải thích nào."
            )
            res = translate_with_gemini(prompt, api_key=gemini_key, model_name=model)
            if res and estimate_vietnamese_syllable_count(res) <= max_syllables + 1:
                logger.info(f"AI Compactor: '{text}' ({curr_syllables} từ) -> '{res}'")
                return res.strip("\"' ")
        except Exception as e:
            logger.warning(f"Lỗi AI Compactor qua Gemini: {e}")

    # 2. Fallback Heuristic offline nếu không có key hoặc LLM timeout
    compacted = text
    for pattern in _REDUNDANT_FILLERS:
        compacted = re.sub(pattern, "", compacted, flags=re.IGNORECASE).strip()
        compacted = re.sub(r"\s+", " ", compacted)

    return compacted
