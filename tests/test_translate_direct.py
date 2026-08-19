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
