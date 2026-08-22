"""Unit test cho parse protocol JSON-lines của Paraformer worker driver.

Feed các dòng stdout giả vào transcribe_paraformer qua Popen fake — không
cần .venv-asr thật.
"""
import json

import pytest

from autodub.config import Settings
from autodub.speech import paraformer_transcriber as pt


class _FakeProc:
    returncode = 0

    def __init__(self, lines):
        self.stdout = iter(lines)
        self.stderr = iter([])

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def _run(monkeypatch, lines, meta=None, settings=None):
    """Chạy transcribe_paraformer với Popen fake; trả (segments, cmd)."""
    settings = settings or Settings()
    proc = _FakeProc(lines)
    captured: dict = {}

    def _popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return proc

    monkeypatch.setattr(pt.subprocess, "Popen", _popen)
    segments = pt.transcribe_paraformer("no_such_file.wav", settings, meta=meta)
    return segments, captured["cmd"]


def test_protocol_with_empty_chunks(monkeypatch):
    lines = [
        json.dumps({"ready": True}),
        json.dumps({"seg": True, "text": "你为什么不告诉我", "start": 1.02, "end": 4.31}),
        json.dumps({"empty": True, "start": 5.0, "end": 6.4}),
        json.dumps({"seg": True, "text": "我很好", "start": 7.5, "end": 8.9}),
        json.dumps({"done": True, "num_segments": 2, "num_empty": 1}),
    ]
    meta = {}
    segments, _cmd = _run(monkeypatch, lines, meta=meta)

    assert len(segments) == 2
    assert segments[0]["text"] == "你为什么不告诉我"
    assert segments[0]["start"] == 1.02
    assert segments[0]["duration"] == round(4.31 - 1.02, 3)
    assert segments[1]["id"] == 2
    assert meta["empty_chunks"] == [{"start": 5.0, "end": 6.4}]


def test_old_protocol_without_empty_key(monkeypatch):
    """Worker cũ không bao giờ emit key mới — driver vẫn phải chạy bình thường."""
    lines = [
        json.dumps({"seg": True, "text": "早安", "start": 0.0, "end": 1.0}),
        json.dumps({"done": True, "num_segments": 1}),
    ]
    meta = {}
    segments, _cmd = _run(monkeypatch, lines, meta=meta)

    assert len(segments) == 1
    assert meta["empty_chunks"] == []


def test_meta_none_ignores_empty_messages(monkeypatch):
    lines = [
        json.dumps({"empty": True, "start": 5.0, "end": 6.4}),
        json.dumps({"seg": True, "text": "你好", "start": 7.0, "end": 8.0}),
        json.dumps({"done": True, "num_segments": 1, "num_empty": 1}),
    ]
    segments, _cmd = _run(monkeypatch, lines, meta=None)

    assert len(segments) == 1


def test_cmd_carries_vad_pad(monkeypatch):
    settings = Settings()
    settings.asr_vad_pad_s = 0.45
    lines = [json.dumps({"done": True, "num_segments": 0, "num_empty": 0})]
    proc_cmd = {}

    def _popen(cmd, **kwargs):
        proc_cmd["cmd"] = cmd
        return _FakeProc(lines)

    monkeypatch.setattr(pt.subprocess, "Popen", _popen)
    with pytest.raises(RuntimeError, match="không nhận dạng được câu nào"):
        pt.transcribe_paraformer("no_such_file.wav", settings, meta=None)
    assert "--vad-pad" in proc_cmd["cmd"]
    assert proc_cmd["cmd"][proc_cmd["cmd"].index("--vad-pad") + 1] == "0.45"


def test_error_message_raises(monkeypatch):
    lines = [json.dumps({"ready": True}),
             json.dumps({"error": "missing model file: x"})]
    with pytest.raises(RuntimeError, match="missing model file"):
        _run(monkeypatch, lines)


def test_no_done_message_raises(monkeypatch):
    lines = [json.dumps({"seg": True, "text": "你", "start": 0.0, "end": 0.5})]
    with pytest.raises(RuntimeError, match="thoát bất thường"):
        _run(monkeypatch, lines)


def test_no_segments_raises(monkeypatch):
    lines = [json.dumps({"done": True, "num_segments": 0, "num_empty": 2})]
    with pytest.raises(RuntimeError, match="không nhận dạng được câu nào"):
        _run(monkeypatch, lines)
