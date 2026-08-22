# VOICE SYNC — REVERSE ENGINEERING REPORT

> Nhiệm vụ: sửa "voice lồng tiếng Việt không khớp với hình/video". Báo cáo Phase 1 (call chain) + Phase 2 (root cause, xác nhận bằng code). Không sửa code trong phase này.
> Ngày: 2026-08-22 · Repo: lphvsub-main (đã có grep/đọc trực tiếp mọi file liệt kê trong spec; `asr_paraformer_worker.py` được đọc toàn bộ trong task trước).

## 1. Call chain thực tế (ĐÃ XÁC MINH)

```text
Video (Step 1: _resolve_video, pipeline.py:1372)
 ↓ Step 2: extract_audio_dual — media/audio.py:147 → 16k mono (ASR) + 44.1k (HQ)
 ↓ Step 2.5: _resolve_background (pipeline.py:1438) → Demucs vocals/no_vocals (async)
 ↓ Step 3: transcribe (speech/transcriber.py:158)
 │   Paraformer: asr_paraformer_worker.py — VAD chunk → decode → JSON-lines
 │   → paraformer_transcriber.py:26 build segments {id,text,start,end,duration}
 │   → split_long_segments (transcriber.py:476) → transcript_original.json
 ↓ Step 3.5: annotate_slots (text/translate_hint.py:68) — gán seg["slot"] (budget ký tự)
 ↓ Step 4: _auto_translate (pipeline.py:1150) → seg["text_vi"] (timeline GỐC)
 ↓ Step 5: _synthesize_segments (pipeline.py:1533)
 │   mỗi câu: synth.synthesize(text, path, target_duration=None)  ← pipeline.py:1631-1637
 │   TTSResult{path, actual_duration, speed_adjusted, rate_applied}  ← tts/base.py:8
 │   vieneu_vi.py:340-344 / capcut_vi.py:316-319: actual_duration = ĐO WAV THẬT ✓
 ↓ Step 5.5 (chỉ khi VIDEO_SPEED<0.999): apply_video_speed/defer_video_speed (retime.py:151/233)
 │   rescale_segments (retime.py:125-134) MUTATE start/end/duration ×scale
 │   → segments giờ nằm trên timeline RETIMED; _refresh_subs làm lại SRT
 ↓ Step 6a: postprocess_voice_clips (audio.py:314) — loudnorm + fade + [VOICE_SPEED atempo]
 │   HOẶC _apply_voice_speed (pipeline.py:1697) → slow_segments (audio.py:181) — atempo toàn cục
 ↓ Step 6b: apply_soft_timing (media/timing.py:132)
 │   plan_placements (timing.py:62): shift vào silence (trần max_drift 1.5s/segment)
 │   + atempo ép buộc ≤1.1 khi câu sau sắp vượt trần drift của nó
 │   MUTATE seg["start"]/["end"] = timeline thật; GIỮ seg["duration"] = nguồn (timing.py:189-191)
 ↓ Step 6c: merge_segments (audio.py:485)
 │   numpy block-mixer: đặt clip tại seg["start"] + ĐO header WAV lấy duration (audio.py:555-564)
 │   → KHÔNG đọc seg["duration"], KHÔNG adelay  ← placement đúng theo (start, wav thật)
 ↓ Step 7: merge_video (media/video.py:193) — mux + burn subs/blur (+setpts deferred)
```

## 2. Bảng function — timestamp source / modification

