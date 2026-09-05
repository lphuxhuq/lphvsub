"""Unit tests cho ParaformerCache và chế độ --serve."""
import json
import os
import threading
from unittest import mock

import pytest

from autodub.config import Settings
from autodub.speech.paraformer_transcriber import ParaformerCache, transcribe_paraformer


class _FakePipeProc:
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.stdin = mock.MagicMock()
        self.poll_val = None
        self.lines = [json.dumps({"ready": True})] + [json.dumps(r) for r in responses]
        self._line_idx = 0

    def poll(self):
        return self.poll_val

    @property
    def stdout(self):
        class _Stdout:
            def __init__(inner):
                inner._idx = 0
            def readline(inner):
                if inner._idx < len(self.lines):
                    res = self.lines[inner._idx] + "\n"
                    inner._idx += 1
                    return res
                return ""
        return _Stdout()

    @property
    def stderr(self):
        return []

    def wait(self, timeout=None):
        return 0


def test_paraformer_cache_ensure_success(monkeypatch):
    cache = ParaformerCache()
    settings = Settings()

    proc = _FakePipeProc([])
    monkeypatch.setattr(settings, "paraformer_configured", lambda: True)
    monkeypatch.setattr("autodub.speech.paraformer_transcriber.subprocess.Popen", lambda *a, **k: proc)

    assert cache._ensure(settings) is True
    assert cache._proc is proc
    cache.close()


def test_paraformer_cache_transcribe_success(monkeypatch, tmp_path):
    dummy_wav = tmp_path / "test.wav"
    dummy_wav.write_bytes(b"RIFFdummyWAVEfmt ")

    responses = [
        {"seg": True, "text": "你好世界", "start": 0.5, "end": 2.0},
        {"empty": True, "start": 2.5, "end": 3.0},
        {"seg": True, "text": "再见", "start": 3.2, "end": 4.1},
        {"done": True, "num_segments": 2, "num_empty": 1},
    ]
    proc = _FakePipeProc(responses)

    settings = Settings()
    monkeypatch.setattr(settings, "paraformer_configured", lambda: True)
    monkeypatch.setattr("autodub.speech.paraformer_transcriber.subprocess.Popen", lambda *a, **k: proc)

    cache = ParaformerCache()
    meta = {}
    segments = cache.transcribe(str(dummy_wav), settings, meta=meta)

    assert segments is not None
    assert len(segments) == 2
    assert segments[0]["text"] == "你好世界"
    assert segments[0]["start"] == 0.5
    assert segments[0]["end"] == 2.0
    assert segments[1]["text"] == "再见"
    assert meta["empty_chunks"] == [{"start": 2.5, "end": 3.0}]
    cache.close()


def test_transcribe_paraformer_uses_cache(monkeypatch, tmp_path):
    dummy_wav = tmp_path / "test.wav"
    dummy_wav.write_bytes(b"RIFFdummyWAVEfmt ")

    settings = Settings()
    mock_cache = mock.Mock(spec=ParaformerCache)
    mock_cache.transcribe.return_value = [{"id": 1, "text": "测试", "start": 0.0, "end": 1.0, "duration": 1.0}]

    segs = transcribe_paraformer(str(dummy_wav), settings, paraformer_cache=mock_cache)
    assert segs == [{"id": 1, "text": "测试", "start": 0.0, "end": 1.0, "duration": 1.0}]
    mock_cache.transcribe.assert_called_once()
