# Task Breakdown — asr-accuracy-boost

> Nguồn: design đã duyệt `.artifacts/designs/asr-accuracy-boost.md` (2026-08-22). Mỗi unit = hiểu → code → test → review độc lập; unit sau chỉ chạy khi unit trước PASS.

## 1. Dependency Graph

```
TASK-1 (worker: padding + empty-signal)          TASK-3 (OCR worker + extraction)
   │                                                  │
TASK-2 (suspect detection, cần empty_chunks)          │
   │                                                  │
   └──────────────► TASK-5 (fusion engine) ◄──────────┘
                        │  cần cả TASK-4 (alignment)
TASK-4 (text alignment, độc lập) ──► TASK-5
                        │
TASK-6 (pipeline wiring + settings + report)
                        │
TASK-7 (integration test + final audit)
```

TASK-1, TASK-3, TASK-4 không phụ thuộc nhau — làm song song được.

## 2. Danh sách Unit

### TASK-1 — Worker Paraformer: speech padding + empty-chunk signaling

**Mục tiêu:** Sửa RC-2/RC-3 trong `asr_paraformer_worker.py` + parse protocol ở driver.

**Dependency:** Không có.

**File được phép sửa:**
- `autodub/speech/asr_paraformer_worker.py`
- `autodub/speech/paraformer_transcriber.py`
- `autodub/speech/transcriber.py` (chỉ kwarg `meta`)
- `tests/test_asr_worker_pad.py` (NEW)
- `tests/test_paraformer_protocol.py` (NEW)

**File không được sửa:** `asr_whisper_worker.py`, `pipeline.py`, mọi file khác.

**Thay đổi dự kiến:**
- Pure function `padded_range(seg_start, seg_end, prev_end, n_samples, pad_samples) -> (s, e)` — clamp `[0, n)`, `s ≥ prev_end`.
- `--vad-pad` arg (default đọc từ env `ASR_VAD_PAD_S` do worker standalone không nhận Settings).
- Decode `samples[s:e]`; timestamp emit giữ biên VAD gốc.
- Chunk rỗng → `{"empty": true, start, end}`; `done` thêm `num_empty`.
- Driver: `transcribe_paraformer(..., meta: dict | None)` ghi `meta["empty_chunks"]`; `transcribe(..., meta=None)` truyền xuyên (nhánh Whisper không ghi key).
- Gọi worker truyền thêm `--vad-pad` từ `settings.asr_vad_pad_s`.

**Acceptance Criteria:**
- `padded_range` bất biến: `0 ≤ s < e ≤ n`, `s ≥ prev_end`, mở rộng ≤ pad mỗi bên.
- Timestamp trong message `seg` KHÔNG đổi khi có/không padding (cùng VAD).
- Empty chunk xuất hiện trong `meta["empty_chunks"]`; worker cũ (không emit) → meta không có key, không crash.
- 630 test cũ PASS.

**Test:** unit `padded_range` (biên đầu/cuối file, chunk kề, pad > chunk), protocol parse JSON-lines giả (có/không có key mới).

**Rủi ro:** padding làm decode trùng chữ giữa 2 chunk kề → clamp `s ≥ prev_end` xử lý; theo dõi qua test.

**Rollback:** `ASR_VAD_PAD_S=0` (không pad); key mới bị parser cũ bỏ qua.

---

### TASK-2 — Suspect segment detection

**Mục tiêu:** FR-B1/B2 — heuristic phát hiện câu nghi ngờ.

**Dependency:** TASK-1 (cần shape `empty_chunks`; vẫn code được với list rỗng).

**File được phép sửa:**
- `autodub/text/fusion.py` (NEW — chỉ phần detection)
- `tests/test_suspect_detection.py` (NEW)

**File không được sửa:** mọi file hiện có.

