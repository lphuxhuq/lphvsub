import json
import pytest
from autodub.config import Settings
from autodub.languages import get_target
from autodub.text.translate_direct import (
    GeminiDirectClient,
    _repair_json,
    _strip_fences_and_citations,
    parse_response_segments,
    translate_segments_direct,
)


def test_strip_fences_and_citations():
    text = "```json\n[{\"id\": 1, \"text_vi\": \"Xin chào.\"}[cite: 3]]\n```"
    cleaned = _strip_fences_and_citations(text)
    assert "[cite:" not in cleaned
    assert "```" not in cleaned


def test_repair_json_unterminated_array():
    raw = '[{"id": 1, "text_vi": "Câu một."}, {"id": 2, "text_vi": "Câu hai.'
    repaired = _repair_json(raw)
    data = json.loads(repaired)
    assert len(data) >= 1
    assert data[0]["id"] == 1


def test_parse_response_segments_handles_dict_and_list():
    raw_list = '[{"id": 1, "text_vi": "Xin chào."}]'
    res = parse_response_segments(raw_list, text_field="text_vi")
    assert len(res) == 1
    assert res[0]["text_vi"] == "Xin chào."

    raw_dict = '{"segments": [{"id": 2, "translation": "Tạm biệt."}]}'
    res2 = parse_response_segments(raw_dict, text_field="text_vi")
    assert len(res2) == 1
    assert res2[0]["text_vi"] == "Tạm biệt."


def test_gemini_direct_client_key_rotation(monkeypatch):
    client = GeminiDirectClient("key1, key2", model="gemini-2.5-flash")
    assert len(client.keys) == 2
    assert client.get_key(0) == "key1"
    assert client.get_key(1) == "key2"
    assert client.get_key() == "key1"
    client.rotate_key()
    assert client.get_key() == "key2"


def test_translate_segments_direct_parallel_multi_keys(monkeypatch, tmp_path):
    settings = Settings(
        gemini_api_key="key_1, key_2, key_3",
        gemini_model="gemini-2.5-flash",
        translate_batch_size=2,
    )
    segments = [
        {"id": 1, "text": "Sentence 1", "start": 0.0, "end": 2.0, "duration": 2.0},
        {"id": 2, "text": "Sentence 2", "start": 2.5, "end": 4.5, "duration": 2.0},
        {"id": 3, "text": "Sentence 3", "start": 5.0, "end": 7.0, "duration": 2.0},
        {"id": 4, "text": "Sentence 4", "start": 7.5, "end": 9.5, "duration": 2.0},
        {"id": 5, "text": "Sentence 5", "start": 10.0, "end": 12.0, "duration": 2.0},
        {"id": 6, "text": "Sentence 6", "start": 12.5, "end": 14.5, "duration": 2.0},
    ]

    keys_used = set()

    def _mock_call(self, system_instruction, user_prompt, preferred_key=None, max_retries=4):
        if preferred_key:
            keys_used.add(preferred_key)
        # Trích xuất id từ prompt
        try:
            items_str = user_prompt.split(":\n", 1)[1]
            items = json.loads(items_str)
            return json.dumps([{"id": item["id"], "text_vi": f"Dịch câu {item['id']}"} for item in items])
        except Exception:
            return json.dumps([])

    monkeypatch.setattr(GeminiDirectClient, "call_ai", _mock_call)

    target = get_target("vi")
    translated = translate_segments_direct(
        segments, target, "en", settings,
        checkpoint_path=str(tmp_path / "ckpt_parallel.json"),
    )

    assert len(translated) == 6
    for i, seg in enumerate(translated, 1):
        assert seg["text_vi"] == f"Dịch câu {i}."

    # Xác nhận các key khác nhau đều được chia luồng chạy
    assert len(keys_used) >= 2


def test_get_direct_client_prioritizes_gemini():
    from autodub.text.translate_direct import get_direct_client, GeminiDirectClient
    settings = Settings(
        gemini_api_key="AIzaSyTestKey123",
        gemini_model="gemini-2.5-flash",
    )
    client, desc = get_direct_client(settings)
    assert isinstance(client, GeminiDirectClient)
    assert "Google Gemini" in desc
    assert client.keys == ["AIzaSyTestKey123"]
    assert client.model == "gemini-2.5-flash"


