# Thiết kế — asr-accuracy-boost (Paraformer recall + Selective OCR Fusion)

## 1. Requirement đã duyệt

`.artifacts/requirements/asr-accuracy-boost.md` — người dùng đã phản hồi `DUYỆT PHÂN TÍCH` (2026-08-22). 5 nhóm FR (A: sửa nguồn mất text; B: suspect detection; C: selective OCR; D: fusion + scoring; E: report) + 12 AC.

## 2. Kiến trúc hiện tại liên quan

- ASR: `transcribe()` (`speech/transcriber.py:158`) → Paraformer worker trong `.venv-asr` qua JSON-lines stdout (`speech/asr_paraformer_worker.py`), fallback Whisper. Ngõ vào là audio gốc 16k mono (`pipeline.py:424`).
- Demucs chạy trước ASR (chờ future khi không overlap) và đã ghi `data/vocals.wav` (44.1k stereo khi HQ) — hiện bỏ phí.
- Transcript cache resume chỉ cần `start/end/text` (`pipeline.py:383-390`).
- Không có OCR; venv pattern chuẩn: `.venv-asr/.venv-whisper/.venv-vieneu` + `scripts/setup_*.py` + `Settings.*_venv_python` (config.py:126-147).
- SRT/TTS/timing đều tiêu thụ `segments` sau Step 3 — mọi cải tiến transcript chỉ cần chèn TRƯỚC `save_transcript` (pipeline.py:425).

## 3. Kiến trúc đề xuất

```
Step 2.5 (Demucs) ──vocals.wav──┐
                                 ▼
Step 3: transcribe(asr_source, meta)          [A] worker pad + empty-signal
          │ segments + empty_chunks
          ▼
   detect_suspect_segments()                  [B] autodub/text/fusion.py
          │ suspects (lý do cụ thể)
          ▼
   hardsub? (probe 5 frame) ──no──► save_transcript (như cũ)
          │ yes
          ▼
   selective OCR trên suspect windows         [C] autodub/media/ocr.py
          │ ocr_segments {text,start,end,conf}
          ▼
   fuse(segments, ocr, suspects)              [D] fusion.py: align + scoring
          │ fused segments + report
          ▼
   save_transcript + asr_fusion_report.json   [E]
```

Nguyên tắc: mọi thứ chèn giữa `transcribe()` và `save_transcript()`; khi OCR off (mặc định) luồng về y hệt hiện tại.

## 4. Component thay đổi

### C1 — ASR source (FR-A1) — `pipeline.py`
- Hàm mới `_asr_source(bg_future, bg_mode, audio_path, work_dir) -> str`: nếu `settings.asr_use_vocals and bg_mode=="demucs"`: `bg_future.result()` (nếu chưa xong) rồi tìm `data/vocals.wav`; nếu tồn tại → ffmpeg resample 16k mono ra `data/asr_vocals.wav` (cache theo mtime như audio.py:205 pattern) và trả path đó; mọi nhánh fail → trả `audio_path` gốc + log rõ nguồn đang dùng.
- Chờ future trong chế độ overlap GPU+CPU đánh mất lợi ích song song — chấp nhận vì recall đúng là mục tiêu của feature; tắt được bằng `ASR_USE_VOCALS=false`.

### C2 — Worker Paraformer (FR-A2/A3) — `asr_paraformer_worker.py`
- Thêm `--vad-pad <s>` (default 0.3). Tách pure-function `padded_range(seg_start, seg_end, prev_end, n_samples, pad_samples) -> (s, e)` — clamp `[0, n)`, `s >= prev_seg_end` (không chồng chunk kề). Decode `samples[s:e]`; **timestamp emit vẫn là biên VAD gốc** (seg.start, seg.start+len).
- Chunk decode rỗng → emit `{"empty": true, "start":…, "end":…}` (protocol mới dạng thêm-key, không đụng key cũ). Message `done` thêm `"num_empty": n`.
- `_read_wav`/model load không đổi.

### C3 — Parse protocol — `paraformer_transcriber.py` + `transcriber.py`
- `transcribe_paraformer(audio_path, settings, meta: dict | None = None)`: `meta["empty_chunks"] = [{"start","end"},…]`; signature cũ không đổi về mặt giá trị trả về.
- `transcribe(..., meta=None)` truyền xuyên; nhánh Whisper không ghi key (docstring ghi rõ).