**Thay đổi dự kiến:**
- `SuspectResult` dataclass + `detect_suspect_segments(segments, empty_chunks=None, ocr_segments=None)`.
- 4 heuristic: `empty_speech_chunk`, `text_too_short_for_duration` (char-rate ngoài `[0.4×median, 3×median]`, cần ≥5 câu dur≥0.5s), `gap_anomaly` (> `max(1.5s, 3×median_gap)`), `ocr_no_asr_match`.
- Thuần stdlib, không mutate input.

**Acceptance Criteria:**
- Mỗi heuristic bắt đúng case mẫu; median chưa đủ mẫu → heuristic tắt (không false positive).
- Segment suspect mang `reason`; `normal` + `suspect` partition đúng input.

**Test:** 4 heuristic riêng + adaptive + chưa đủ样本 + empty input.

**Rủi ro:** false positive kéo OCR tốn thời gian → mặc định ngưỡng nới (0.4×/3×), chỉnh được sau bằng data thật.

**Rollback:** module mới, chưa ai dùng — xoá file.

---

### TASK-3 — OCR engine: worker + selective extraction

**Mục tiêu:** FR-C1→C4 — RapidOCR trong `.venv-ocr`, frame extraction selective, normalize/merge, cache.

**Dependency:** Không có (song song TASK-1/2).

**File được phép sửa:**
- `autodub/media/ocr.py` (NEW)
- `autodub/media/ocr_worker.py` (NEW, chạy trong `.venv-ocr`)
- `scripts/setup_ocr.py` (NEW)
- `autodub/config.py` (chỉ thêm settings OCR: `ocr_enabled/ocr_fps/ocr_region_height/ocr_venv_python` + env)
- `tests/test_ocr_normalize.py` (NEW)
- `tests/test_ocr_cache.py` (NEW)

**File không được sửa:** `pipeline.py`, `speech/`, `text/`.

**Thay đổi dự kiến:**
- Worker standalone JSON-lines: nhận file-list ảnh → emit `{frame, lines:[{text,score,box}]}` → `done`; chạy bằng `settings.ocr_venv_python_path()`.
- `ocr_available()` check venv (pattern `asr_ready()` config.py:532).
- `detect_hardsub(video_path, settings)`: 5 frame probe (mỗi 1/5 độ dài) + crop region dưới → ≥3/5 có CJK → True.
- `run_selective_ocr(video_path, suspects, settings)`: window `[start-1, end+1]` clamp; ffmpeg `-ss/-t -vf fps=OCR_FPS,crop` → JPEG `data/ocr_frames/<hash>/`; worker OCR; normalize (full→half-width, chỉ CJK + CJK punct, strip); merge frame liên tiếp giống nhau ≥0.9 → `OcrSegment{text, start_time, end_time, confidence}`; multi-line ghép theo box y.
- Cache `data/ocr_result.json` keyed `(mtime video, region, fps, windows)`; dọn frame sau merge.

**Acceptance Criteria:**
- Không suspect → 0 frame extract, 0 lời gọi worker (test với mock counter — AC-6).
- Window sát cuối video không vượt biên.
- Normalize: bỏ ký tự rác, full-width chuyển đúng; merge không đếm trùng.
- Cache hit không chạy lại ffmpeg/worker.
- Worker chết/venv thiếu → exception rõ ràng cho caller bắt (TASK-6 sẽ catch).

**Test:** normalize/merge unit (mock OCR output), cache unit, hardsub probe (mock ffmpeg + worker), window clamp.

**Rủi ro:** RapidOCR quality zh — worker tách riêng để đổi engine sau; box tọa độ multi-line lệch → filter theo trong-region.

**Rollback:** `OCR_ENABLED=false` mặc định; module mới không ai gọi đến TASK-6.

---

### TASK-4 — Text alignment ASR↔OCR

**Mục tiêu:** FR-D2 — align mức ký tự, phát hiện bổ sung prefix/suffix, merge không duplicate.

**Dependency:** Không có (song song).

**File được phép sửa:**
- `autodub/text/fusion.py` (NEW — chỉ phần `align_texts`; ghép cùng file TASK-2)
- `tests/test_fusion_alignment.py` (NEW)

