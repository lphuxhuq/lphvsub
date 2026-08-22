# TIẾN ĐỘ

## voice-sync — HOÀN THÀNH TOÀN BỘ (2026-08-22) ✅

TASK-1→6 xong theo `.artifacts/tasks/voice-sync.md`. Final audit: **PASS** (`.artifacts/reviews/final-audit-voice-sync.md`, review chi tiết TASK-1→5 ở `voice-sync-TASK-1-5.md`).

**File production:**
- NEW `autodub/speech/boundaries.py` (refine biên VAD→speech bằng RMS), `autodub/media/voice_timing.py` (`fit_voice_to_slot`/`_decide_tempo`)
- MODIFY `autodub/media/timing.py` (`plan_voice_placements` thay `plan_placements`; apply gán dub_*/tempo_factor/timing_adjustment + log [VOICE-SYNC]), `autodub/pipeline.py` (refine sau ASR; tts_actual_duration; VOICE_SPEED legacy gate + guard `_apply_voice_speed`; warning VIDEO_SPEED), `autodub/config.py` (5 settings mới + comment)
- Docs: `docs/VOICE_SYNC_REVERSE_ENGINEERING.md`, `docs/VOICE_SYNC_DESIGN.md`, `docs/VOICE_SYNC_BENCHMARK.md` (sinh từ test)

**Test:** full suite **728 passed** (690 cũ + 38 mới; 690 cũ gồm 630 gốc + 60 của asr-accuracy TASK-1..4). Bug HIGH duy nhất (gate legacy bỏ sót `_apply_voice_speed`) bắt trong review TASK-4 và sửa ngay.

**Còn lại (ngoài scope):** đo trên video thật (CHƯA XÁC ĐỊNH); compaction bản dịch tự động cho câu VI >1.15× (chỉ flag); asr-accuracy-boost TASK-5→7 vẫn TẠM DỪNG.

---

## asr-accuracy-boost — TẠM DỪNG sau TASK-4

> ⏸️ (2026-08-22) user đổi ưu tiên sang voice-sync. TASK-5 (fuse), TASK-6 (wiring), TASK-7 (audit) CHƯA làm; `fusion.py` hiện có detection + align_texts nhưng CHƯA được pipeline gọi — không ảnh hưởng luồng chạy.

## TASK-4 — Text alignment ASR↔OCR ✅

**File:** `autodub/text/fusion.py` (thêm `Alignment`, `_normalize_for_align`, `align_texts`), `tests/test_fusion_alignment.py` (NEW, 10 test).
**Kết quả:** 10/10 pass; full suite **690 passed** (630 cũ + 60 mới của TASK-1..4). Review ngắn: merge chỉ khi chuỗi ASR normalize LÀ substring của OCR (tách prefix/suffix chính xác, không duplicate); các TH khác giữ ASR + similarity chặn ở rule fusion (TASK-5). Test bao đủ 4 TH spec + empty + punct + full-width + ASR dài hơn OCR. PASS.

## TASK-1 — Worker Paraformer: speech padding + empty-chunk signaling ✅

**Ngày:** 2026-08-22

**File thay đổi:**
- `autodub/speech/asr_paraformer_worker.py` — thêm pure function `padded_range()`; `--vad-pad` (default 0.3s); decode bản padded nhưng timestamp emit giữ biên VAD gốc; chunk decode rỗng emit `{"empty": true, start, end}`; `done` thêm `num_empty`.
- `autodub/speech/paraformer_transcriber.py` — kwarg `meta`; parse message `empty` vào `meta["empty_chunks"]` + warning từng đoạn + warning tổng; cmd truyền `--vad-pad` từ settings.
- `autodub/speech/transcriber.py` — `transcribe()` nhận `meta` truyền xuyên cho nhánh Paraformer (nhánh Whisper không ghi key), docstring ghi rõ.
- `autodub/config.py` — **DEVIATION**: thêm `asr_vad_pad_s: float = 0.3` + env `ASR_VAD_PAD_S` (clamp 0-1). Task breakdown ghi setting này thuộc TASK-6 nhưng TASK-1 bắt buộc đọc nó để truyền `--vad-pad` — thêm 4 dòng đúng bảng settings C7 của design đã duyệt, TASK-6 sẽ không phải thêm lại.
- `tests/test_asr_worker_pad.py` (NEW, 9 test) — bất biến padded_range: clamp 2 biên, chặn chunk kề, pad 0, chunk 1-sample.
- `tests/test_paraformer_protocol.py` (NEW, 7 test) — protocol mới (empty/num_empty), protocol cũ tương thích, meta=None, cmd có --vad-pad, error/no-done/no-segments raise RuntimeError.

**Test đã chạy:**
- `pytest tests/test_asr_worker_pad.py tests/test_paraformer_protocol.py` → 16 passed.
- `pytest tests/` full suite → **646 passed** (630 cũ + 16 mới), 1 warning audioop có sẵn. Không regression.

**Code review (`.artifacts/reviews/TASK-1.md`) — kết quả PASS sau 1 vòng sửa:**
- Finding HIGH đã bắt trong review: bản đầu chỉ clamp trái → decode của chunk trước tràn `+pad` vào speech chunk sau tại force-split 20s (gap=0) → chữ đầu câu lặp. Đã sửa: `padded_range` nhận thêm `next_start` (clamp phải), worker tách 2-pass (thu thập VAD xong rồi decode với biên 2 chunk kề). Thêm test bất biến `test_no_chunk_speech_decoded_twice`.
- Sau sửa: 19 test unit mới pass, full suite **649 passed** (630 cũ + 19 mới), `py_compile` 4 file production OK.

**Acceptance Criteria đối chiếu:**
- [x] `padded_range` bất biến `0 ≤ s < e ≤ n`, `s ≥ prev_end`, mở rộng ≤ pad mỗi bên.
- [x] Timestamp `seg` không đổi khi có/không padding (emit biên VAD gốc — bằng thiết kế code).
- [x] Empty chunk vào `meta["empty_chunks"]`; worker cũ (không key mới) → `empty_chunks == []`, không crash.
- [x] 630 test cũ PASS (646 tổng).

**Warning:** không.

**Phần còn lại:** TASK-2 (suspect detection) → TASK-3/4 (song song) → TASK-5 → TASK-6 → TASK-7.