### C4 — Fusion/suspect core (FR-B, D) — module mới `autodub/text/fusion.py`
Thuần stdlib (difflib cho similarity/prefix-suffix), không dependency mới. Public API:
- `detect_suspect_segments(segments, empty_chunks, ocr_segments=None, settings=None) -> SuspectResult{normal: list, suspect: list[Segment+reason], stats}`
  - `empty_speech_chunk`: khoảng empty chunk không được segment nào phủ.
  - `text_too_short_for_duration`: char-rate (CJK chars/s, bỏ punct) ngoài `[0.4×median, 3×median]` — median tính trên các segment dur ≥ 0.5s (adaptive, ≥5 câu mới bật heuristic).
  - `gap_anomaly`: khoảng lặng > `max(1.5s, 3×median_gap)` giữa hai câu kề.
  - `ocr_no_asr_match`: OCR text tồn tại trong window mà không có ASR text (chỉ khi có ocr_segments — lần 2 gọi sau OCR).
- `align_texts(asr_text, ocr_text) -> Alignment{similarity, merged, added_prefix, added_suffix}`: strip punct/full-width normalize → longest common prefix/suffix → merged candidate không duplicate ký tự chung.
- `fuse(segments, ocr_segments, suspects) -> (fused_segments, report)` — quyết định từng cặp (ASR segment ↔ các OCR segment giao thời gian ≥ 0.2s):
  - Scoring 0..1, FINAL = `0.30·ASR + 0.20·OCR + 0.20·ALIGN + 0.15·TEMPORAL + 0.15·COMPLETENESS`:
    - `ASR_SCORE`: 0.6 base khi có text; +0.2 nếu char-rate bình thường; +0.2 nếu segment không nằm trong suspect list.
    - `OCR_SCORE`: trung bình confidence OCR × hệ số ổn định (cùng text ≥80% frame trong window).
    - `ALIGNMENT_SCORE`: `Alignment.similarity`.
    - `TEMPORAL_SCORE`: IoU hai khoảng thời gian.
    - `COMPLETENESS_SCORE`: 1 nếu một bên chứa bên kia (prefix/suffix/substring), 0 nếu rời rạc,线性 theo phần giao.
  - Quy tắc quyết định (ưu tiên từ trên xuống — mọi hằng số là named constant ở đầu file):
    1. ASR text rỗng/mất + OCR có text ≥3 CJK chars và OCR_SCORE ≥ 0.6 → **dùng OCR text + timestamp OCR** (Case 4).
    2. ALIGN ≥ 0.8 và OCR thêm prefix/suffix ≥1 ký tự → **merge text, giữ timestamp ASR** (Case 2/3).
    3. ALIGN ≥ 0.85 (chỉ khác vài ký tự) → **giữ ASR** (Case 5 — OCR sai vài chữ).
    4. ALIGN < 0.6 (khác hoàn toàn) hoặc FINAL không vượt `FUSION_OVERRIDE_MIN=0.75` → **giữ ASR + flag `suspect` trong report** (Case 6).
  - Bất biến output: sort theo start, `0 < start < end`, duration ≥ 0.1s, không chồng câu kề (clip start lên `prev.end`), id gán lại tuần tự, số segment không bao giờ giảm so với input ASR (chỉ thêm từ OCR rời).
  - Passthrough: không có ocr_segments → trả (segments, report rỗng) không đụng gì (Case 1/AC-1).

### C5 — OCR engine (FR-C) — module mới `autodub/media/ocr.py` + worker `autodub/media/ocr_worker.py` + `scripts/setup_ocr.py`
- **Engine: RapidOCR** (`rapidocr_onnxruntime`) trong venv riêng `.venv-ocr` — đúng pattern venv hiện có; CPU onnxruntime, không kéo Paddle đầy đủ, hỗ trợ zh tốt.
- Worker standalone (không import autodub), giao thức JSON-lines y hệt ASR worker: đọc danh sách ảnh từ argv file-list, emit `{"frame": path, "lines": [{"text", "score", "box"}]}` rồi `done`.
- Main-app side (`ocr.py`):
  - `detect_hardsub(video_path, settings) -> bool`: ffmpeg trích 5 frame (mỗi 1/5 độ dài), crop region dưới (mặc định 18% chiều cao, `OCR_REGION_HEIGHT`), gửi worker; ≥3/5 frame có text CJK → hard-sub.
  - `run_selective_ocr(video_path, suspects, settings) -> list[OcrSegment]`: mỗi suspect window `[start-margin, end+margin]` (margin 1.0s, clamp biên video) → ffmpeg `-ss/-t -vf fps=OCR_FPS(default 3),crop=…` xuất JPEG vào `data/ocr_frames/<hash>/`; worker OCR; normalize (strip, full→half-width, chỉ giữ CJK + punct CJK cơ bản); merge frame liên tiếp trùng text (ngưỡng giống nhau 0.9) thành `OcrSegment{text, start_time, end_time, confidence}`.
  - Cache `data/ocr_result.json` keyed `(video mtime, region, fps, window list)` — chạy lại không OCR lại.
  - Frame tạm dọn sau khi merge (giữ cache JSON).

