import wave
from unittest.mock import MagicMock, patch

import numpy as np

from autodub.config import Settings
from autodub.speech.transcriber import _transcribe_whisper


def test_transcribe_whisper_uses_batched_pipeline(tmp_path):
    # Valid 1s WAV file
    wav_path = str(tmp_path / "audio.wav")
    rate = 16000
    audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, rate)) * 1000).astype(np.int16)
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio_data.tobytes())

    settings = Settings()
    settings.whisper_model = "tiny"
    settings.whisper_beam_size = 1

    mock_model = MagicMock()
    mock_model.feature_extractor.sampling_rate = 16000
    mock_seg = MagicMock()
    mock_seg.text = "Hello world"
    mock_seg.start = 0.0
    mock_seg.end = 1.0
    mock_seg.words = []

    mock_info = MagicMock()
    mock_info.language = "en"
    mock_info.language_probability = 0.99
    mock_info.duration = 1.0

    mock_model.transcribe.return_value = ([mock_seg], mock_info)

    mock_batched = MagicMock()
    mock_batched.transcribe.return_value = ([mock_seg], mock_info)

    with (
        patch("autodub.speech.transcriber._load_whisper_model", return_value=(mock_model, "cuda")),
        patch("faster_whisper.BatchedInferencePipeline", return_value=mock_batched),
        patch("autodub.media.audio.wav_duration_s", return_value=1.0),
    ):
        segs = _transcribe_whisper(wav_path, "en", settings)

    assert len(segs) == 1
    assert segs[0]["text"] == "Hello world"
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] == 1.0
    mock_batched.transcribe.assert_called_once()
    assert mock_batched.transcribe.call_args[1]["batch_size"] == 16