| Function (file:line) | Input | Output | Timestamp source | Sửa timestamp? |
|---|---|---|---|---|
| worker emit (asr_paraformer_worker.py) | 16k wav | {text,start,end} | **biên VAD chunk** (coarse) | nguồn gốc |
| transcribe_paraformer (paraformer_transcriber.py:26) | JSON-lines | segments + duration=end-start | truyền qua | round |
| split_long_segments (transcriber.py:476) | segments | tách câu >10s | word boundary (Whisper) / char-proportional (Paraformer) | có (chỉ câu dài) |
| rescale_segments (retime.py:125) | scale | start/end/duration ×scale | — | **CÓ** (toàn bộ, khi VIDEO_SPEED<1) |
| apply_soft_timing (timing.py:132) | wavs đo được | start/end mới | wav header + plan_placements | **CÓ** (shift + atempo) |
| merge_segments (audio.py:485) | segs + wavs | mix wav | seg["start"] + wav header | không |
| postprocess/slow_segments (audio.py:240/181) | wavs | wavs hậu kỳ | — | đổi DURATION file (atempo), không đụng segments |
| build_timing_guide (timing.py:220) | segs + wavs | json | so duration nguồn vs TTS | không |

**TTS duration source:** `wav_duration_s` (audio.py:364 — đọc header, không load waveform) gọi ở: pipeline.py:1618 (cache), vieneu/capcut sau render, timing.py:151 (trước placement), audio.py:560 (lúc merge), pipeline.py:647 (giãn total_duration).

## 3. Phase 2 — Root cause (xác nhận bằng code, không suy đoán)

### A. Paraformer dùng VAD boundary làm segment boundary — XÁC NHẬN
- Timestamp = `seg.start/16000`, `start+len(samples)/16000` (worker). Silero threshold 0.35 → onset speech thật thường TRƯỚC biên VAD ~100-400ms (VAD cần vài window để vượt ngưỡng); min_silence 0.5s cắt đuôi sớm.
- Không tồn tại bước refine nào giữa VAD và final timeline. (TASK trước đã thêm decode-padding nhưng timestamp vẫn cố ý giữ biên VAD để timeline ổn định.)
- Hệ quả sync: dub_start lệch muộn so với môi miệng/speech thật ở đầu câu; slot tính từ biên rộng hơn speech → TTS target cũng lệch.

### B. Paraformer thiếu text — XÁC NHẬN (chi tiết ở `.artifacts/paraformer-ocr-root-cause.md`)
RC-1 ASR nghe bản trộn nhạc (vocals.wav có sẵn mà chưa dùng) · RC-2 không speech-pad (đã thêm ở TASK-1, decode-only) · RC-3 chunk rỗng bị nuốt (đã thêm signaling TASK-1) · RC-4 max_speech 20s chặt · RC-5 min_speech 0.1s. Post-process/merge KHÔNG làm mất text (đã loại).

### C. TTS không target duration — XÁC NHẬN
- `target_duration=None` cố ý (pipeline.py:1631-1637, comment "timing is handled globally by VIDEO_SPEED/VOICE_SPEED, never per clip").
- Engines render natural pace; interface đã trả `actual_duration` đo thật (Phase 10 của spec **đã thoả** từ trước — không cần sửa API).
- Hệ quả: VI dài hơn ZH ~15-25% → toàn bộ gánh sync dồn sang Step 6b (shift 1.5s trần + atempo 1.1 trần) và/hoặc VIDEO_SPEED.

### D. VIDEO_SPEED là cơ chế sync chính hiện nay — XÁC NHẬN
- Default đã là 1.0 (config.py:394), nhưng comment config.py:176-180 **khuyến nghị 0.82 cho zh→vi** + GUI slider 0.5-1.0 (settings_fields.py:116-121) → sync bằng làm chậm video là đường "chính" được hướng dẫn dùng.
- Khi bật: video setpts + segments ×scale + subs làm lại — mọi timeline đồng bộ với nhau (không mismatch nội bộ), NHƯNG nhịp môi bị chậm lại chính là triệu chứng "voice không khớp hình" theo hướng ngược.

### E. VOICE_SPEED toàn cục — XÁC NHẬN
- MỘT hệ số atempo cho MỌI clip: fuse trong postprocess (audio.py:281-287) hoặc slow_segments (audio.py:181-232). Không tồn tại per-segment speed ngoài atempo ép buộc hiếm hoi của soft timing (trần 1.1, chỉ khi câu sau sắp vượt drift).

