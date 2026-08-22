"""Quản lý bảng thuật ngữ (Glossary) và tìm kiếm/thay thế hàng loạt cho phụ đề."""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Tuple


# Bảng phiên âm/ngữ âm mặc định cho AI TTS — dùng chung cho cả AI Studio và Direct API.
# KHÔNG được thêm quy tắc ký tự đơn (i, e, a, x, v, z...) hoặc ký hiệu dấu câu (/, -).
_DEFAULT_PHONETIC_GLOSSARY = [
    # Âm cảm thán / tiếng lóng rõ ràng (>= 3 ký tự)
    ('hắc hắc', 'ha ha'), ('hắc hắc hắc', 'ha ha ha'),
    ('hic', 'hích'), ('huhu', 'hu hu'), ('huhuhu', 'hu hu hu'),
    ('huh', 'Hửm'),
    ('ừhm', 'ừ'), ('Ưhm', 'ừ'),
    ('hmm', 'hừ'), ('Hmm', 'hừ'), ('Hmmm', 'hừ'),
    # Từ tiếng Anh / nước ngoài đủ dài
    ('cosplay', 'cốt bơ lay'),
    ('NTR', 'Nờ Tê Rờ'),
    ('bye', 'bai'),
    ('app', 'áp'),
    ('donate', 'đô nết'),
    ('yes', 'dét'),
    # Cụm từ Việt cụ thể đủ dài
    ('tu vi', 'tu vy'), ('vi sư', 'vy sư'), ('vi diệu', 'vy diệu'),
    ('xi măng', 'sy măng'),
]


def build_replacement_pattern(term: str, whole_word: bool = False) -> str:
    """Tạo biểu thức chính quy an toàn từ từ khóa tìm kiếm."""
    escaped = re.escape(term.strip())
    if whole_word:
        # Ranh giới từ Unicode an toàn cho cả tiếng Việt và ký tự đặc biệt
        return rf"(?<!\w){escaped}(?!\w)"
    return escaped


def apply_glossary(
    text: str,
    glossary: Dict[str, str] | List[Tuple[str, str]],
    case_sensitive: bool = False,
) -> str:
    """Áp dụng bảng thuật ngữ để thay thế các từ khóa trong văn bản trong MỘT lượt (single-pass).

    Các từ dài hơn được ưu tiên so khớp trước, và kết quả thay thế không bị thay thế lặp lại.
    """
    if not text or not glossary:
        return text

    items = (
        glossary.items()
        if isinstance(glossary, dict)
        else glossary
    )
    # Sắp xếp ưu tiên cụm từ dài nhất trước
    sorted_items = sorted(
        [(k.strip(), v) for k, v in items if k and k.strip()],
        key=lambda x: len(x[0]),
        reverse=True,
    )
    if not sorted_items:
        return text

    # Xây dựng bảng tra cứu và regex gộp
    lookup: dict[str, str] = {}
    patterns = []
    for source, target in sorted_items:
        key = source if case_sensitive else source.lower()
        lookup[key] = target
        escaped = re.escape(source)
        patterns.append(rf"(?<!\w){escaped}(?!\w)")

    combined_regex = re.compile(
        "|".join(patterns),
        flags=0 if case_sensitive else re.IGNORECASE,
    )

    def _repl(match: re.Match) -> str:
        matched_str = match.group(0)
        k = matched_str if case_sensitive else matched_str.lower()
        return lookup.get(k, matched_str)

    return combined_regex.sub(_repl, text)


def apply_glossary_to_segments(
    segments: List[dict],
    glossary: Dict[str, str],
    text_field: str = "text_vi",
    case_sensitive: bool = False,
) -> Tuple[List[dict], int]:
    """Áp dụng bảng thuật ngữ lên toàn bộ danh sách câu thoại.

    Trả về (danh sách câu đã cập nhật, số lượng câu bị thay đổi).
    """
    if not glossary:
        return segments, 0

    changed_count = 0
    updated_segments = []
    for seg in segments:
        new_seg = dict(seg)
        original_text = str(seg.get(text_field, ""))
        new_text = apply_glossary(
            original_text, glossary, case_sensitive=case_sensitive
        )
        if new_text != original_text:
            new_seg[text_field] = new_text
            changed_count += 1
        updated_segments.append(new_seg)

    return updated_segments, changed_count


def batch_replace_segments(
    segments: List[dict],
    search_term: str,
    replacement: str,
    text_field: str = "text_vi",
    case_sensitive: bool = False,
    whole_word: bool = False,
) -> Tuple[List[dict], int]:
    """Tìm kiếm và thay thế một từ/cụm từ trên toàn bộ các câu thoại."""
    if not search_term or not segments:
        return segments, 0

    pattern = build_replacement_pattern(search_term, whole_word=whole_word)
    flags = 0 if case_sensitive else re.IGNORECASE

    changed_count = 0
    updated_segments = []
    for seg in segments:
        new_seg = dict(seg)
        original_text = str(seg.get(text_field, ""))
        new_text = re.sub(pattern, replacement, original_text, flags=flags)
        if new_text != original_text:
            new_seg[text_field] = new_text
            changed_count += 1
        updated_segments.append(new_seg)

    return updated_segments, changed_count


def load_glossary_file(path: str) -> Dict[str, str]:
    """Tải bảng thuật ngữ từ tệp JSON."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        if isinstance(data, list):
            # Hỗ trợ dạng [{"source": "A", "target": "B"}]
            res = {}
            for item in data:
                if isinstance(item, dict) and "source" in item and "target" in item:
                    res[str(item["source"])] = str(item["target"])
            return res
    except Exception:
        return {}
    return {}


def save_glossary_file(glossary: Dict[str, str], path: str) -> None:
    """Lưu bảng thuật ngữ ra tệp JSON."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(glossary, f, ensure_ascii=False, indent=2)
