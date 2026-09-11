import os

import autodub.pipeline_cache as pc
from autodub.config import Settings
from autodub.languages import get_target
from autodub.pipeline import DubPipeline, DubRequest
from autodub.workdir import data_dir, data_path


def _create_dummy_wav(path: str):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(
            b"RIFF\x24\x01\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x01\x00\x00"
            + b"\x55" * 256
        )


def test_upc_and_local_resume_coexistence(tmp_path):
    """Test that local work_dir resume takes priority, and UPC provides cross-project fallback."""
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video_bytes_content_sample")

    proj1_dir = str(tmp_path / "proj1")
    proj2_dir = str(tmp_path / "proj2")
    os.makedirs(data_dir(proj1_dir), exist_ok=True)
    os.makedirs(data_dir(proj2_dir), exist_ok=True)

    target = get_target("vi")
    settings = Settings()
    pipeline = DubPipeline(settings)

    # Pre-populate proj1 with local transcript
    local_transcript = data_path(proj1_dir, "transcript_original.json")
    from autodub.speech.transcriber import save_transcript

    orig_segs = [{"id": 1, "start": 0.0, "end": 1.0, "text": "Local Line 1"}]
    save_transcript(orig_segs, local_transcript)

    # Also populate UPC cache with a different transcript for the same audio
    audio_path = str(tmp_path / "audio.wav")
    _create_dummy_wav(audio_path)
    upc_segs = [{"id": 1, "start": 0.0, "end": 1.0, "text": "UPC Line 1"}]
    pc.get_asr_cache().store(audio_path, "base", "zh", "whisper", upc_segs)

    # 1. When resuming proj1, local transcript must win
    req1 = DubRequest(file_path=str(video), resume_dir=proj1_dir)
    assert os.path.exists(local_transcript)

    # 2. When creating proj2 (new directory, no local transcript), UPC cache must be used
    req2 = DubRequest(file_path=str(video), resume_dir=proj2_dir)
    proj2_local = data_path(proj2_dir, "transcript_original.json")
    assert not os.path.exists(proj2_local)

    # Simulate Step 3 lookup in proj2
    cached = pc.get_asr_cache().lookup(audio_path, "base", "zh", "whisper")
    assert cached == upc_segs
    assert cached[0]["text"] == "UPC Line 1"


def test_mid_run_interruption_leaves_cache_untainted(tmp_path):
    """A crashed/interrupted step must not leave corrupt entries in UPC cache."""
    audio = str(tmp_path / "crash_audio.wav")
    _create_dummy_wav(audio)

    # Try storing non-existent or 0-byte stems in demucs
    fake_vocals = str(tmp_path / "nonexistent_vocals.wav")
    fake_no_vocals = str(tmp_path / "nonexistent_no_vocals.wav")
    pc.get_demucs_cache().store_result(audio, fake_vocals, fake_no_vocals, "htdemucs", 44100, 2)

    # Lookup should still be None
    assert (
        pc.get_demucs_cache().lookup_and_restore(audio, str(tmp_path / "out"), "htdemucs", 44100, 2)
        is None
    )

    # Try storing non-WAV in TTS cache
    bad_wav = tmp_path / "bad.wav"
    bad_wav.write_bytes(b"NOT_A_WAV")
    pc.get_tts_cache().store("some text", "nam_bac_1", str(bad_wav))

    # Lookup should still be None
    assert pc.get_tts_cache().lookup("some text", "nam_bac_1") is None