### F. Drift: có tích luỹ hay không? — KHÔNG tích luỹ vô hạn, NHƯNG trần quá rộng
- `t = max(natural, prev_end+gap)`, chặn `natural + max_drift_s` — mỗi segment đối chiếu timeline nguồn (không cộng dồn shift) ✓ đúng nguyên tắc "tham chiếu source".
- NHƯNG `max_drift_s` mặc định **1.5s** (config.py:202) — xa vượt ngưỡng lip-sync cảm nhận (~0.12-0.2s). Dub có thể trễ đến 1.5s so với speech mà pipeline vẫn coi "đã xong".
- atempo ép buộc chỉ tính khi THREATEN câu sau (look-ahead 1 câu) — không đối chiếu `actual_duration` vs `source_duration` của chính câu.

### G. Placement merge — ĐÚNG, không phải root cause
- merge dùng `seg["start"]` (timeline sau retime + soft-timing) + wav đo thật. `seg["duration"]` KHÔNG bị dùng nhầm ở merge (spec mục 12 đã thoả).
- Semantic `duration`: = source speech duration (×scale một lần khi retime) — nhất quán ở mọi reader hiện có (timing_guide, annotate_slots, editor). Chỉ `rescale_segments` đổi nó, có chủ đích.

### Tổng hợp root cause "voice không khớp video" (thứ tự tác động)
1. **RC-S1**: dub_onset lệch do soft-timing shift trần 1.5s (quá rộng) — TTS tự nhiên dài hơn slot → dồn trễ thay vì fit từng câu.
2. **RC-S2**: không có per-segment fitting (C) + VOICE_SPEED toàn cục (E) — câu ngắn bị kéo theo tốc độ của cả video.
3. **RC-S3**: VAD boundary coarse (A) — sai số gốc vài trăm ms ở mọi câu.
4. **RC-S4**: VIDEO_SPEED được khuyến nghị làm cơ chế sync (D) — làm chậm hình thay vì fit voice.
5. RC-S5 (gián tiếp): transcript thiếu/sai câu (B) → dịch lệch → TTS sai chỗ.

## 4. Điểm cần lưu ý cho thiết kế

- `TTSResult.actual_duration` + `wav_duration_s` đã đo thật mọi nơi → nền tảng cho per-segment fitting có sẵn.
- `plan_placements` THUẦN TOÁN, tách render — nơi thay chiến lược fit mà không đụng audio/video.
- Soft-timing hiện tại chạy SAU VOICE_SPEED → tốc度 cuối cùng của một câu = VOICE_SPEED × atempoép — nhân chồng hệ số, phải thống nhất một chỗ.
- `rescale_segments` mutate `duration` (retime) trong khi `apply_soft_timing` giữ nguyên (nguồn) — semantic ổn nhưng thêm field mới (dub_start/dub_end/tts_actual_duration) phải không đụng 3 field cũ để giữ resume-cache + editor + SRT.
- numpy CÓ sẵn trong env chính (audio.py:397 dùng) → refine biên speech bằng energy/RMS không cần dependency mới.
- OCR cross-check (Phase 9 của spec): đang dở ở TASK-5→7 của feature asr-accuracy-boost (đã tạm dừng) — design voice-sync không phụ thuộc nó.

## 5. Files đã kiểm tra (trực tiếp hoặc qua agent có file:line)

transcriber.py · paraformer_transcriber.py · asr_paraformer_worker.py (toàn file) · pipeline.py (Step 2→7, _synthesize_segments, _apply_voice_speed, _resolve_background, _build_timing_guide) · media/audio.py (merge_segments, postprocess, slow_segments, apply_atempo, wav_duration_s) · media/timing.py (toàn file) · media/retime.py (apply/defer/rescale) · speech/tts/base.py · vieneu_vi.py / capcut_vi.py (synthesize + TTSResult) · config.py (VIDEO_SPEED/VOICE_SPEED/soft_timing) · translate_hint.py (annotate_slots/slot) · editor.py (re-synth path).

TRẠNG THÁI: HOÀN THÀNH (Phase 1 + Phase 2). Chưa sửa code.
