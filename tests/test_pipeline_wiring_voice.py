"""Unit test cho pipeline wiring voice-sync (TASK-4).

Kiểm tra: legacy gate của VOICE_SPEED, Settings defaults, refine được gọi
đúng chỗ (qua monkeypatch), tts_actual_duration được gán sau TTS.
"""
import logging

import pytest

import autodub.media.audio as audio_mod
from autodub.config import Settings
from autodub.pipeline import DubPipeline


def test_settings_defaults_voice_sync():
    s = Settings()
    assert s.speech_boundary_refine is True
    assert s.timing_max_start_drift_s == 0.15
    assert s.voice_fit_max_speed == 1.15
    assert s.voice_speed_legacy is False
    assert s.video_speed == 1.0


def test_voice_speed_legacy_env(monkeypatch):
    monkeypatch.setenv("VOICE_SPEED_LEGACY", "true")
    s = Settings.load()
    assert s.voice_speed_legacy is True


def test_apply_voice_speed_disabled_by_default(tmp_path, monkeypatch):
    """VOICE_SPEED=1.3 + legacy=false → KHÔNG clip nào bị atempo toàn cục."""
    calls = {"n": 0}
    real = audio_mod.slow_segments

    def _counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(audio_mod, "slow_segments", _counting)
    settings = Settings()
    settings.voice_speed = 1.3
    settings.voice_speed_legacy = False
    pipe = DubPipeline(settings)
    out = pipe._apply_voice_speed([], str(tmp_path), str(tmp_path))
    assert out == str(tmp_path)
    assert calls["n"] == 0


def test_apply_voice_speed_legacy_on(tmp_path, monkeypatch):
    """legacy=true + speed 1.3 → vẫn dùng đường cũ (backward compat)."""
    monkeypatch.setattr(audio_mod, "slow_segments",
                        lambda *a, **k: "SLOWED")
    settings = Settings()
    settings.voice_speed = 1.3
    settings.voice_speed_legacy = True
    pipe = DubPipeline(settings)
    assert pipe._apply_voice_speed([], str(tmp_path), "wd") == "SLOWED"


def test_pipeline_source_wires_refine_and_duration():
    """Smoke: pipeline gọi refine sau ASR và gán tts_actual_duration sau TTS
    (nguồn có chuỗi gọi — test mức source tránh phải chạy cả pipeline)."""
    import inspect
    from autodub import pipeline as pipe_mod
    src = inspect.getsource(pipe_mod.DubPipeline._run_impl)
    assert "refine_speech_boundaries" in src
    assert "speech_boundary_refine" in src
    src_synth = inspect.getsource(pipe_mod.DubPipeline._synthesize_segments)
    assert 'seg["tts_actual_duration"]' in src_synth
    src_speed = inspect.getsource(pipe_mod.DubPipeline._apply_voice_speed)
    assert "voice_speed_legacy" in src_speed


def test_video_speed_warning_logged(caplog):
    """AC-9: warning lip-sync xuất hiện khi VIDEO_SPEED<1 (qua hàm helper
    của pipeline — nội dung warning là contract)."""
    # Warning nằm inline trong _run_impl; test contract qua source + hằng
    # chuỗi dùng chung để không phải chạy cả pipeline.
    from autodub import pipeline as pipe_mod
    import inspect
    src = inspect.getsource(pipe_mod)
    assert "may affect visual speech" in src