**File không được sửa:** file hiện có.

**Thay đổi dự kiến:**
- `Alignment` dataclass `{similarity, merged, added_prefix, added_suffix}`.
- `align_texts(asr_text, ocr_text)`: normalize (bỏ punct, full→half) → longest common prefix/suffix → merged; similarity = `difflib.SequenceMatcher.ratio()` trên chuỗi normalized.

**Acceptance Criteria:**
- Ví dụ spec: `你为什么不告诉` + `你为什么不告诉我` → merged `你为什么不告诉我`, `added_suffix="我"`, similarity ≥ 0.8.
- Hai chuẩn giống nhau → similarity 1.0, merged == asr.
- Chuỗi rời rạc hoàn toàn → similarity thấp, merged ưu tiên asr.
- Merged không bao giờ chứa substring chung hai lần (no duplicate).

**Test:** các cặp trong spec (Case 2/3/5/6) + chuỗi rỗng + toàn punct.

**Rủi ro:** merge hai chuỗi gần giống giữa chừng tạo chuỗi kỳ dị → chỉ được dùng khi quyết định fusion rule 2 (ALIGN ≥ 0.8) — ghi nhận ở TASK-5.

**Rollback:** function mới chưa ai gọi.

---

### TASK-5 — Fusion engine + scoring

**Mục tiêu:** FR-D1→D5 + E — quyết định từng segment, bất biến timestamp, report.

**Dependency:** TASK-2, TASK-3, TASK-4.

**File được phép sửa:**
- `autodub/text/fusion.py` (phần `fuse` + constants)
- `tests/test_fusion_scoring.py` (NEW)
- `tests/test_fusion_invariants.py` (NEW)

**File không được sửa:** file hiện có.

**Thay đổi dự kiến:**
- Named constants: `W_ASR=0.30, W_OCR=0.20, W_ALIGN=0.20, W_TEMPORAL=0.15, W_COMPLETENESS=0.15`, `FUSION_OVERRIDE_MIN=0.75`, ngưỡng rule (0.8/0.85/0.6).
- 5 score component như design C4 + FINAL weighted.
- `fuse(segments, ocr_segments, suspects) -> (fused, report)`: ghép cặp theo giao thời gian ≥0.2s; 4 quy tắc quyết định ưu tiên từ trên xuống; OCR rời (không ghép) thành segment mới chỉ khi rule 1.
- Bất biến: sort, `0<start<end`, dur≥0.1s, không chồng kề (clip start), id lại tuần tự, **len(fused) ≥ len(asr_segments)**; passthrough khi `ocr_segments` rỗng.
- Report: mỗi câu — decision, rule ăn theo, 5 score, FINAL, reason suspect, ocr/asr text đối chiếu; schema `{"version": 1, …}`.

**Acceptance Criteria:**
- Case 1–8 spec tương ứng AC-1→AC-7 pass unit test.
- AC-10: property test (random segments + OCR) thỏa mọi bất biến.
- Passthrough trả về object input y hệt (AC-1).

**Test:** 8 case + property test (hypothesis-style bằng random seed cố định, không thêm dependency — dùng `random` stdlib).

**Rủi ro:** rule 1 (ASR rỗng dùng OCR) tạo false segment từ OCR nhiễu → điều kiện ≥3 CJK chars + OCR_SCORE ≥0.6 đã có; theo dõi report trên data thật.

**Rollback:** module chưa wire vào pipeline.

---

### TASK-6 — Pipeline wiring + settings + ASR source

**Mục tiêu:** FR-A1 + C6 — nối tất cả vào Step 3, chọn nguồn vocals, ghi report.

**Dependency:** TASK-1 → TASK-5 tất cả.

**File được phép sửa:**
- `autodub/pipeline.py` (chỉ vùng Step 3 + hàm mới `_asr_source`)
- `autodub/config.py` (settings `asr_use_vocals`, `asr_vad_pad_s` + env — phần TASK-3 đã lo OCR settings)
- `tests/test_pipeline_asr_source.py` (NEW)
- `tests/test_pipeline_wiring.py` (NEW)

