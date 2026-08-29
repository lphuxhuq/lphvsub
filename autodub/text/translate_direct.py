"""Dịch trực tiếp qua API bên thứ 3 (HHTech / Custom Base URL / Gemini / OpenAI / DeepSeek / OpenRouter) từ máy khách.
Hỗ trợ nhập nhiều API Key để chia luồng song song (Multi-threading) tăng tốc độ dịch tối đa.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

import requests

from autodub.languages import TargetLang
from autodub.progress import ProgressReporter
from autodub.text.glossary import _DEFAULT_PHONETIC_GLOSSARY
from autodub.text.translate_common import TranslateCheckpoint, TranslateError
from autodub.text.translate_hint import annotate_slots, effective_cps, ensure_terminal_punct, payload_segment
from autodub.utils import setup_logging

logger = setup_logging("autodub.translate_direct")

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_CITE_RE = re.compile(r"\[cite:\s*[\d,\s]+\]", re.IGNORECASE)
_FALLBACK_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.5-pro",
    "gemini-1.5-pro",
]


class _KeyRateLimiter:
    """Điều phối nhịp gửi API cho từng API Key riêng biệt."""

    def __init__(self, min_interval_s: float = 0.3):
        self.min_interval_s = min_interval_s
        self._last_hits: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            last = self._last_hits.get(key, 0.0)
            wait = self.min_interval_s - (now - last)
            if wait > 0:
                time.sleep(wait)
            self._last_hits[key] = time.monotonic()


KEY_LIMITER = _KeyRateLimiter(min_interval_s=0.3)


def _has_cjk(text: str) -> bool:
    """Kiểm tra câu dịch có còn sót ký tự chữ Hán / Nhật / Hàn không."""
    if not text:
        return False
    cjk_count = sum(
        1 for c in text
        if (0x4E00 <= ord(c) <= 0x9FFF)    # CJK Unified Ideographs
        or (0x3400 <= ord(c) <= 0x4DBF)    # CJK Extension A
        or (0xAC00 <= ord(c) <= 0xD7AF)    # Korean Hangul
        or (0x3040 <= ord(c) <= 0x30FF)    # Hiragana + Katakana
    )
    return cjk_count >= 2


def _strip_fences_and_citations(text: str) -> str:
    cleaned = re.sub(_CITE_RE, "", text)
    cleaned = re.sub(_FENCE_RE, "", cleaned)
    return cleaned.strip()


def _slice_to_payload(text: str) -> str:
    starts = [text.find("{"), text.find("[")]
    valid_starts = [i for i in starts if i >= 0]
    if not valid_starts:
        return text
    start = min(valid_starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1] if end > start else text[start:]


def _repair_json(text: str) -> str:
    cleaned = _slice_to_payload(_strip_fences_and_citations(text)).rstrip()
    if not cleaned:
        return cleaned

    stack = []
    in_string = False
    escaped = False
    for ch in cleaned:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in ("{", "["):
            stack.append("}" if ch == "{" else "]")
        elif ch in ("}", "]") and stack:
            stack.pop()

    if in_string:
        cleaned += '"'
    cleaned = re.sub(r",\s*$", "", cleaned)
    cleaned = re.sub(r',\s*"[^"]*"\s*:?\s*$', "", cleaned)
    cleaned = re.sub(r'\{\s*"[^"]*"\s*:?\s*$', "{", cleaned)
    return cleaned + "".join(reversed(stack))


def parse_response_segments(content: str, text_field: str = "text_vi") -> List[dict]:
    """Phân tích kết quả trả về (JSON hoặc dòng đánh số) thành mảng các câu dịch."""
    raw = _strip_fences_and_citations(content)

    candidates: List[str] = [raw, _slice_to_payload(raw), _repair_json(raw)]

    # Trích xuất khối ```json ... ``` hoặc ``` ... ``` nếu AI trả về kèm suy nghĩ/lời giải thích
    for fence_match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", content, re.IGNORECASE):
        fc = fence_match.group(1).strip()
        if fc:
            candidates.insert(0, fc)
            candidates.insert(1, _slice_to_payload(fc))
            candidates.insert(2, _repair_json(fc))

    # Tìm khối mảng JSON [ ... ] xuất hiện bất kỳ đâu trong văn bản
    array_match = re.search(r"(\[\s*\{[\s\S]*\}\s*\])", content)
    if array_match:
        ac = array_match.group(1).strip()
        candidates.insert(0, ac)
        candidates.insert(1, _repair_json(ac))

    # 1. Thử parse JSON chuẩn hoặc JSON đã sửa
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if isinstance(data, dict):
            data = data.get("segments") or data.get("data") or data.get("translations")
        if isinstance(data, list):
            valid = []
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    txt = item.get(text_field) or item.get("translation") or item.get("text_vi") or item.get("text")
                    if txt is not None:
                        item[text_field] = str(txt).strip()
                        valid.append(item)
            if valid:
                return valid

    # 2. Fallback: Trích xuất từng object {"id": ..., "text_vi": "..."} hoặc {"text_vi": "...", "id": ...}
    # Bền bỉ ngay cả khi toàn bộ chuỗi JSON bị cắt cụt đuôi hoặc lẫn tạp âm UI AI Studio
    obj_pattern = re.compile(
        r'\{\s*"id"\s*:\s*(\d+)\s*,\s*"(?:'
        + re.escape(text_field)
        + r'|translation|text_vi|text)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"',
        re.IGNORECASE,
    )
    regex_items: List[dict] = []
    seen_ids = set()
    for m in obj_pattern.finditer(content):
        sid = int(m.group(1))
        raw_val = m.group(2)
        try:
            val_txt = json.loads(f'"{raw_val}"')
        except Exception:
            val_txt = raw_val
        if val_txt and val_txt.strip() and sid not in seen_ids:
            regex_items.append({"id": sid, text_field: val_txt.strip()})
            seen_ids.add(sid)

    if not regex_items:
        obj_pattern_rev = re.compile(
            r'\{\s*"(?:'
            + re.escape(text_field)
            + r'|translation|text_vi|text)"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"\s*,\s*"id"\s*:\s*(\d+)',
            re.IGNORECASE,
        )
        for m in obj_pattern_rev.finditer(content):
            raw_val = m.group(1)
            sid = int(m.group(2))
            try:
                val_txt = json.loads(f'"{raw_val}"')
            except Exception:
                val_txt = raw_val
            if val_txt and val_txt.strip() and sid not in seen_ids:
                regex_items.append({"id": sid, text_field: val_txt.strip()})
                seen_ids.add(sid)

    if regex_items:
        return regex_items

    # 3. Fallback: Parse theo dạng dòng đánh số "1. Lời thoại..."
    numbered_lines = []
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^(\d+)[\.\:\-\s]+(.*)$", line)
        if m:
            sid = int(m.group(1))
            txt = m.group(2).strip()
            if txt:
                numbered_lines.append({"id": sid, text_field: txt})
    if numbered_lines:
        return numbered_lines

    raise TranslateError(f"Không thể đọc kết quả dịch từ AI: {raw[:200]}")


def _phonetic_section() -> str:
    """Tạo phần hướng dẫn phiên âm dùng chung cho cả Direct API và Browser."""
    lines = [
        "### PHIÊN ÂM / TIẾNG LÓNG BẮT BUỘC",
        "Khi gặp các từ/ngữ sau trong câu nguồn hoặc câu dịch, dùng dạng bên phải để AI TTS đọc đúng:",
    ]
    for src, dst in _DEFAULT_PHONETIC_GLOSSARY:
        lines.append(f'  "{src}" → "{dst}"')
    return "\n".join(lines)


def _build_system_prompt(
    target_field: str = "text_vi",
    style_notes: str = "",
    target: Optional[TargetLang] = None,
    source_lang: str = "zh",
    settings: Any = None,
    cps_budget: Optional[float] = None,
) -> str:
    """Tạo System Prompt dịch thuật chất lượng cao (đồng bộ với chuẩn AI Studio / Prompt Master)."""
    from autodub.languages import get_target
    from autodub.text.translate_hint import (
        CHARS_PER_SECOND_BUDGET,
        build_translation_prompt,
        effective_cps,
    )

    if target is None:
        target = get_target("vi" if "vi" in target_field else target_field)

    cps = cps_budget or (effective_cps(settings) if settings else CHARS_PER_SECOND_BUDGET)
    base_prompt = build_translation_prompt(
        target=target,
        source_lang=source_lang,
        settings=settings,
        cps_budget=cps,
        compact_output=True,
    )
    phonetic = _phonetic_section()

    extra_blocks = [phonetic]
    if style_notes and style_notes.strip():
        if style_notes.strip() not in base_prompt:
            extra_blocks.append(f"### YÊU CẦU BỔ SUNG VỀ VĂN PHONG:\n{style_notes.strip()}")

    return base_prompt + "\n\n" + "\n\n".join(extra_blocks)


class GeminiDirectClient:
    """Gọi trực tiếp Google Gemini API với cơ chế luân chuyển nhiều API Key và Fallback Model."""

    def __init__(self, api_keys: List[str] | str, model: str = "gemini-2.5-flash", timeout_s: int = 120,
                 thinking: bool = False):
        if isinstance(api_keys, str):
            raw_tokens = re.split(r"[,;\n]+", api_keys)
            self.keys = [k.strip().strip("'\"") for k in raw_tokens if k.strip().strip("'\"")]
        else:
            self.keys = [str(k).strip().strip("'\"") for k in api_keys if str(k).strip().strip("'\"")]
        if not self.keys:
            raise ValueError("Cần cung cấp ít nhất một Gemini API Key.")

        self._key_index = 0
        self._lock = threading.Lock()
        self.model = model.strip() if model else "gemini-2.5-flash"
        self.timeout_s = timeout_s
        # TRANSLATE_THINKING: model 2.5 "nghĩ" hàng chục giây trước khi trả
        # JSON — dịch theo schema không cần, mặc định tắt cho nhanh.
        self.thinking = bool(thinking)
        self.session = requests.Session()

    def get_key(self, index: Optional[int] = None) -> str:
        if index is not None:
            return self.keys[index % len(self.keys)]
        with self._lock:
            return self.keys[self._key_index % len(self.keys)]

    def rotate_key(self) -> str:
        with self._lock:
            self._key_index += 1
            new_key = self.keys[self._key_index % len(self.keys)]
            logger.info(f"Đã chuyển sang Gemini API Key #{self._key_index % len(self.keys) + 1}/{len(self.keys)}")
            return new_key

    def call_ai(
        self,
        system_instruction: str,
        user_prompt: str,
        preferred_key: Optional[str] = None,
        max_retries: int = 4,
        response_schema: Optional[dict] = None,
    ) -> str:
        models = [self.model] + [m for m in _FALLBACK_GEMINI_MODELS if m != self.model]
        model_idx = 0
        current_key = preferred_key or self.get_key()
        include_schema = bool(response_schema)

        for attempt in range(max_retries):
            KEY_LIMITER.acquire(current_key)
            current_model = models[model_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"

            gen_cfg: dict[str, Any] = {
                "temperature": 0.3,
                "responseMimeType": "application/json",
                "maxOutputTokens": 16384,
            }
            if include_schema and response_schema:
                gen_cfg["responseSchema"] = response_schema

            # Tắt thinking cho model 2.5 flash: dịch theo schema JSON không
            # cần "suy nghĩ" — chênh lệch là hàng chục giây mỗi call. Model
            # 1.5 từ chối field lạ (400), 2.5-pro không cho tắt (floor 128).
            if ("2.5" in current_model and "pro" not in current_model
                    and not self.thinking):
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
            payload = {
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": gen_cfg,
            }
            if system_instruction and system_instruction.strip():
                payload["systemInstruction"] = {
                    "parts": [{"text": system_instruction.strip()}]
                }

            headers = {
                "Content-Type": "application/json",
                "x-goog-api-key": current_key,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            params = {"key": current_key}

            try:
                resp = self.session.post(
                    url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_s,
                )
            except Exception as e:
                logger.warning(f"Gemini API kết nối lỗi (lần {attempt + 1}/{max_retries}): {e}")
                time.sleep(2.0 * (attempt + 1))
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if not candidates:
                        raise TranslateError(f"Gemini không trả về candidate: {data}")
                    parts = candidates[0].get("content", {}).get("parts") or []
                    text = "".join(p.get("text", "") for p in parts)
                    if not text.strip():
                        raise TranslateError("Gemini trả về nội dung rỗng.")
                    return text
                except Exception as e:
                    logger.warning(f"Lỗi đọc dữ liệu từ Gemini: {e}")

            err_text = resp.text[:300]
            if resp.status_code == 400 and include_schema:
                logger.warning(f"Model {current_model} từ chối responseSchema (400), thử lại không kèm schema...")
                include_schema = False
                continue

            if resp.status_code == 401:
                masked = f"...{current_key[-6:]}" if len(current_key) > 6 else "***"
                logger.error(f"Khóa API Gemini không hợp lệ ({masked}): HTTP 401")
                if len(self.keys) > 1:
                    current_key = self.rotate_key()
                    continue
                raise TranslateError(f"Khóa API Gemini không hợp lệ (HTTP 401 UNAUTHENTICATED).")

            if resp.status_code == 429 or (resp.status_code == 403 and "quota" in err_text.lower()):
                if len(self.keys) > 1:
                    current_key = self.rotate_key()
                    continue
                wait_s = min(20.0, 3.0 * (attempt + 1) + random.uniform(0.5, 2.0))
                time.sleep(wait_s)
                continue

            if resp.status_code == 404 and model_idx + 1 < len(models):
                model_idx += 1
                logger.warning(f"Model {current_model} không khả dụng (404), chuyển sang {models[model_idx]}")
                continue

            logger.warning(f"Gemini HTTP {resp.status_code}: {err_text}")
            time.sleep(2.0 * (attempt + 1))

        raise TranslateError(f"Không thể gọi Gemini API sau {max_retries} lần thử: HTTP {resp.status_code} - {err_text}")



class OpenAICompatDirectClient:
    """Gọi trực tiếp OpenAI-Compatible API (HHTech, DeepSeek, OpenRouter, OpenAI, v.v.) từ máy khách."""

    def __init__(
        self,
        api_keys: List[str] | str,
        base_url: str = "https://hhtechapi.net/v1",
        model: str = "deepseek-v4-flash",
        timeout_s: int = 75,
    ):
        if isinstance(api_keys, str):
            raw_tokens = re.split(r"[,;\n]+", api_keys)
            self.keys = [k.strip().strip("'\"") for k in raw_tokens if k.strip().strip("'\"")]
        else:
            self.keys = [str(k).strip().strip("'\"") for k in api_keys if str(k).strip().strip("'\"")]
        if not self.keys:
            raise ValueError("Cần cung cấp ít nhất một API Key.")

        self._key_index = 0
        self._lock = threading.Lock()
        base = base_url.strip().rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        self.endpoint = f"{base}/chat/completions"
        self.model = model.strip() if model else "deepseek-v4-flash"
        self.timeout_s = timeout_s
        self.session = requests.Session()

    def get_key(self, index: Optional[int] = None) -> str:
        if index is not None:
            return self.keys[index % len(self.keys)]
        with self._lock:
            return self.keys[self._key_index % len(self.keys)]

    def rotate_key(self) -> str:
        with self._lock:
            self._key_index += 1
            new_key = self.keys[self._key_index % len(self.keys)]
            logger.info(f"Đã chuyển sang API Key #{self._key_index % len(self.keys) + 1}/{len(self.keys)}")
            return new_key

    def call_ai(
        self,
        system_instruction: str,
        user_prompt: str,
        preferred_key: Optional[str] = None,
        max_retries: int = 6,
        response_format: Optional[dict] = None,
        response_schema: Optional[dict] = None,
    ) -> str:
        current_key = preferred_key or self.get_key()
        # Fallback model nếu model chính bị nghẽn trên HHTech proxy
        fallback_models = [self.model]
        if "hhtech" in self.endpoint:
            for alt in ("deepseek-v4-pro", "grok-4.6"):
                if alt not in fallback_models:
                    fallback_models.append(alt)

        include_fmt = bool(response_format)
        for attempt in range(max_retries):
            KEY_LIMITER.acquire(current_key)
            current_model = fallback_models[attempt % len(fallback_models)]
            if attempt > 0:
                logger.info(f"    ↻ Thử lại lần {attempt + 1}/{max_retries} với model [{current_model}]...")
            else:
                logger.debug(f"    → Gọi [{current_model}] (attempt 1/{max_retries})")
            headers = {
                "Authorization": f"Bearer {current_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
            payload: dict[str, Any] = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
                "stream": True,  # Stream để không bị timeout giữa chừng khi proxy bận
            }
            if include_fmt and response_format:
                payload["response_format"] = response_format

            _t_req = time.time()
            try:
                # connect timeout 10s, max 45s per-chunk để phát hiện lô bị nghẽn sớm
                resp = self.session.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=(10, 45),
                    stream=True,
                )
            except Exception as e:
                logger.warning(f"    ✗ [{current_model}] kết nối lỗi sau {time.time()-_t_req:.1f}s (lần {attempt + 1}/{max_retries}): {e}")
                # Tạo session mới để tránh kết nối cũ bị hỏng
                self.session = requests.Session()
                time.sleep(1.0 * (attempt + 1))
                continue

            if resp.status_code == 400 and include_fmt:
                logger.warning(f"Model {current_model} từ chối response_format (400), thử lại không kèm format...")
                include_fmt = False
                continue


            if resp.status_code != 200:
                err_text = resp.text[:300]
                if resp.status_code == 401:
                    masked = f"...{current_key[-6:]}" if len(current_key) > 6 else "***"
                    logger.error(f"Khóa API không hợp lệ ({masked}): HTTP 401")
                    if len(self.keys) > 1:
                        current_key = self.rotate_key()
                        continue
                    raise TranslateError(f"Khóa API không hợp lệ (HTTP 401 Unauthorized): {err_text}")
                if resp.status_code == 429:
                    if len(self.keys) > 1:
                        current_key = self.rotate_key()
                        continue
                    wait_s = min(15.0, 2.0 * (attempt + 1) + random.uniform(0.5, 1.5))
                    time.sleep(wait_s)
                    continue
                logger.warning(f"AI ({current_model}) HTTP {resp.status_code}: {err_text}")
                time.sleep(1.0 * (attempt + 1))
                continue

            # Thu thập các chunk SSE với tổng timeout 60s để không bị kẹt vô thời hạn
            try:
                import queue as _queue
                _result_q: _queue.Queue = _queue.Queue()

                def _read_stream():
                    try:
                        parts: list[str] = []
                        for raw_line in resp.iter_lines():
                            if not raw_line:
                                continue
                            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                            if not line.startswith("data:"):
                                continue
                            data_str = line[len("data:"):].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                part = delta.get("content", "")
                                if part:
                                    parts.append(part)
                            except Exception:
                                continue
                        _result_q.put("".join(parts))
                    except Exception as ex:
                        _result_q.put(ex)

                t = threading.Thread(target=_read_stream, daemon=True)
                t.start()
                try:
                    result_val = _result_q.get(timeout=40)
                except _queue.Empty:
                    elapsed = time.time() - _t_req
                    logger.warning(f"    ⏱ [{current_model}] stream kẹt quá 40s ({elapsed:.1f}s), tạo session mới và thử lại...")
                    resp.close()
                    self.session = requests.Session()
                    continue

                if isinstance(result_val, Exception):
                    raise result_val

                content = result_val.strip()
                if content:
                    elapsed = time.time() - _t_req
                    chars = len(content)
                    logger.debug(f"    ✔ [{current_model}] trả về {chars} ký tự sau {elapsed:.1f}s")
                    return content
                logger.warning(f"    ⚠ [{current_model}] trả về stream rỗng, thử lại...")
                time.sleep(1.0)
            except TranslateError:
                raise
            except Exception as e:
                logger.warning(f"    ✗ [{current_model}] stream lỗi (lần {attempt + 1}/{max_retries}): {e}")
                self.session = requests.Session()
                time.sleep(1.0 * (attempt + 1))
                continue

        raise TranslateError(f"Không thể gọi AI API sau {max_retries} lần thử.")


def get_direct_client(settings: Any) -> Tuple[Any, str]:
    """Khởi tạo client AI phù hợp dựa trên cài đặt của người dùng.
    
    Google Gemini AI (Gemini SRT Pro Direct) là bộ dịch chính trực tiếp.
    """
    # 1. Google Gemini AI (Ưu tiên số 1 - Gemini Direct / Gemini SRT Pro)
    gemini_key = getattr(settings, "gemini_api_key", "").strip()
    if gemini_key:
        model = getattr(settings, "gemini_model", "gemini-2.5-flash") or "gemini-2.5-flash"
        thinking = bool(getattr(settings, "translate_thinking", False))
        return (GeminiDirectClient(gemini_key, model=model, thinking=thinking),
                f"Google Gemini ({model})")

    # 2. DeepSeek API trực tiếp
    deepseek_key = getattr(settings, "deepseek_api_key", "").strip()
    if deepseek_key:
        return OpenAICompatDirectClient(deepseek_key, base_url="https://api.deepseek.com/v1", model="deepseek-chat"), "DeepSeek (deepseek-chat)"

    # 3. OpenRouter API
    openrouter_key = getattr(settings, "openrouter_api_key", "").strip()
    if openrouter_key:
        return OpenAICompatDirectClient(openrouter_key, base_url="https://openrouter.ai/api/v1", model="google/gemini-2.5-flash"), "OpenRouter"

    # 4. OpenAI API
    openai_key = getattr(settings, "openai_api_key", "").strip()
    if openai_key:
        return OpenAICompatDirectClient(openai_key, base_url="https://api.openai.com/v1", model="gpt-4o-mini"), "OpenAI (gpt-4o-mini)"

    raise ValueError("Chưa cấu hình Google Gemini API Key trong Cài đặt hoặc bước Tạo dự án.")


def _default_workers(num_keys: int, configured: int, is_compat: bool) -> int:
    """Số luồng dịch: cấu hình tường minh (>0) hoặc tự động theo số key.

    Tự động: proxy compat 2 luồng; Gemini tối thiểu 2 (1 key vẫn song song —
    API chấp nhận, rate limiter giữ nhịp, 429 thì client tự xoay key),
    tối đa 4 theo số key.
    """
    if configured > 0:
        return max(1, min(8, configured))
    if is_compat:
        return 2
    return max(2, min(4, num_keys))


def _plan_batches(segment_count: int, batch_size: int, workers: int,
                  floor: int) -> List[Tuple[int, int, int]]:
    """[(batch_index, begin, end)] chia ĐỀU ``segment_count`` câu thành lô.

    Mặc định theo ``batch_size``; khi số luồng nhiều hơn số lô thì chia nhỏ
    thêm (tối đa tới ``floor`` câu/lô) để mọi luồng đều có việc — 38 câu
    với batch 40 không phải ngồi 1 luồng cho 1 lô khổng lồ nữa.
    """
    if segment_count <= 0:
        return []
    n = max(1, (segment_count + batch_size - 1) // batch_size)
    if workers > 1 and floor > 0:
        n_max = max(1, segment_count // floor)
        n = max(n, min(workers, n_max))
    n = min(n, segment_count)
    base, rem = divmod(segment_count, n)
    out: List[Tuple[int, int, int]] = []
    start = 0
    for i in range(n):
        size = base + (1 if i < rem else 0)
        out.append((i + 1, start, start + size))
        start += size
    return out


def translate_segments_direct(
    segments: List[dict],
    target: TargetLang,
    source_lang: str,
    settings: Any,
    reporter: Optional[ProgressReporter] = None,
    checkpoint_path: Optional[str] = None,
) -> List[dict]:
    """Dịch toàn bộ các câu thoại trực tiếp qua API bên thứ 3 với đa luồng song song."""
    client, provider_desc = get_direct_client(settings)

    annotate_slots(segments)
    cps = effective_cps(settings)
    is_compat = isinstance(client, OpenAICompatDirectClient)
    # Với API OpenAI Compat / HHTech proxy, chia lô nhỏ 5 câu
    default_bs = 5 if is_compat else 25
    max_bs = 8 if is_compat else 40
    batch_size = max(1, min(int(getattr(settings, "translate_batch_size", default_bs) or default_bs), max_bs))

    num_keys = len(client.keys)
    configured_workers = int(getattr(settings, "translate_direct_workers", 0) or 0)
    max_workers = _default_workers(num_keys, configured_workers, is_compat)
    # Chia lô thích nghi: ít lô hơn số luồng thì chia nhỏ để đủ việc cho
    # mọi luồng (floor câu/lô) — không còn "1 lô 38 câu chạy 1 luồng".
    floor = 5 if is_compat else 8
    batches: List[Tuple[int, List[dict]]] = [
        (b_idx, segments[s:e])
        for b_idx, s, e in _plan_batches(len(segments), batch_size,
                                         max_workers, floor)
    ]

    total_batches = len(batches)
    max_workers = min(max_workers, total_batches)

    checkpoint = (
        TranslateCheckpoint(checkpoint_path, text_field=target.text_field)
        if checkpoint_path
        else None
    )

    system_prompt = _build_system_prompt(
        target_field=target.text_field,
        style_notes=getattr(settings, "translate_style_notes", ""),
        target=target,
        source_lang=source_lang,
        settings=settings,
        cps_budget=cps,
    )

    logger.info(
        f"Bắt đầu dịch trực tiếp {len(segments)} câu bằng {provider_desc} "
        f"— Đa luồng: {max_workers} luồng song song với {num_keys} API Key ({total_batches} lô)..."
    )
    if reporter:
        reporter.emit("translate", "start", detail=f"0/{len(segments)} câu ({provider_desc})")

    translated_segments_map: Dict[int, dict] = {}
    completed_count = 0
    state_lock = threading.Lock()
    t_trans_start = time.time()

    pending_batches: List[Tuple[int, List[dict], str]] = []
    for idx, (b_idx, batch) in enumerate(batches):
        cached_batch = checkpoint.take(batch) if checkpoint else None
        if cached_batch is not None:
            for s in cached_batch:
                translated_segments_map[s["id"]] = s
            completed_count += len(batch)
        else:
            assigned_key = client.get_key(idx)
            pending_batches.append((b_idx, batch, assigned_key))

    if reporter and completed_count > 0:
        reporter.emit("translate", "progress", detail=f"{completed_count}/{len(segments)} câu")

    batch_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "INTEGER"},
                target.text_field: {"type": "STRING"},
            },
            "required": ["id", target.text_field],
        },
    }

    def _worker(b_idx: int, batch: List[dict], key: str):
        if reporter:
            reporter.check_cancelled()

        seg_ids = [s["id"] for s in batch]
        logger.info(f"  ▶ Lô {b_idx}/{total_batches} bắt đầu ({len(batch)} câu: {seg_ids[0]}..{seg_ids[-1]})")
        _t0 = time.time()

        payload_items = [payload_segment(s, cps_budget=cps) for s in batch]
        user_prompt = (
            f"Dịch các câu thoại sau sang {target.name} ({target.text_field}):\n"
            f"{json.dumps(payload_items, ensure_ascii=False)}"
        )

        translated_items = []
        last_err = None
        for try_i in range(3):
            try:
                cur_key = key if try_i == 0 else client.get_key()
                raw_reply = client.call_ai(
                    system_prompt,
                    user_prompt,
                    preferred_key=cur_key,
                    response_schema=batch_schema,
                )
                translated_items = parse_response_segments(raw_reply, text_field=target.text_field)
                if translated_items:
                    break
            except Exception as e:
                last_err = e
                time.sleep(1.0 * (try_i + 1))

        if not translated_items:
            # Fallback: dịch từng câu lẻ nếu cả lô bị lỗi. Các câu độc lập
            # nhau — chạy song song (executor.map giữ đúng thứ tự).
            logger.warning(f"  ⚠ Lô {b_idx} lỗi parse ({last_err}), đang chuyển sang dịch từng câu lẻ...")

            def _single(s):
                try:
                    s_payload = [payload_segment(s, cps_budget=cps)]
                    s_prompt = f"Dịch câu thoại sau sang {target.name} ({target.text_field}):\n{json.dumps(s_payload, ensure_ascii=False)}"
                    s_reply = client.call_ai(system_prompt, s_prompt, response_schema=batch_schema)
                    return parse_response_segments(s_reply, text_field=target.text_field) or []
                except Exception as s_err:
                    logger.warning(f"  ✗ Dịch câu #{s['id']} thất bại: {s_err}")
                    return []

            with ThreadPoolExecutor(max_workers=4) as pool:
                for items in pool.map(_single, batch):
                    translated_items.extend(items)

        trans_map = {item["id"]: item[target.text_field] for item in translated_items if "id" in item}
        batch_results = []
        for s in batch:
            sid = s["id"]
            txt = trans_map.get(sid, "")
            if not txt or _has_cjk(txt):
                # Nếu câu bị thiếu trong phản hồi của batch hoặc còn sót chữ CJK, thử dịch lại câu lẻ
                try:
                    s_payload = [payload_segment(s, cps_budget=cps)]
                    s_prompt = f"Dịch câu thoại sau sang {target.name} ({target.text_field}), không để lại chữ Hán:\n{json.dumps(s_payload, ensure_ascii=False)}"
                    s_reply = client.call_ai(system_prompt, s_prompt, response_schema=batch_schema)
                    s_items = parse_response_segments(s_reply, text_field=target.text_field)
                    if s_items and target.text_field in s_items[0]:
                        cand = s_items[0][target.text_field]
                        if cand and not _has_cjk(cand):
                            txt = cand
                except Exception as s_err:
                    logger.warning(f"  ✗ Dịch bù câu #{sid} thất bại: {s_err}")

            if not txt:
                txt = s.get("text", "")
            new_seg = dict(s)
            new_seg[target.text_field] = ensure_terminal_punct(txt)
            batch_results.append(new_seg)

        elapsed = time.time() - _t0
        nonlocal completed_count
        with state_lock:
            for s in batch_results:
                translated_segments_map[s["id"]] = s
            if checkpoint:
                checkpoint.put(batch_results)
            completed_count += len(batch)
            total_elapsed = time.time() - t_trans_start
            rate = completed_count / total_elapsed if total_elapsed > 0 else 0
            rem_count = max(0, len(segments) - completed_count)
            rem_s = rem_count / rate if rate > 0 else 0
            from autodub.utils import format_eta
            eta_info = f" (⏱ Đã chạy: {format_eta(total_elapsed)} | ETA: ~{format_eta(rem_s)})" if rem_count > 0 else f" (⏱ Tổng: {format_eta(total_elapsed)})"
            logger.info(f"  ✓ Lô {b_idx}/{total_batches} hoàn thành ({completed_count}/{len(segments)} câu) — {elapsed:.1f}s{eta_info}")
            if reporter:
                reporter.emit("translate", "progress", detail=f"{completed_count}/{len(segments)} câu")

    if pending_batches:
        if max_workers > 1:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    executor.submit(_worker, b_idx, batch, key)
                    for (b_idx, batch, key) in pending_batches
                ]
                for f in as_completed(futures):
                    try:
                        f.result()
                    except TranslateError as exc:
                        logger.warning(f"Lô dịch bị bỏ qua do lỗi: {exc}")
        else:
            for (b_idx, batch, key) in pending_batches:
                try:
                    _worker(b_idx, batch, key)
                except TranslateError as exc:
                    logger.warning(f"Lô dịch bị bỏ qua do lỗi: {exc}")

    results = [translated_segments_map.get(s["id"], s) for s in segments]

    # Hậu xử lý tự động chống sót chữ CJK (Tính năng cốt lõi của Gemini SRT)
    cjk_untranslated = [
        s for s in results
        if _has_cjk(s.get(target.text_field, ""))
    ]
    if cjk_untranslated:
        logger.info(f"[Hậu xử lý] Phát hiện {len(cjk_untranslated)} câu còn sót ký tự CJK — đang tiến hành dịch bù...")

        def _fix_cjk(s):
            try:
                single_payload = [payload_segment(s, cps_budget=cps)]
                re_prompt = (
                    f"Dịch câu thoại sau sang {target.name} ({target.text_field}), bắt buộc dịch hoàn toàn không để lại chữ Hán/Nhật/Hàn:\n"
                    f"{json.dumps(single_payload, ensure_ascii=False)}"
                )
                re_reply = client.call_ai(system_prompt, re_prompt)
                re_parsed = parse_response_segments(re_reply, text_field=target.text_field)
                if re_parsed and target.text_field in re_parsed[0]:
                    new_txt = re_parsed[0][target.text_field]
                    if new_txt and not _has_cjk(new_txt):
                        s[target.text_field] = ensure_terminal_punct(new_txt)
                        logger.info(f"  ✓ Đã dịch bù thành công câu #{s['id']}: {new_txt}")
            except Exception as exc:
                logger.warning(f"  ✗ Dịch bù câu #{s['id']} không thành công: {exc}")

        # Các câu độc lập — dịch bù song song thay vì từng câu tuần tự.
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(_fix_cjk, cjk_untranslated))

    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            os.remove(checkpoint_path)
        except OSError:
            pass

    if reporter:
        reporter.emit("translate", "done", detail=f"{len(results)} câu")
    return results
