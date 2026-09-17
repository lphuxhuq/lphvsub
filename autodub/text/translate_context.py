"""Phân tích ngữ cảnh video và phụ đề chưa dịch (Phase 0).

Rút trích chủ đề, tóm tắt nội dung, danh sách nhân vật, quy ước xưng hô
và thuật ngữ cố định trước khi tiến hành dịch theo lô.
"""

from __future__ import annotations

import dataclasses
import json
import os
from typing import Any

from autodub.utils import setup_logging

logger = setup_logging("autodub.translate_context")


def sample_transcript(segments: list[dict], max_lines: int = 120) -> list[str]:
    """Lấy mẫu thông minh từ transcript chưa dịch: đầu, giữa và cuối."""
    texts = [str(s.get("text", "")).strip() for s in segments if s.get("text")]
    if not texts:
        return []
    if len(texts) <= max_lines:
        return texts

    part = max_lines // 3
    mid = len(texts) // 2
    head = texts[:part]
    middle = texts[max(0, mid - part // 2) : min(len(texts), mid + part // 2)]
    tail = texts[-part:]
    return [*head, "... [đoạn giữa] ...", *middle, "... [đoạn kết] ...", *tail]


def analyze_transcript_context(
    segments: list[dict],
    source_lang: str,
    settings: Any,
    video_title: str = "",
    cache_path: str | None = None,
) -> dict | None:
    """Phân tích ngữ cảnh video từ sub chưa dịch và tiêu đề, lưu cache vào video_context.json."""
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached, dict) and cached.get("summary"):
                logger.info("Dùng lại phân tích ngữ cảnh video từ cache video_context.json")
                return cached
        except Exception as e:
            logger.debug(f"Không thể đọc cache video_context.json ({e}), chạy phân tích mới")

    texts = sample_transcript(segments)
    if not texts:
        return None

    effective_title = video_title or getattr(settings, "translate_video_title", "")
    gemini_key = getattr(settings, "gemini_api_key", "").strip()
    if not gemini_key:
        logger.debug("Không có Gemini API Key, bỏ qua phân tích ngữ cảnh tự động")
        return None

    from autodub.text.translate_direct import GeminiDirectClient

    model = getattr(settings, "gemini_model", "gemini-2.5-flash") or "gemini-2.5-flash"
    client = GeminiDirectClient(gemini_key, model=model, thinking=False)

    system_instruction = (
        "Bạn là chuyên gia phân tích kịch bản video và ngữ cảnh cho lồng tiếng. "
        "Nhiệm vụ của bạn là đọc tiêu đề và các câu thoại trích mẫu của video, "
        "từ đó phân tích thể loại, tóm tắt nội dung, danh sách nhân vật, quy ước xưng hô chuẩn mực "
        "và thuật ngữ/tên riêng để phục vụ dịch lồng tiếng chất lượng cao."
    )

    schema = {
        "type": "OBJECT",
        "properties": {
            "domain": {
                "type": "STRING",
                "description": "Thể loại/chủ đề cụ thể của video (vd: Review phim kịch tính, Vlog ẩm thực, Khoa học công nghệ, Cổ trang kiếm hiệp)",
            },
            "summary": {
                "type": "STRING",
                "description": "Tóm tắt ngắn gọn cốt truyện hoặc nội dung chính trong 2-3 câu",
            },
            "characters": {
                "type": "STRING",
                "description": "Danh sách các nhân vật chính, độ tuổi, vai trò và mối quan hệ",
            },
            "pronouns": {
                "type": "STRING",
                "description": "Quy ước xưng hô chuẩn xác giữa các nhân vật và với khán giả người xem",
            },
            "glossary": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Danh sách danh từ riêng, thuật ngữ hoặc tên nhân vật cần dịch thống nhất (Gốc -> Dịch)",
            },
            "style_notes": {
                "type": "STRING",
                "description": "Gợi ý giọng điệu và phong cách lồng tiếng phù hợp nhất cho video này",
            },
        },
        "required": ["domain", "summary", "pronouns"],
    }

    user_prompt = (
        f"Tiêu đề video: {effective_title or 'Không có'}\n"
        f"Ngôn ngữ nguồn: {source_lang}\n"
        f"Các câu thoại trích mẫu từ video:\n"
        f"{json.dumps(texts, ensure_ascii=False, indent=2)}\n\n"
        "Hãy phân tích ngữ cảnh video trên và trả về kết quả theo cấu trúc JSON."
    )

    try:
        raw_reply = client.call_ai(
            system_instruction,
            user_prompt,
            response_schema=schema,
            max_retries=2,
        )
        data = json.loads(raw_reply)
        if isinstance(data, dict):
            logger.info(
                f"Phân tích ngữ cảnh thành công: {data.get('domain')} | {str(data.get('summary'))[:80]}..."
            )
            if cache_path:
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception as save_err:
                    logger.debug(f"Không thể lưu cache video_context.json: {save_err}")
            return data
    except Exception as exc:
        logger.warning(
            f"Phân tích ngữ cảnh video qua Gemini lỗi ({exc}) — tiếp tục dịch với thiết lập mặc định"
        )
        return None

    return None


def apply_analysis(settings: Any, analysis: dict | None) -> Any:
    """Cập nhật các trường ngữ cảnh còn trống trong Settings bằng kết quả phân tích."""
    if not analysis or not isinstance(analysis, dict):
        return settings

    updates: dict[str, Any] = {}
    if not getattr(settings, "translate_domain", "").strip() and analysis.get("domain"):
        updates["translate_domain"] = str(analysis["domain"]).strip()

    if not getattr(settings, "translate_context", "").strip() and analysis.get("summary"):
        ctx_parts = [str(analysis["summary"]).strip()]
        if analysis.get("characters"):
            ctx_parts.append(f"Nhân vật: {str(analysis['characters']).strip()}")
        updates["translate_context"] = "\n\n".join(ctx_parts)

    if not getattr(settings, "translate_pronouns", "").strip() and analysis.get("pronouns"):
        updates["translate_pronouns"] = str(analysis["pronouns"]).strip()

    if not getattr(settings, "translate_glossary", "").strip() and analysis.get("glossary"):
        items = analysis["glossary"]
        if isinstance(items, list):
            updates["translate_glossary"] = "\n".join(
                str(x).strip() for x in items[:20] if str(x).strip()
            )
        elif isinstance(items, str):
            updates["translate_glossary"] = items.strip()

    if not getattr(settings, "translate_style_notes", "").strip() and analysis.get("style_notes"):
        updates["translate_style_notes"] = str(analysis["style_notes"]).strip()

    if analysis.get("translate_style"):
        updates["translate_style"] = str(analysis["translate_style"]).strip()
    elif analysis.get("style"):
        updates["translate_style"] = str(analysis["style"]).strip()

    if not updates:
        return settings

    logger.info(
        "Bơm ngữ cảnh phân tích tự động vào cài đặt dịch: "
        + ", ".join(k.replace("translate_", "") for k in updates)
    )
    return dataclasses.replace(settings, **updates)
