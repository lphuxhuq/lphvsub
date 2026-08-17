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

    # 1. Thử parse JSON chuẩn hoặc JSON đã sửa
    for candidate in (raw, _slice_to_payload(raw), _repair_json(raw)):
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

    # 2. Fallback: Parse theo dạng dòng đánh số "1. Lời thoại..."
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


def _build_system_prompt(target_field: str = "text_vi", style_notes: str = "") -> str:
    prompt = f"""Bạn là chuyên gia dịch thuật và chuyển thể lồng tiếng video sang tiếng Việt tự nhiên cho AI TTS.
Dịch các câu thoại đầu vào sang tiếng Việt tự nhiên, ngắn gọn, khớp thời lượng nói, không dịch thô cứng hay sót chữ Hán, số viết thành chữ để đọc (ví dụ 100 -> một trăm).
Bắt buộc trả về đúng định dạng mảng JSON duy nhất:
[
  {{"id": 1, "{target_field}": "Bản dịch tiếng Việt."}}
]
Không giải thích, không thêm chữ ngoài mảng JSON."""
    if style_notes and style_notes.strip():
        prompt += f"\n\n### Ngữ cảnh & Văn phong:\n{style_notes.strip()}"
    return prompt


class GeminiDirectClient:
    """Gọi trực tiếp Google Gemini API với cơ chế luân chuyển nhiều API Key và Fallback Model."""

    def __init__(self, api_keys: List[str] | str, model: str = "gemini-2.5-flash", timeout_s: int = 120):
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
    ) -> str:
        models = [self.model] + [m for m in _FALLBACK_GEMINI_MODELS if m != self.model]
        model_idx = 0
        current_key = preferred_key or self.get_key()

        for attempt in range(max_retries):
            KEY_LIMITER.acquire(current_key)
            current_model = models[model_idx]
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent"

            payload = {
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "responseMimeType": "application/json",
                },
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
    ) -> str:
        current_key = preferred_key or self.get_key()
        # Fallback model nếu model chính bị nghẽn trên HHTech proxy
        fallback_models = [self.model]
        if "hhtech" in self.endpoint:
            for alt in ("deepseek-v4-pro", "grok-4.6"):
                if alt not in fallback_models:
                    fallback_models.append(alt)

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
            payload = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
                "stream": True,  # Stream để không bị timeout giữa chừng khi proxy bận
            }

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
    """Khởi tạo client AI phù hợp dựa trên cài đặt của người dùng."""
    # 1. Custom AI / HHTech API
    custom_key = getattr(settings, "custom_ai_api_key", "").strip()
    if custom_key:
        base_url = getattr(settings, "custom_ai_base_url", "https://hhtechapi.net/v1").strip() or "https://hhtechapi.net/v1"
        model = getattr(settings, "custom_ai_model", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
        return OpenAICompatDirectClient(custom_key, base_url=base_url, model=model), f"Custom/HHTech ({model})"

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

    # 5. Gemini API
    gemini_key = getattr(settings, "gemini_api_key", "").strip()
    if gemini_key:
        model = getattr(settings, "gemini_model", "gemini-2.5-flash")
        return GeminiDirectClient(gemini_key, model=model), f"Google Gemini ({model})"

    raise ValueError("Chưa cấu hình API Key dịch thuật nào trong Cài đặt.")


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

    batches: List[Tuple[int, List[dict]]] = []
    for i in range(0, len(segments), batch_size):
        b_idx = (i // batch_size) + 1
        batches.append((b_idx, segments[i:i + batch_size]))

    total_batches = len(batches)
    num_keys = len(client.keys)
    # Với proxy bên thứ 3 (HHTech), cho phép 2 luồng song song dù chỉ có 1 key
    # để lô bị kẹt không chặn toàn bộ pipeline mà không quá tải proxy
    if is_compat:
        max_workers = min(2, total_batches)
    else:
        max_workers = max(1, min(num_keys, 4, total_batches))

    checkpoint = (
        TranslateCheckpoint(checkpoint_path, text_field=target.text_field)
        if checkpoint_path
        else None
    )

    system_prompt = _build_system_prompt(
        target_field=target.text_field,
        style_notes=getattr(settings, "translate_style_notes", ""),
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

        raw_reply = client.call_ai(system_prompt, user_prompt, preferred_key=key)
        translated_items = parse_response_segments(raw_reply, text_field=target.text_field)

        trans_map = {item["id"]: item[target.text_field] for item in translated_items if "id" in item}
        batch_results = []
        for s in batch:
            sid = s["id"]
            txt = trans_map.get(sid, "")
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
            logger.info(f"  ✓ Lô {b_idx}/{total_batches} hoàn thành ({completed_count}/{len(segments)} câu) — {elapsed:.1f}s")
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

    if checkpoint_path and os.path.exists(checkpoint_path):
        try:
            os.remove(checkpoint_path)
        except OSError:
            pass

    if reporter:
        reporter.emit("translate", "done", detail=f"{len(results)} câu")
    return results
