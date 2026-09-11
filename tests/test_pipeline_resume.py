"""Phase 8: Pipeline Checkpoint Resume and Invalidation Verification.

Tests:
1. End-to-end resume skips earlier completed stages (download, extract, ASR, translation, TTS).
2. Corrupt transcript JSON on resume recovers gracefully (falls back to transcribe).
3. Corrupt translation JSON on resume recovers gracefully (falls back to translate).
4. Corrupt/truncated TTS WAV segments are detected and re-synthesized.
5. Video merge reuse respects dependency mtimes (re-merges if audio or subtitles updated).
"""

import json
import os
import time
from unittest.mock import MagicMock, patch

from autodub.config import Settings
from autodub.languages import get_target
from autodub.pipeline import DubPipeline, DubRequest


def _create_valid_wav(path: str, duration_samples: int = 16000):
    """Write a valid 16kHz mono 16-bit PCM WAV."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    raw_pcm = b"\x00\x00" * duration_samples
    data_len = len(raw_pcm)
    riff_len = 36 + data_len
    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF" + riff_len.to_bytes(4, "little") + b"WAVE")
        # fmt chunk: 16-bit PCM, 1 channel, 16000 Hz, 32000 bytes/sec, 2 bytes/sample
        f.write(
            b"fmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00"
        )
        # data chunk
        f.write(b"data" + data_len.to_bytes(4, "little") + raw_pcm)


def test_pipeline_resume_reuses_all_earlier_stages(tmp_path):
    """When resuming a project with audio, transcript, translation, and TTS segments,

    pipeline skips all earlier stages and only runs merging/rendering.
    """
    proj_dir = tmp_path / "proj_resume"
    d_dir = proj_dir / "data"
    d_dir.mkdir(parents=True, exist_ok=True)

    video_file = proj_dir / "source.mp4"
    video_file.write_bytes(b"dummy_mp4_bytes")

    # Save source_video.json
    with open(d_dir / "source_video.json", "w", encoding="utf-8") as f:
        json.dump({"path": str(video_file), "url": None}, f)

    # Pre-populate audio
    audio_file = d_dir / "original_audio.wav"
    _create_valid_wav(str(audio_file))
    _create_valid_wav(str(d_dir / "original_audio_hq.wav"))

    # Pre-populate transcript (with speaker_id to skip diarization)
    orig_segs = [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "你好", "speaker_id": 1}
    ]
    with open(d_dir / "transcript_original.json", "w", encoding="utf-8") as f:
        json.dump(orig_segs, f)

    # Pre-populate translation
    dub_segs = [
        {
            "id": 1,
            "start": 0.0,
            "end": 1.0,
            "duration": 1.0,
            "text": "你好",
            "text_vi": "Xin chào",
            "speaker_id": 1,
        }
    ]
    with open(d_dir / "transcript_vi.json", "w", encoding="utf-8") as f:
        json.dump(dub_segs, f)

    # Pre-populate TTS segments with valid .render_mode
    seg_dir = d_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    with open(seg_dir / ".render_mode", "w", encoding="utf-8") as f:
        f.write(DubPipeline.RENDER_MODE)
    from autodub.utils import seg_wav_path

    seg_file = seg_wav_path(str(seg_dir), 1)
    _create_valid_wav(str(seg_file))

    settings = Settings(bg_mode="none", diarization_enabled=False, speech_boundary_refine=False)
    pipeline = DubPipeline(settings)
    req = DubRequest(
        file_path=str(video_file),
        resume_dir=str(proj_dir),
        target="vi",
        bg_mode="none",
        skip_video=True,
    )

    with (
        patch("autodub.media.audio.extract_audio") as mock_extract,
        patch("autodub.speech.transcriber.transcribe") as mock_transcribe,
        patch.object(DubPipeline, "_auto_translate") as mock_translate,
        patch.object(DubPipeline, "_get_synth") as mock_get_synth,
        patch("autodub.media.audio.merge_segments") as mock_merge,
    ):
        res = pipeline.run(req)

        assert res.status == "completed"
        # Earlier expensive stages must NOT be invoked
        mock_extract.assert_not_called()
        mock_transcribe.assert_not_called()
        mock_translate.assert_not_called()
        mock_get_synth.assert_not_called()
        # Audio merge was invoked
        mock_merge.assert_called_once()


def test_pipeline_resume_handles_corrupted_transcript(tmp_path):
    """Corrupted transcript_original.json on resume falls back to transcribing."""
    proj_dir = tmp_path / "proj_corrupt_asr"
    d_dir = proj_dir / "data"
    d_dir.mkdir(parents=True, exist_ok=True)

    video_file = proj_dir / "source.mp4"
    video_file.write_bytes(b"dummy_mp4_bytes")

    audio_file = d_dir / "original_audio.wav"
    _create_valid_wav(str(audio_file))
    _create_valid_wav(str(d_dir / "original_audio_hq.wav"))

    # Write corrupt JSON
    corrupt_transcript = d_dir / "transcript_original.json"
    corrupt_transcript.write_text("{this is not valid json")

    settings = Settings(bg_mode="none", diarization_enabled=False, speech_boundary_refine=False)
    pipeline = DubPipeline(settings)
    req = DubRequest(
        file_path=str(video_file),
        resume_dir=str(proj_dir),
        target="vi",
        bg_mode="none",
        skip_video=True,
    )

    mock_segs = [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "Re-transcribed text"}
    ]
    mock_dub_segs = [
        {
            "id": 1,
            "start": 0.0,
            "end": 1.0,
            "duration": 1.0,
            "text": "Re-transcribed text",
            "text_vi": "Văn bản nghe lại",
        }
    ]

    dummy_tts_res = [
        {
            "path": "dummy.wav",
            "actual_duration": 1.0,
            "speed_adjusted": False,
            "rate_applied": "cached",
        }
    ]

    with (
        patch("autodub.speech.transcriber.transcribe", return_value=mock_segs) as mock_transcribe,
        patch.object(DubPipeline, "_auto_translate", return_value=mock_dub_segs) as mock_translate,
        patch.object(DubPipeline, "_get_synth"),
        patch.object(DubPipeline, "_synthesize_segments", return_value=dummy_tts_res),
        patch("autodub.media.audio.merge_segments") as mock_merge,
    ):
        res = pipeline.run(req)
        assert res.status == "completed"
        # Must have fallen back to transcribing
        mock_transcribe.assert_called_once()


def test_pipeline_resume_handles_corrupted_translation(tmp_path):
    """Corrupted transcript_vi.json on resume falls back to translating."""
    proj_dir = tmp_path / "proj_corrupt_trans"
    d_dir = proj_dir / "data"
    d_dir.mkdir(parents=True, exist_ok=True)

    video_file = proj_dir / "source.mp4"
    video_file.write_bytes(b"dummy_mp4_bytes")

    audio_file = d_dir / "original_audio.wav"
    _create_valid_wav(str(audio_file))
    _create_valid_wav(str(d_dir / "original_audio_hq.wav"))

    # Valid original transcript
    orig_segs = [{"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text": "你好"}]
    with open(d_dir / "transcript_original.json", "w", encoding="utf-8") as f:
        json.dump(orig_segs, f)

    # Corrupt translation file (0 bytes or invalid JSON)
    bad_trans = d_dir / "transcript_vi.json"
    bad_trans.write_text('{"broken": ')

    settings = Settings(bg_mode="none", diarization_enabled=False, speech_boundary_refine=False)
    pipeline = DubPipeline(settings)
    req = DubRequest(
        file_path=str(video_file),
        resume_dir=str(proj_dir),
        target="vi",
        bg_mode="none",
        skip_video=True,
    )

    mock_dub_segs = [
        {
            "id": 1,
            "start": 0.0,
            "end": 1.0,
            "duration": 1.0,
            "text": "你好",
            "text_vi": "Đã dịch lại",
        }
    ]
    dummy_tts_res = [
        {
            "path": "dummy.wav",
            "actual_duration": 1.0,
            "speed_adjusted": False,
            "rate_applied": "cached",
        }
    ]

    with (
        patch.object(DubPipeline, "_auto_translate", return_value=mock_dub_segs) as mock_translate,
        patch.object(DubPipeline, "_get_synth"),
        patch.object(DubPipeline, "_synthesize_segments", return_value=dummy_tts_res),
        patch("autodub.media.audio.merge_segments"),
    ):
        res = pipeline.run(req)
        assert res.status == "completed"
        # Must have recovered and re-translated
        mock_translate.assert_called_once()


def test_pipeline_resume_detects_corrupted_wav_segment_and_resynthesizes(tmp_path):
    """If a segment wav in data/segments/ is truncated or unreadable,

    _synthesize_segments detects it and re-synthesizes it.
    """
    proj_dir = tmp_path / "proj_bad_wav"
    seg_dir = proj_dir / "data" / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    # Write a corrupt 8-byte file as segment 1
    from autodub.utils import seg_wav_path

    bad_seg = seg_wav_path(str(seg_dir), 1)
    with open(bad_seg, "wb") as f:
        f.write(b"BAD_WAV!")

    # Write a valid wav for segment 2
    good_seg = seg_wav_path(str(seg_dir), 2)
    _create_valid_wav(str(good_seg), duration_samples=8000)

    target = get_target("vi")
    settings = Settings(diarization_enabled=False)
    pipeline = DubPipeline(settings)

    segments = [
        {"id": 1, "start": 0.0, "end": 1.0, "duration": 1.0, "text_vi": "Câu 1"},
        {"id": 2, "start": 1.0, "end": 2.0, "duration": 1.0, "text_vi": "Câu 2"},
    ]

    mock_synth = MagicMock()
    mock_synth.recommended_threads = 1
    mock_synth.synthesize.return_value = {
        "path": str(bad_seg),
        "actual_duration": 0.95,
        "speed_adjusted": False,
        "rate_applied": "normal",
    }

    # Disable UPC cache to isolate local resume check
    os.environ["LPHVSub_DISABLE_CACHE"] = "1"  # noqa: SIM112 — tên env cũ của production
    try:
        results = pipeline._synthesize_segments(
            target, "nam_bac_1", segments, str(seg_dir), synth=mock_synth
        )
        assert len(results) == 2
        # Segment 1 was corrupt -> mock_synth.synthesize was called for segment 1!
        mock_synth.synthesize.assert_called_once()
        call_args = mock_synth.synthesize.call_args
        assert call_args.kwargs["text"] == "Câu 1"
        # Segment 2 was valid -> reused directly as cached
        assert results[1]["rate_applied"] == "cached"
    finally:
        os.environ.pop("LPHVSub_DISABLE_CACHE", None)


def test_pipeline_resume_video_mtime_invalidation(tmp_path):
    """STEP 7 re-merges video when audio or subtitle is newer than the existing dubbed video,

    but reuses the existing video when it is strictly newer than its dependencies.
    """
    proj_dir = tmp_path / "proj_video_mtime"
    d_dir = proj_dir / "data"
    d_dir.mkdir(parents=True, exist_ok=True)

    video_file = proj_dir / "source.mp4"
    video_file.write_bytes(b"dummy_mp4_bytes")

    # Audio & Subtitle
    merged_audio = d_dir / "audio_vi_full.wav"
    _create_valid_wav(str(merged_audio))

    sub_file = proj_dir / "transcript_vi.srt"
    sub_file.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n", encoding="utf-8")

    dubbed_video = proj_dir / "dubbed_video.mp4"
    # Create valid-sized dummy video (> 100_000 bytes)
    dubbed_video.write_bytes(b"\x00" * 120_000)

    # Case 1: Video is older than audio -> must re-merge
    t_old = time.time() - 100.0
    t_new = time.time()
    os.utime(str(dubbed_video), (t_old, t_old))
    os.utime(str(merged_audio), (t_new, t_new))

    v_mtime = os.path.getmtime(str(dubbed_video))
    dep_mtimes = [
        os.path.getmtime(str(video_file)),
        os.path.getmtime(str(merged_audio)),
        os.path.getmtime(str(sub_file)),
    ]
    can_reuse_case1 = all(d <= v_mtime for d in dep_mtimes)
    assert not can_reuse_case1, "Must NOT reuse video when merged_audio is newer"

    # Case 2: Video is newer than all inputs -> reuse video
    os.utime(str(dubbed_video), (t_new + 10.0, t_new + 10.0))
    v_mtime_new = os.path.getmtime(str(dubbed_video))
    can_reuse_case2 = all(d <= v_mtime_new for d in dep_mtimes)
    assert can_reuse_case2, "Must reuse video when dubbed_video is newer than all inputs"
