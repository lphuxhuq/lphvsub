# REVERSE_ENGINEERING_REPORT — Paraformer + OCR Accuracy Task (Phase 1)

> Triển khai theo task spec. Nền tảng chung: `.artifacts/project-map.md` (bản 2026-08-21, HOÀN THÀNH). Báo cáo này tập riêng vào pipeline ASR/timestamp/SRT/OCR.

## 1. Sơ đồ luồng thực tế (ĐÃ XÁC MINH từ code)

```
Video (Douyin)
 ↓ Step 2: extract_audio_dual — autodub/media/audio.py:147 (ffmpeg -ar 16000 -ac 1)
 ↓ 16kHz mono wav (ASR) + 44.1kHz stereo (HQ)
 ↓ Step 3: transcribe — autodub/speech/transcriber.py:158 (pipeline.py:376-442)
 ↓   ├─ Paraformer: paraformer_transcriber.py:26 → subprocess .venv-asr
 ↓   │    └─ asr_paraformer_worker.py:main
 ↓   │         silero VAD (thr .35 / min_sil .5s / min_speech .1s / max_speech 20s)
 ↓   │         mỗi VAD chunk → Paraformer greedy decode → CT-Transformer punct
 ↓   │         → JSON line {"text","start","end"} stdout
 ↓   └─ fallback: Whisper (vad_filter cùng tham số + speech_pad 500ms)
 ↓ transcribe() post: split_long_segments(>10s, transcriber.py:476/204)
 ↓ save_transcript → transcript_original.json (atomic) + .srt (pipeline.py:426)
 ↓ Step 4: _auto_translate (pipeline.py:1150) → text_vi → refresh_subtitles
 ↓ Step 5-6: TTS → soft timing → merge
```

OCR: **KHÔNG TỒN TẠI** (ĐÃ XÁC MINH — grep toàn repo + requirements). `blur_regions` là thủ công (GUI kéo rectangle trên 1 frame, `autodub_gui/style_dialog.py:165-198`). Trích frame duy nhất: preview 1 frame (`style_dialog.py:57-74`). Không có fps sampling, không có hard-sub detection.

## 2. Chi tiết từng module

### 2.1 Paraformer worker — `autodub/speech/asr_paraformer_worker.py`
- Chạy trong `.venv-asr` riêng, standalone, giao tiếp JSON-lines stdout (không import autodub).
- Model: `OfflineRecognizer.from_paraformer` int8 ONNX, 16kHz, fbank 80, greedy search (line 79-86).
- VAD config (line 115-121): threshold 0.35, min_silence 0.5s, min_speech 0.1s, max_speech 20s, feed window 512 samples.
- Timestamp = biên VAD chunk (line 141-142). **Không có word-level timestamp, không có speech padding.**

### 2.2 Dispatch + post-process — `autodub/speech/transcriber.py`
- `transcribe()` :158; Paraformer lỗi → tự fallback Whisper :183-184.
- `split_long_segments()` :476: tách segment >10s tại dấu câu; nếu không tìm thấy boundary thì giữ nguyên (không mất text).
- Output chuẩn: `{"id","text","start","end","duration"}`; strip field `words` :209-210.

### 2.3 SRT — `autodub/text/srt.py:142` `generate_srt`
- Cue = `start/end` của segment; segment dài tách bởi `split_for_display` (:64) chia thời lượng theo ký tự (min cue 0.8s). `refresh_subtitles` (subtitles.py:28) là entry regen duy nhất.

### 2.4 Translation — `autodub/pipeline.py:1150` `_auto_translate`
- Ưu tiên: AI Studio browser → Direct API → SaaS. Ghi `text_vi` (TargetLang.text_field). `_load_translation` :1298 ép khớp số segment.

### 2.5 Cache / resume
- `transcript_original.json` valid (có start/end/text) → skip ASR (pipeline.py:380-395). Atomic write. Mọi cải tiến ASR/OCR phải giữ 3 field này để không gãy resume.

## 3. Root-cause candidates — Paraformer thiếu text (đối chiếu 13 giả thuyết của spec)

| Giả thuyết spec | Tồn tại? | Bằng chứng |
|---|---|---|
| VAD cắt đầu/cuối câu | **CÓ — CAO** | Paraformer VAD không speech_pad (Whisper có 500ms, transcriber.py:414). Worker cũng chặt biên qua threshold 0.35 |
| Chunk quá ngắn / boundary mất từ | CÓ — TRUNG BÌNH | min_speech 0.1s bỏ utterance ngắn; max_speech 20s chặt câu dài không merge lại (worker:120) |
| Speech overlap giữa chunk | KHÔNG (VAD tuần tự, không overlap) | worker:148-160 |
| Background music/noise, volume thấp | **CÓ — CAO** | ASR chạy trên audio GỐC (Demucs chỉ dùng cho nhạc nền, chạy async song song Step 2.5, không feeding ASR); threshold 0.35 dễ bỏ sót speech trộn nhạc |
| Nhiều speaker / nói nhanh | SUY LUẬN — ảnh hưởng model, không phải code | greedy search, không LM |
| Sampling rate sai | KHÔNG | worker ép 16kHz, check :109-110 |
| Post-process cắt text | KHÔNG (chỉ tách, không xoá) | transcriber.py:476 |
| Timestamp merge mất segment | KHÔNG | không có bước merge |
| SRT formatter mất nội dung | KHÔNG | srt.py giữ nguyên text |
| **Decode ra text rỗng bị drop im lặng** | **CÓ — CAO** | worker:133-134 `if not text: return` — đúng triệu chứng "có tiếng nhưng không có text", không log |
| Model decoding/config | CÓ thể chỉnh | greedy, int8, num_threads |

## 4. Ràng buộc bắt buộc khi thiết kế (Phase 3+)

1. Timeline `start/end` là single source of truth cho SRT + TTS + timing + timing_report — fusion OCR không được phá.
2. Worker ASR tách venv — dependency OCR mới phải cài đúng env.
3. Format transcript cache phải backward-compatible (`start/end/text`).
4. Không rewrite pipeline — chỉ chèn module selective OCR + fusion ở Step 3.

## 5. Gaps cần làm rõ ở các phase sau

- CHƯA XÁC ĐỊNH: hiệu quả thực tế của từng root cause trên video Douyin mẫu (Phase 2 cần thí nghiệm).
- CHƯA XÁC ĐỊNH: chọn engine OCR (PaddleOCR/RapidOCR — CPU-friendly cho venv).
- SUY LUẬN: cho ASR ăn vocals đã tách Demucs có thể tăng recall không cần OCR — ứng viên thiết kế.

TRẠNG THÁI: HOÀN THÀNH (Phase 1). Chưa sửa bất kỳ dòng code production nào.