### C6 — Wiring (pipeline.py Step 3)
```python
segments = transcribe(audio_src, lang_code, settings, meta=meta)
if settings.ocr_enabled:
    if detect_hardsub(video_path, settings):
        suspects = detect_suspect_segments(segments, meta.get("empty_chunks"))
        ocr_segments = run_selective_ocr(video_path, suspects.suspect, settings)
        suspects2 = detect_suspect_segments(segments, meta.get("empty_chunks"), ocr_segments)
        segments, fusion_report = fuse(segments, ocr_segments, suspects2)
        save_json_atomic(data_path(work_dir,"asr_fusion_report.json"), fusion_report)
save_transcript(segments, transcript_orig_path)   # như cũ
```
- `empty_chunks` từ RC-3 signal; khi worker cũ chưa cập nhật (resume) → meta rỗng, heuristic khác vẫn chạy.

### C7 — Settings mới (`config.py`) + env
| Setting | Default | Env |
|---|---|---|
| `asr_use_vocals` | true | `ASR_USE_VOCALS` |
| `asr_vad_pad_s` | 0.3 | `ASR_VAD_PAD_S` |
| `ocr_enabled` | **false** | `OCR_ENABLED` |
| `ocr_fps` | 3 | `OCR_FPS` |
| `ocr_region_height` | 0.18 | `OCR_REGION_HEIGHT` |
| `ocr_venv_python` | `<app>/.venv-ocr/...` | `OCR_VENV_PYTHON` |

## 5. Data Flow

`vocals.wav →(resample)→ asr_vocals.wav → worker(VAD+pad) → segments + empty_chunks → suspect → frames →(worker .venv-ocr)→ ocr_segments → fusion → transcript_original.json + asr_fusion_report.json`. Không đổi data flow phía sau (SRT/dịch/TTS).

## 6. Control Flow

Xem C6. Retry/fallback: OCR worker chết → log warning, tiếp tục với ASR thuần (không fail pipeline); Paraformer lỗi → fallback Whisper như cũ; hardsub probe fail → coi như không có hard-sub.

## 7. Database

Không có DB.

## 8. API Contract (internal)

- Worker ASR protocol: **thêm key** (`empty`, `num_empty`) — tương thích ngược với parser cũ (bỏ qua key lạ, paraformer_transcriber.py:74-79 đã skip non-JSON).
- `transcribe()` thêm kwarg `meta` optional — caller cũ không đổi.
- `fusion.py`, `ocr.py` là module mới — không break gì.

## 9. UI Contract

Không UI mới. OCR off mặc định; power-user bật qua env/settings. (GUI wiring để phase sau nếu cần.)

## 10. Validation

- `padded_range`: bất biến `0 ≤ s < e ≤ n`, `s ≥ prev_end`, không vượt pad×2.
- `OcrSegment`: `0 ≤ start < end`, confidence ∈ [0,1], text non-empty sau normalize.
- Fusion output: bất biến section C4; `asr_fusion_report.json` schema có version.

## 11. Error Handling

- Worker OCR thiếu venv/model → `ocr_available()` check như `asr_ready()` (config.py:532 pattern); OCR skip + warning.
- ffmpeg frame extraction lỗi 1 window → bỏ window đó, không bỏ run.
- fusion exception → catch ở pipeline, log, dùng segments gốc (fail-safe về hành vi hiện tại).

## 12. Security

Không network mới; frame tạm trong work dir và được dọn; không exec input từ user (argv là path nội bộ).

## 13. Performance

- Không OCR: chi phí thêm ≈ 0 (heuristic in-memory O(n) + 1 lần resample ffmpeg cho vocals).
- OCR bật: chi phí = startup worker (~2s) + Σ(window×fps) frame OCR; hardsub probe = 5 frame. Ví dụ 10 suspect × 4s × 3fps = 120 frame — so với OCR toàn video 10 phút × 3fps = 1800 frame (15×).
- Vocals cho ASR còn tăng tốc VAD (ít false trigger) và tăng accuracy decode.

