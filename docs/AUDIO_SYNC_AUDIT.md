# AUDIO_SYNC_AUDIT

## 4.1. Repository map

- `autodub/pipeline.py`: Orchestrator (DubPipeline). Entry point for the core dubbing logic. Dependencies: transcribers, translators, TTS, timing, audio, video. Callers: GUI (`autodub_gui/workers.py`) or CLI.
- `autodub/speech/transcriber.py` & `asr_whisper_worker.py`: ASR implementation (Faster-Whisper). Outputs segments with `start`, `end`, `words`, `speech_start`, `speech_end`.
- `autodub/text/translate_direct.py` & `translate_browser.py`: Translation implementations (Gemini, OpenRouter, etc.). Takes ASR segments, adds `text_vi` (or target field) keeping the same timing.
- `autodub/speech/tts/`: TTS implementations (VieNeu, CapCut). Synthesizes Vietnamese audio from translated text.
- `autodub/media/timing.py`: Timing/alignment logic (`plan_voice_placements`, `apply_soft_timing`). Adjusts segment tempo and placement to fit the original Chinese speech slots.
- `autodub/media/audio.py`: Audio mixing/ducking (`merge_segments`, `postprocess_voice_clips`). Overlays Vietnamese voices on the background track, handles ducking.
- `autodub/media/vocal_separator.py`: Demucs audio separation. Splits original audio into `vocals.wav` and `no_vocals.wav`.
- `autodub/media/video.py`: FFmpeg export (`merge_video`). Combines original video, merged audio, subtitles, and effects.
- `autodub/text/srt.py` & `autodub/text/subtitles.py`: Subtitle generation (`refresh_subtitles`, `generate_srt_styled`).

## 4.2. Pipeline thực tế

Input Video
    ↓ (`autodub/pipeline.py`)
Audio Extraction (`autodub/media/audio.py:extract_audio`)
    ↓
Demucs (Audio Separation) (`autodub/media/vocal_separator.py:separate_vocals`)
    ↓
ASR (Whisper) (`autodub/speech/transcriber.py`)
    ↓
Diarization (`autodub/speech/diarization.py`)
    ↓
Translation (`autodub/text/translate_direct.py`)
    ↓
TTS (`autodub/speech/tts/`)
    ↓
Video Speed Adjustment (Optional) (`autodub/media/retime.py:apply_video_speed`)
    ↓
Timing (Tempo Adjustment & Placement) (`autodub/media/timing.py:apply_soft_timing`)
    ↓
Audio Mix (Ducking & Voice Overlay) (`autodub/media/audio.py:merge_segments`)
    ↓
Subtitle Generation (`autodub/text/subtitles.py:refresh_subtitles`)
    ↓
FFmpeg Export (`autodub/media/video.py:merge_video`)
    ↓
Output (`dubbed_video.mp4`)

## 5. Trace End-to-End

User selects video -> `autodub_gui/workers.py:DubWorker.run()`
    ↓
`autodub/pipeline.py`
Class: `DubPipeline`
Function: `run(req)` / `_run_impl(req)`
Input: `DubRequest(url, file_path, ...)`
Output: `DubResult(status, work_dir, ...)`
Called by: GUI Worker
Calls:
- `_asr_source()`: Extracts audio, runs Demucs, runs Whisper. Returns `segments`.
- `_translate_source()`: Runs translation API. Modifies `segments` in-place adding `text_vi`.
- `_synthesize_segments()`: Calls TTS. Generates `.wav` files in `segments/`.
- `apply_soft_timing()`: Adjusts start/end timestamps and stretches audio using `atempo`.
- `postprocess_voice_clips()`: Trims silence, normalizes, applies fades.
- `merge_segments()`: Mixes background with TTS clips.
- `refresh_subtitles()`: Generates `.srt`.
- `merge_video()`: Calls FFmpeg to assemble video, audio, and subtitles.

## 6. Audit Data Model

Speech segment representation (verified in code):
```python
{
    "id": 1,
    "start": 10.2,  # Actual timeline start (seconds)
    "end": 12.8,  # Actual timeline end (seconds)
    "text": "...",  # Original Chinese text
    "text_vi": "...",  # Translated Vietnamese text
    "speaker_id": 0,  # Int speaker ID
    "speech_start": 10.3,  # True start of speech from ASR/VAD (seconds)
    "speech_end": 12.7,  # True end of speech from ASR/VAD (seconds)
    "speech_duration": 2.4,  # Duration of active speech (seconds)
    "duration": 2.6,  # Original segment duration (seconds)
    "words": [...],  # Word-level timestamps (optional)
    "dub_start": 10.3,  # Final start after timing/merge
    "dub_end": 12.7,  # Final end after timing/merge
    "dub_duration": 2.4,  # Final TTS duration
    "tempo_factor": 1.0,  # Applied atempo
    "timing_adjustment": "none",
    "timing_reason": "",
}
```

## 7. Audit Timestamp System

Timestamps are stored as `float` representing `seconds` (e.g., `10.250`).
Source of truth during pipeline: The `segments` array (specifically `start` and `end` keys).
After `apply_soft_timing` and `merge_segments`, `seg["start"]` and `seg["end"]` represent the absolute timeline in seconds, which is then used by `refresh_subtitles` to generate SRT/ASS files.

## 8. Audit TTS Duration

TTS duration is calculated using `autodub.media.audio.wav_duration_s(wav_path)`.
Target duration is typically `speech_duration` or `end - start`.
The duration fitting is done in `autodub.media.timing.py:plan_voice_placements` and `autodub.media.voice_timing.py:_decide_tempo`.
- Uses `atempo` (tempo adjustment up to a max_speed, e.g., 1.15).
- Does not blindly squash. If TTS is too long, it sets `atempo` up to max limit. Any remaining duration spills over as "overlap" or uses available tail silence.
- Post-processing uses `trim_tts_silence` before measuring final duration to avoid stretching silence.

## 9. Mục Tiêu Audio Sync

The system aligns Vietnamese TTS with Chinese speech timelines using:
- `t = max(natural, prev_end + min_gap_s)`
- `natural` is derived from `speech_start` minus `pre_roll_s`.
- Overlaps are strictly prevented using an anti-collision check (`t < prev_actual_end + min_gap_safe`).

## 10. Duration Fitting Engine

Implemented in `plan_voice_placements` (`timing.py`) and `_decide_tempo` (`voice_timing.py`):
- Case A (TTS longer): Uses `atempo` (up to `max_speed`, default 1.15x). If still too long, spills over into silence before next clip or overlap is logged but limited.
- Case B (TTS shorter): Uses `atempo` (down to `min_speed`, default 0.9x) only if `VOICE_FIT_STRETCH` is enabled, otherwise natural duration is kept.

## 11. Overlap Handling

Currently, `plan_voice_placements` tries to serialize clips: `t = max(natural, prev_end + min_gap_s)`. It explicitly prevents true overlapping audio by delaying the start of the next clip (`prev_actual_end`).
If Speaker A and B overlap natively, the Vietnamese dub will push Speaker B to start after Speaker A finishes. True parallel mixing of voices is NOT supported by the current array-based concatenation/overlay logic in `merge_segments`.

## 12. Silence Handling

`plan_voice_placements` resolves "available slot" by checking the `speech_start` of the next segment. It allows a clip to overflow into the silence before the next clip, up to a safety gap (`min_gap_s`). It does not create continuous voice if there's silence.

## 13. Chinese Original Voice

Original audio is extracted to `original_audio.wav`.
Demucs separates it into `vocals.wav` and `no_vocals.wav` (`pipeline.py:721`).
If `bg_mode` is "demucs", `background_path` is `no_vocals.wav`.
If `bg_mode` is "duck" or "none", `background_path` is `original_audio.wav`.

## 14. Audio Mix Modes

Supported via `bg_mode` in `DubRequest`:
- `demucs`: Dub + Music/SFX (no original vocals).
- `duck`: Dub + Original Audio (ducked).
- `none`: Dub + Original Audio (no ducking, full volume).

## 15. Dynamic Ducking

Implemented in `merge_segments` (`audio.py`).
Uses `speech_intervals` (derived from `speech_start` to `speech_end` of all segments).
Applies `sidechaincompress` or `volume` filter dynamically during these intervals using `duck_attack_s` and `duck_release_s`.

## 16. Audio Normalization

`postprocess_voice_clips` (`audio.py`) applies a linear gain normalization using `compute_speech_gain_db` targeting `-16.0 LUFS` with True-Peak `-1.5 dBFS`.
It avoids `loudnorm` single-pass dynamic compression.
Sample rate of TTS (24kHz/44.1kHz) is preserved during stretching (`apply_formant_preserved_stretch`).

## 17. FFmpeg Audit

- `merge_video` (`video.py`): Uses `-filter_complex` for subtitles (`subtitles=`), blurring, scaling, watermark. Uses `setpts=PTS+...` for parallel chunked export.
- `merge_segments` (`audio.py`): Builds a complex `-filter_complex` with `adelay` for placing voice clips on the timeline, `amix` to mix voice tracks (max 64 inputs per amix chunk), and volume automation for ducking.

## 18. Drift Detection

`timing.py` anchors every segment to its `natural` start time (source of truth). It limits drift using `max_start_drift_s`. Thus, drift cannot accumulate globally across the video.

## 19. Sync Metrics

Present in `TimingReport` (`timing.py`):
- `segments_shifted`
- `max_shift_s`
- `segments_compressed`
- `segments_stretched`
- `segments_overlapped`
- `total_overlap_s`
Also in `quality_report.json` via `build_timing_guide`.

## 20. Testing

Current test suite uses `pytest`.
Has extensive tests in `tests/test_audio_merger.py`, `tests/test_timing_engine_invariants.py`, `tests/test_voice_stretch.py`.