def test_parse_response_segments_with_thoughts_and_reversed_keys():
    raw_with_thoughts = (
        "I'm currently focused on the translation parameters. I've noted the source is Mandarin Chinese...\n\n"
        "```json\n"
        "[\n"
        '  {"text_vi": "Hà Nhân vừa hưởng lạc đêm xuân xong thì bị Ngự sử tố cáo.", "id": 1},\n'
        '  {"id": 2, "text_vi": "Lại thêm một kẻ mang chứng cứ định đuổi anh khỏi kinh thành."}\n'
        "]\n"
        "```\n"
        "Here is the finalized translation."
    )
    res = parse_response_segments(raw_with_thoughts, text_field="text_vi")
    assert len(res) == 2
    assert res[0]["id"] == 1
    assert "Hà Nhân" in res[0]["text_vi"]
    assert res[1]["id"] == 2



# ----------------------------------------------- speedup: plan/workers/thinking #

def test_plan_batches_splits_for_workers():
    """38 câu, batch 40, 4 luồng → phải chia 4 lọ cân bằng thay vì 1 lô khổng lồ."""
    from autodub.text.translate_direct import _plan_batches
    spans = _plan_batches(38, batch_size=40, workers=4, floor=8)
    assert len(spans) == 4
    sizes = [e - s for _b, s, e in spans]
    assert sizes == [10, 10, 9, 9]
    # phủ kín, không chồng lấn
    assert spans[0][1] == 0 and spans[-1][2] == 38
    for (_b1, _s1, e1), (_b2, s2, _e2) in zip(spans, spans[1:]):
        assert e1 == s2


def test_plan_batches_respects_floor_when_short():
    """Ít câu hơn floor → không chia lẻ được, giữ 1 lô."""
    from autodub.text.translate_direct import _plan_batches
    spans = _plan_batches(6, batch_size=40, workers=4, floor=8)
    assert spans == [(1, 0, 6)]


def test_plan_batches_keeps_normal_batching():
    from autodub.text.translate_direct import _plan_batches
    spans = _plan_batches(100, batch_size=25, workers=4, floor=8)
    assert len(spans) == 4
    assert all(e - s == 25 for _b, s, e in spans)
    # 1 luồng → số lô theo batch_size, chia cân bằng (mỗi lô ≤ batch_size)
    spans1 = _plan_batches(20, batch_size=6, workers=1, floor=8)
    assert len(spans1) == 4
    assert all(e - s == 5 for _b, s, e in spans1)


def test_default_workers():
    from autodub.text.translate_direct import _default_workers
    assert _default_workers(1, 0, is_compat=False) == 2   # 1 key vẫn 2 luồng
    assert _default_workers(9, 0, is_compat=False) == 4
    assert _default_workers(1, 0, is_compat=True) == 2
    assert _default_workers(1, 5, is_compat=False) == 5   # cấu hình đè
    assert _default_workers(1, 99, is_compat=False) == 8  # trần 8


class _FakeResp:
    status_code = 200
    text = ""

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]}


def _capture_payload(model, thinking=False):
    from autodub.text.translate_direct import GeminiDirectClient as G
    client = G("k1", model=model, thinking=thinking)
    captured = {}

    class _Sess:
        def post(self, url, params=None, headers=None, json=None, timeout=None):
            captured["payload"] = json
            return _FakeResp()

    client.session = _Sess()
    client.call_ai("sys", "prompt")
    return captured["payload"]


def test_thinking_disabled_for_25_flash():
    cfg = _capture_payload("gemini-2.5-flash")["generationConfig"]
    assert cfg["thinkingConfig"] == {"thinkingBudget": 0}
    assert cfg["maxOutputTokens"] == 16384


def test_thinking_not_sent_for_15_models():
    # Model 1.5 từ chối field lạ (400) — không được gửi thinkingConfig.
    cfg = _capture_payload("gemini-1.5-flash")["generationConfig"]
    assert "thinkingConfig" not in cfg


def test_thinking_not_sent_for_25_pro():
    # 2.5-pro không cho tắt thinking (floor 128) — không gửi budget 0.
    cfg = _capture_payload("gemini-2.5-pro")["generationConfig"]
    assert "thinkingConfig" not in cfg


def test_thinking_setting_reenables():
    cfg = _capture_payload("gemini-2.5-flash", thinking=True)["generationConfig"]
    assert "thinkingConfig" not in cfg


def test_get_direct_client_passes_thinking_setting():
    from autodub.text.translate_direct import get_direct_client
    client_on, _ = get_direct_client(Settings(
        gemini_api_key="AIzaSyTestKey123", translate_thinking=True))
    assert client_on.thinking is True
    client_off, _ = get_direct_client(Settings(
        gemini_api_key="AIzaSyTestKey123"))
    assert client_off.thinking is False