## 14. Testing

- `tests/test_asr_worker_pad.py`: `padded_range` mọi biên (đầu/cuối file, chunk kề, pad > chiều dài chunk).
- `tests/test_paraformer_protocol.py`: parse `empty`/`num_empty` qua JSON-lines giả.
- `tests/test_suspect_detection.py`: 4 heuristic + adaptive median + không đủ样本.
- `tests/test_fusion_alignment.py`: align prefix/suffix/substring, không duplicate (AC-2).
- `tests/test_fusion_scoring.py`: 8 case spec (Case 1-8) + named-constant thresholds.
- `tests/test_fusion_invariants.py`: property test bất biến timestamp (AC-10), passthrough (AC-1).
- `tests/test_ocr_normalize.py`: full-width, multi-line, merge frame trùng, confidence filter.
- `tests/test_pipeline_asr_source.py`: chọn nguồn vocals/fallback (mock ffmpeg/demucs).
- Regression: 630 test cũ phải PASS.

## 15. Migration/Rollback

- Rollback toàn bộ: `OCR_ENABLED=false` (mặc định) tắt C/D/E; `ASR_USE_VOCALS=false` + `ASR_VAD_PAD_S=0` trả worker về hành vi cũ. Không migration dữ liệu — transcript cache schema không đổi.

## 16. File dự kiến thay đổi

- MODIFY `autodub/pipeline.py` (Step 3 wiring + `_asr_source`)
- MODIFY `autodub/speech/asr_paraformer_worker.py`, `paraformer_transcriber.py`, `transcriber.py`
- MODIFY `autodub/config.py` (settings mới)
- NEW `autodub/text/fusion.py`, `autodub/media/ocr.py`, `autodub/media/ocr_worker.py`, `scripts/setup_ocr.py`
- NEW tests (mục 14), `requirements-doc` không cần

## 17. File không được tự ý thay đổi

`autodub/text/srt.py`, `autodub/text/subtitles.py`, `autodub/media/timing.py`, `autodub/text/translate_*.py`, `autodub/media/audio.py` (merge/postprocess), GUI, `asr_whisper_worker.py`, mọi `tests/` cũ (chỉ thêm).

## 18. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| Vocals Demucs méo tiếng làm ASR sai hơn ở một số video | Fallback settings + so sánh trong fusion report; thí nghiệm thực tế sau UNIT đầu |
| OCR region mặc định 18% sai vị trí với một số layout Douyin | Config `OCR_REGION_HEIGHT`; box filter theo tọa độ có thể mở rộng sau |
| Merge prefix/suffix tạo text kỳ dị khi align sai | Chỉ merge khi ALIGN ≥ 0.8; kết quả luôn ghi vào report để audit |
| Chờ Demucs làm chậm chế độ overlap GPU | Chỉ xảy ra khi bật vocals cho ASR; tắt được bằng 1 flag |
| RapidOCR chất lượng zh thấp hơn Paddle đầy đủ | Worker tách biệt — đổi engine chỉ sửa 1 file worker |

## 19. Phương án đã cân nhắc

1. **Tách vocals 16k riêng cho ASR bằng Demucs lần 2** — loại: Demucs đã chạy sẵn, tái dùng output.
2. **PaddleOCR đầy đủ** — loại: cài nặng (paddlepaddle + dll), venv phình to; RapidOCR same-model-weights qua onnxruntime.
3. **Fusion bằng LLM** — loại: thêm network + chi phí + không deterministic để test.
4. **Đưa OCR vào `.venv-asr` chung** — loại: phá ràng buộc "không đổi dependency venv ASR" (NFR-4) và tách lỗi engine.
5. **Chỉnh VAD threshold thay vì padding** — giữ nguyên 0.35, pad giải quyết triệu chứng mất đầu/cuối trực tiếp hơn và không tăng false-silence.

## 20. Quyết định thiết kế

1. Timestamp emit của worker **giữ biên VAD gốc** dù decode bản padded — timeline không trượt, invariant resume không đổi.
2. Trọng số scoring là named constants (`W_ASR=0.30`…), điều chỉnh được không cần sửa logic.
3. `ocr_enabled` mặc định **false** — feature opt-in, an toàn rollback; nhóm A bật mặc định vì thuần cải thiện recall.
4. Empty-chunk là tín hiệu quan trọng nhất của suspect detection → worker signaling (FR-A3) là prerequisite của B/C/D, implement ở UNIT đầu.

TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ
