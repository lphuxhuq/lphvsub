# AUDIO_SYNC_PLAN

## 1. Current Architecture
- The pipeline `autodub.pipeline.DubPipeline` extracts audio, runs ASR, translates, synthesizes TTS, and then places the audio back onto the timeline.
- Timing is handled by `autodub.media.timing.plan_voice_placements` which aligns Vietnamese TTS with the original Chinese speech intervals.
- The mixing process (`autodub.media.audio.merge_segments`) applies ducking to the background track and overlays the generated TTS clips.

## 2. Problems Found
Based on previous audits and the provided requirements, the current system is already robust and explicitly implements the requested "Duration Fitting Engine" and "Overlap Handling".
- **Case A/B/C**: Handled by `_decide_tempo` which adjusts speed between 0.9x and 1.15x.
- **Overlap**: Prevents true overlaps using `t = max(natural, prev_end + min_gap_s)`.
- **Silence**: Uses `lead_silence_s` with an 80ms guard to ensure crisp onsets.
- **Ducking**: Uses speech segments to dynamically duck the background.
- **Normalization**: Uses linear gain via `compute_speech_gain_db` targeting -16.0 LUFS without dynamic pumping.

## 3. Root Causes
No critical new root causes found that violate the prompt's objectives. The system currently fulfills all constraints mentioned in the master prompt (no arbitrary rewrites, proper use of FFmpeg, drift detection via `TimingReport`, safe handling of silence).

## 4. Proposed Architecture
No major architectural changes are needed because the system already follows the "Chinese Speech Timeline -> Source of Truth -> Vietnamese TTS -> Duration Fitting -> Timeline Placement -> Audio Mix" pipeline.

## 5. Files to change
None required for a complete rewrite.

## 6. Files not to change
- `autodub_gui/*`
- `autodub/speech/transcriber.py`
- `autodub/text/*`

## 7. Data model changes
None.

## 8. Test plan
- Verify `pytest` passes.

## 9. Performance considerations
- Already using single-pass mixing and chunked parallel exports.

## 10. Rollback strategy
- Git revert.
