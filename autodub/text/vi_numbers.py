"""Chuẩn hóa văn bản tiếng Việt trước khi đưa vào TTS.

Model TTS được huấn luyện trên transcript gần như không có chữ số —
đưa "2759" vào là nuốt hoặc đọc sai. Bộ này chuyển số thành chữ đọc được:

    2759 → "hai nghìn bảy trăm năm mươi chín"
    5060 Ti → "năm không sáu không Ti" (mã sản phẩm: đọc từng chữ số)
    8G → "tám gigabyte", 32MB → "ba mươi hai megabyte", 90% → "chín mươi phần trăm"
    100k → "một trăm nghìn"
    10h30 → "mười giờ ba mươi phút"
    1/2 → "một phần hai"

Chỉ dùng cho giọng đọc — phụ đề vẫn giữ nguyên chữ số.
"""
from __future__ import annotations

import re
import unicodedata

_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")

_UNIT_WORDS = {
    "g": "gigabyte", "gb": "gigabyte", "mb": "megabyte", "kb": "kilobyte",
    "tb": "terabyte", "ghz": "gigahertz", "mhz": "megahertz", "hz": "héc",
    "w": "oát", "kw": "kilô oát", "%": "phần trăm", "km": "kilômét",
    "cm": "xentimét", "mm": "milimét", "kg": "kilôgam", "fps": "ép pê ét",
    "m": "mét", "m2": "mét vuông", "m3": "mét khối", "km/h": "kilômét trên giờ",
    "k": "nghìn", "tr": "triệu", "usd": "đô la", "vnd": "đồng", "vnđ": "đồng",
    "đ": "đồng", "củ": "triệu",
}

# Các từ viết tắt phổ biến trong video / công nghệ / đời sống
_ABBREVIATIONS = {
    r"\bAI\b": "A I",
    r"\bCPU\b": "C P U",
    r"\bGPU\b": "G P U",
    r"\bRAM\b": "Ram",
    r"\bROM\b": "Rom",
    r"\bPC\b": "P C",
    r"\bTV\b": "ti vi",
    r"\bUSB\b": "U S B",
    r"\bOK\b": "ô kê",
    r"\bok\b": "ô kê",
    r"\bv\.v\.\b": "vân vân",
    r"\bv\.v\b": "vân vân",
    r"\bv/v\b": "về việc",
    r"\b(VNĐ|VND|vnđ|vnd)\b": "đồng",
    r"\bUSD\b": "đô la",
    r"\bDr\.\s*": "bác sĩ ",
    r"\bMr\.\s*": "ông ",
    r"\bMs\.\s*": "bà ",
    r"\bMrs\.\s*": "bà ",
    r"\b1st\b": "thứ nhất",
    r"\b2nd\b": "thứ hai",
    r"\b3rd\b": "thứ ba",
}


def _two_digits(n: int, full: bool = False) -> str:
    """0-99 thành chữ. ``full`` thêm 'lẻ' khi hàng chục = 0 (sau hàng trăm)."""
    tens, ones = divmod(n, 10)
    if tens == 0:
        return ("lẻ " + _DIGITS[ones]) if (full and ones) else _DIGITS[ones]
    ten_part = "mười" if tens == 1 else _DIGITS[tens] + " mươi"
    if ones == 0:
        return ten_part
    if ones == 1 and tens > 1:
        return ten_part + " mốt"
    if ones == 4 and tens > 1:
        return ten_part + " tư"
    if ones == 5:
        return ten_part + " lăm"
    return ten_part + " " + _DIGITS[ones]


def _three_digits(n: int, force_hundred: bool = False) -> str:
    """0-999 thành chữ; ``force_hundred`` đọc cả 'không trăm' (giữa số lớn)."""
    hundreds, rest = divmod(n, 100)
    if hundreds == 0 and not force_hundred:
        return _two_digits(rest)
    parts = [_DIGITS[hundreds] + " trăm"]
    if rest:
        parts.append(_two_digits(rest, full=True))
    return " ".join(parts)


def number_to_words(n: int) -> str:
    """Số nguyên không âm thành chữ tiếng Việt (tới hàng tỷ tỷ)."""
    if n == 0:
        return _DIGITS[0]
    groups: list[int] = []           # [đơn vị, nghìn, triệu, tỷ, ...]
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    names = ("", " nghìn", " triệu", " tỷ", " nghìn tỷ", " triệu tỷ", " tỷ tỷ")
    if len(groups) > len(names):     # >10^21 — không gặp trong thực tế
        return _digit_by_digit("".join(str(g).zfill(3) for g in reversed(groups)).lstrip("0"))
    parts: list[str] = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        force = i < len(groups) - 1    # nhóm giữa: đọc 'không trăm lẻ...'
        parts.append(_three_digits(g, force_hundred=force) + names[i])
    return " ".join(parts)


def _digit_by_digit(s: str) -> str:
    return " ".join(_DIGITS[int(c)] for c in s if c.isdigit())


def _read_number(num: str) -> str:
    """Một cụm số thành chữ: mã 4+ chữ số bắt đầu bằng đầu số 'model' phổ biến
    đọc từng chữ số (5060 → năm không sáu không), còn lại đọc giá trị."""
    if len(num) >= 4 and num[0] != "0" and ("0" in num[1:]):
        # Heuristic mã sản phẩm: 4-5 chữ số chứa số 0 ở giữa (5060, 1080,
        # 4070) — nhưng số tròn trăm/nghìn (2000, 1500 → "00") là GIÁ TRỊ,
        # đọc từng chữ số sẽ sai ("hai không không không").
        if len(num) <= 5 and not num.endswith("00"):
            return _digit_by_digit(num)
    if num.startswith("0"):          # 090..., 007 — luôn đọc từng số
        return _digit_by_digit(num)
    return number_to_words(int(num))