**File không được sửa:** `speech/`, `text/fusion.py`, `media/ocr.py` nội dung; mọi file ở "File không được tự ý thay đổi" của design.

**Thay đổi dự kiến:**
- `_asr_source(...)`: demucs mode → chờ future, lấy `data/vocals.wav`, ffmpeg resample 16k mono → `data/asr_vocals.wav` (cache mtime); fail → audio gốc + log.
- Step 3: `transcribe(..., meta=meta)`; khối `if settings.ocr_enabled:` gọi detect_hardsub → suspects → selective OCR → re-detect → fuse → `save_json_atomic(asr_fusion_report.json)`; mọi exception OCR/fusion catch + warning + dùng segments gốc.
- `save_transcript` + SRT như cũ (fusion xảy ra TRƯỚC save).

**Acceptance Criteria:**
- AC-9: chọn nguồn đúng + fallback (mock).
- AC-11: resume với transcript cũ vẫn skip ASR (không cần meta).
- OCR fail mọi mức → pipeline vẫn hoàn thành bằng ASR (test inject lỗi).
- 630 test cũ PASS.

**Test:** `_asr_source` unit (mock ffmpeg/demucs/future), wiring end-to-end với fusion module giả (stub trả kết quả cố định), regression.

**Rủi ro:** chờ Demucs làm mất song song GPU — chỉ khi `asr_use_vocals` bật + demucs mode; ghi log thời gian chờ.

**Rollback:** `ASR_USE_VOCALS=false, OCR_ENABLED=false` → luồng cũ nguyên vẹn.

---

### TASK-7 — Integration test + final audit

**Mục tiêu:** Chạy tổng, đối chiếu 12 AC của requirement, final-audit skill.

**Dependency:** TASK-6.

**File được phép sửa:**
- `tests/test_asr_accuracy_integration.py` (NEW)
- `.artifacts/reviews/final-audit-asr-accuracy-boost.md` (NEW)

**File không được sửa:** production code (nếu audit phát hiện lỗi → unit riêng theo skill fix-bug).

**Acceptance Criteria:**
- Full suite PASS (630 cũ + mới).
- Ma trận 12 AC mapping code+test+ kết quả trong final audit.
- Kết luận PASS/FAIL rõ ràng.

**Test:** kịch bản end-to-end với mock ASR worker + OCR worker + video fixture nhỏ (nếu không có video thật:合成 wav + frame PNG fixture).

**Rủi ro:** thiếu video Douyin mẫu thật → đánh dấu CHƯA XÁC ĐỊNH phần hiệu quả thực tế, đề xuất thí nghiệm sau release opt-in.

**Rollback:** N/A (chỉ test + doc).

---

## 3. Thứ tự thực hiện

1. **TASK-1** và **TASK-3** và **TASK-4** (song song được, nhưng tuần tự cũng OK: 1 → 3 → 4).
2. **TASK-2** (sau TASK-1).
3. **TASK-5** (sau 2+3+4).
4. **TASK-6** (sau tất cả).
5. **TASK-7** cuối.

Sau mỗi unit: code-review skill + regression full suite trước khi sang unit kế.

## 4. Change Budget

- Production: ~6 file MODIFY (`asr_paraformer_worker.py`, `paraformer_transcriber.py`, `transcriber.py` nhỏ, `pipeline.py` vùng Step 3, `config.py` thêm settings, ) + 3 file NEW (`fusion.py`, `ocr.py`, `ocr_worker.py`) + `scripts/setup_ocr.py`.
- Tổng diff production dự kiến ≤ ~900 dòng (worker OCR ~150, fusion ~350, ocr.py ~250, wiring ~80, worker patch ~40, config ~30).
- Tests: 9 file test mới, không sửa test cũ.
- Không refactor ngoài phạm vi; không đụng 17 file trong "File không được tự ý thay đổi" của design.

TRẠNG THÁI: CHỜ DUYỆT TASK