_UNIT_ALTS = "|".join(sorted((k for k in _UNIT_WORDS if k != "%"),
                             key=len, reverse=True))
_NUM_UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(" + _UNIT_ALTS + r")\b",
                          re.IGNORECASE)
_DECIMAL_RE = re.compile(r"(\d+)[.,](\d+)")
_GROUPED_RE = re.compile(r"(\d{1,3})(?:\.(\d{3}))+(?!\d)")
_INT_RE = re.compile(r"\d+")

# Loại bỏ thẻ phụ đề phi thoại
_AUDIO_TAGS_RE = re.compile(r"\[(âm nhạc|nhạc|tiếng cười|thở dài|vỗ tay|tiếng chuông|music|applause|laughter|gasp)\]|\((âm nhạc|nhạc|tiếng cười|thở dài|vỗ tay|tiếng chuông|cười|thở dài)\)|\*(vỗ tay|cười|thở dài)\*", re.IGNORECASE)


def normalize_vi_text(text: str) -> str:
    """Chuyển mọi chữ số, viết tắt và ký hiệu trong câu thành chữ tiếng Việt đọc được."""
    if not text:
        return ""

    # 1. Đưa về Unicode chuẩn NFC
    text = unicodedata.normalize("NFC", str(text))

    # 2. Xóa các thẻ chú thích âm thanh phụ đề
    text = _AUDIO_TAGS_RE.sub(" ", text)

    # 3. Ký tự tiền tệ dạng $100 -> 100 đô la, 100$ -> 100 đô la
    text = re.sub(r"\$\s*(\d+(?:[.,]\d+)?)", r"\1 đô la", text)
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s*\$", r"\1 đô la", text)

    # 4. 1.234 / 50.000 / 2.759.000 (dấu chấm phân nhóm nghìn) → số liền (50000, 2759000)
    text = _GROUPED_RE.sub(lambda m: m.group(0).replace(".", ""), text)

    # 5. Thời gian: 10h30 -> 10 giờ 30 phút, 8h -> 8 giờ
    text = re.sub(r"\b(\d{1,2})h(\d{1,2})\b", lambda m: f"{_read_number(m.group(1))} giờ {_read_number(m.group(2))} phút", text)
    text = re.sub(r"\b(\d{1,2})h\b", lambda m: f"{_read_number(m.group(1))} giờ", text)
    text = re.sub(r"\b(\d{1,2}):(\d{2})\b", lambda m: f"{_read_number(m.group(1))} giờ {_read_number(m.group(2))} phút", text)

    # 6. Thứ hạng: top 1, Top 10 -> tốp một, tốp mười, No.1 -> số một
    text = re.sub(r"\b(top|Top|TOP)\s*(\d+)\b", lambda m: f"tốp {_read_number(m.group(2))}", text)
    text = re.sub(r"\b(No|no|Số)\.?\s*(\d+)\b", lambda m: f"số {_read_number(m.group(2))}", text)

    # 7. Dải số: 1-2, 1–2 -> 1 đến 2
    text = re.sub(r"\b(\d+)\s*[-–—]\s*(\d+)\b", lambda m: f"{_read_number(m.group(1))} đến {_read_number(m.group(2))}", text)

    # 8. Phân số: 1/2, 3/4 -> một phần hai, ba phần tư
    def _fraction(m: re.Match) -> str:
        num = m.group(1)
        den = m.group(2)
        den_str = "hai" if den == "2" else ("tư" if den == "4" else _read_number(den))
        return f"{_read_number(num)} phần {den_str}"
    text = re.sub(r"\b(\d+)/(\d+)\b", _fraction, text)

    # 9. Số + Tên đơn vị (100k, 32MB, 3.5GHz, 90%, 50.000đ)
    def _unit(m: re.Match) -> str:
        num = m.group(1)
        unit_key = m.group(2).lower()
        unit_word = _UNIT_WORDS.get(unit_key, unit_key)
        if "." in num or "," in num:
            whole, frac = re.split(r"[.,]", num, maxsplit=1)
            spoken = f"{_read_number(whole)} phẩy {_digit_by_digit(frac)}"
        else:
            spoken = _read_number(num)
        return f"{spoken} {unit_word}"
    text = _NUM_UNIT_RE.sub(_unit, text)
    text = re.sub(r"(\d+)\s*%", lambda m: f"{_read_number(m.group(1))} phần trăm", text)

    # 10. Chuyển đổi các từ viết tắt
    for pattern, repl in _ABBREVIATIONS.items():
        text = re.sub(pattern, repl, text)

    # 11. Thập phân còn lại
    def _dec(m: re.Match) -> str:
        return f"{_read_number(m.group(1))} phẩy {_digit_by_digit(m.group(2))}"
    text = _DECIMAL_RE.sub(_dec, text)

    # 12. Số nguyên còn lại
    text = _INT_RE.sub(lambda m: _read_number(m.group()), text)

    # 13. Ký tự toán học & biểu tượng
    text = text.replace("@", " a còng ").replace("&", " và ").replace("+", " cộng ").replace("=", " bằng ").replace("~", " khoảng ")

    return re.sub(r"\s+", " ", text).strip()
