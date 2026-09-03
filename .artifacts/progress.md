# TIẾN ĐỘ

## AI Multi-Speaker Smart Voice Director (Đạo diễn Lồng Tiếng Đa Nhân Vật Tự Động) — HOÀN THÀNH TOÀN BỘ ✅ (2026-09-02)

Đã triển khai hoàn chỉnh toàn bộ 7 Task theo kế hoạch (`.artifacts/tasks/ai-multi-speaker-voice-director.md`):

**File production & GUI:**
- NEW `autodub/speech/voice_models.py`: Định nghĩa dataclass bất biến (`PitchStats`, `SpeakerProfile`, `VoiceProfile`, `VoiceAssignment`, `CastingResult`).
- NEW `autodub/speech/speaker_profiler.py`: Trích xuất $F_0$ Autocorrelation FFT decimation trên CPU, tính toán thống kê, phân loại giới tính xác suất và phát hiện vai trò Dẫn chuyện (`narrator`).
- NEW `autodub/speech/voice_catalog.py`: Unified Voice Catalog & Providers trừu tượng hóa cho cả **VieNeu (Offline)** và **CapCut (Online API)**.
- NEW `autodub/speech/voice_director.py`: Động cơ chấm điểm phân vai (Compatibility Scoring), phạt trùng lặp (**Uniqueness Penalty**), tôn trọng **Manual Overrides** và Toggle On/Off.
- MODIFY `autodub/config.py`: Bổ sung cấu hình `auto_voice_director_enabled: bool = True`.
- MODIFY `autodub/pipeline.py`: Tích hợp Step 3.7 Auto Voice Casting và Step 5 Multi-Voice Synthesis.
- MODIFY `autodub_gui/pages/editor_panels.py` & `autodub_gui/pages/editor_page.py`: Giao diện quản lý danh sách Nhân vật (Speaker Cards), Voice Picker per-speaker và toggle Bật/Tắt Auto Director.

**Kiểm thử & Benchmark:**
- NEW `tests/test_voice_models.py` (4 tests)
- NEW `tests/test_speaker_profiler.py` (6 tests)
- NEW `tests/benchmark_speaker_profiler.py` (Benchmark CPU: **Median = 327.1ms**, **P95 = 329.3ms** cho audio 5 phút, GPU = 0%)
- NEW `tests/test_voice_catalog.py` (2 tests)
- NEW `tests/test_voice_director.py` (3 tests)
- NEW `tests/test_pipeline_multi_voice.py` (1 test)
- NEW `tests/test_editor_voice_panel.py` (1 test)
- NEW `tests/test_voice_director_integration.py` (1 test)
- **Full Regression Test Suite: 1045 / 1045 passed (100%)** trong 87.15s.
- **Final Audit: PASS** (`.artifacts/reviews/final-audit-ai-voice-director.md`).

---

## Fix: Bổ sung bộ cài Model & Scaling linh hoạt cho Phương thức 2 AI Inpaint — HOÀN THÀNH ✅ (2026-09-02)
- Đã tải và tích hợp mô hình chuẩn **LaMa ONNX** (`models/inpaint/lama.onnx` ~198.4 MB).
- Bổ sung script cài đặt tự động `scripts/setup_inpaint.py` và file batch `cai_them_inpaint.bat`.
- Cập nhật `LaMaOnnxEngine` trong `autodub/media/inpaint/lama_onnx.py` hỗ trợ tự động co giãn tensor (fixed-shape 512x512 / dynamic-shape) và phục hồi đúng kích thước patch gốc.
- Smoke test và toàn bộ test suite **1015 / 1015 passed (100%)**.

---

## AI Subtitle Remover Integration (Phương thức che/xóa phụ đề thứ 2) — HOÀN THÀNH TOÀN BỘ ✅ (2026-09-01)

Đã triển khai hoàn chỉnh toàn bộ 6 Task theo kế hoạch đã duyệt (`.artifacts/tasks/ai-subtitle-remover-integration.md`):

**File thêm mới & cập nhật:**
- NEW `autodub/media/inpaint/__init__.py`: Cung cấp `inpaint_video_with_cache` và `get_inpaint_engine`.
- NEW `autodub/media/inpaint/base.py`: Lớp cơ sở `BaseInpaintEngine`, tiện ích chuyển đổi `regions` thành mask và tính bounding box ROI.
- NEW `autodub/media/inpaint/cache.py`: Quản lý bộ nhớ đệm SHA256 cache cho video sạch (`clean_video.mp4`).
- NEW `autodub/media/inpaint/lama_onnx.py`: Engine LaMa ONNX nhúng trực tiếp, tối ưu hóa ROI patch crop và streaming FFmpeg pipes.
- NEW `autodub/media/inpaint/vsr_bridge.py`: Adapter kết nối VSR CLI (`video-subtitle-remover`).
- MODIFY `autodub/config.py`: Bổ sung cấu hình `mask_method`, `inpaint_engine`, `inpaint_device`, `inpaint_model_path`, `vsr_dir`.
- MODIFY `autodub/editor.py`: Cập nhật `_render_options` đồng bộ lưu/đọc `render_opts.json`.
- MODIFY `autodub/preflight.py`: Bổ sung hàm kiểm tra `_check_inpaint` cho model ONNX/VSR.
- MODIFY `autodub/media/video.py`: Tích hợp quy trình 2-Stage trong `merge_video` (inpaint sạch ➔ final compose không còn boxblur).
- MODIFY `autodub/pipeline.py`: Chuyển tiếp các tùy chọn inpaint vào pipeline.
- MODIFY `.env.example`: Cập nhật tài liệu cấu hình chi tiết cho các biến inpaint.

**Kiểm thử & Đánh giá:**
- NEW `tests/test_inpaint_cache.py` (6 tests)
- NEW `tests/test_inpaint_engine.py` (3 tests)
- NEW `tests/test_video_render_inpaint.py` (3 tests)
- Cập nhật `tests/test_config.py` (+2 tests), `tests/test_preflight.py` (+3 tests)
- **Full Inpaint Test Suite: 49 / 49 passed (100%)** trong 1.15s.
- **Final Audit: PASS** (`.artifacts/reviews/final-audit-ai-subtitle-remover.md`).

---


## AI Viral Shorts & Reels Clipper (9:16) — HOÀN THÀNH TOÀN BỘ (2026-08-31) ✅

Đã triển khai hoàn chỉnh toàn bộ 5 Task theo kế hoạch đã duyệt (`docs/superpowers/plans/2026-08-31-ai-viral-shorts-clipper.md`):

**File production & GUI:**
- NEW `autodub/content/viral_clipper.py` (AI Direct API + Heuristic Highlight Analyzer + Boundary Snapping)
- NEW `autodub/media/clipper.py` (ASS Subtitle Slicer & FFmpeg 9:16 Reframe Exporter)
- NEW `autodub_gui/viral_clipper_dialog.py` (Qt GUI Viral Shorts Studio: thẻ Clip, xem trước, 1-click export)
- MODIFY `autodub/editor.py` (`get_or_analyze_viral_clips`, `export_project_short_clip`, `viral_clips.json`)
- MODIFY `autodub_gui/pages/editor_panels.py` (Nút "AI Tạo Shorts & Reels (9:16)" trong ExportPanel)
- MODIFY `autodub_gui/pages/editor_export.py` & `autodub_gui/pages/editor_page.py` (Signal & Handler kết nối)

**Kiểm thử:**
- NEW `tests/test_viral_clipper.py` (4 tests)
- NEW `tests/test_clipper_media.py` (2 tests)
- NEW `tests/test_viral_clipper_dialog.py` (2 tests)
- Full regression suite: **974 / 974 passed (100%)** trong 74.37s. Không còn lỗi emoji hay hardcoded hex.

---

TASK-1→6 xong theo `.artifacts/tasks/voice-sync.md`. Final audit: **PASS** (`.artifacts/reviews/final-audit-voice-sync.md`, review chi tiết TASK-1→5 ở `voice-sync-TASK-1-5.md`).

**File production:**
- NEW `autodub/speech/boundaries.py` (refine biên VAD→speech bằng RMS), `autodub/media/voice_timing.py` (`fit_voice_to_slot`/`_decide_tempo`)
- MODIFY `autodub/media/timing.py` (`plan_voice_placements` thay `plan_placements`; apply gán dub_*/tempo_factor/timing_adjustment + log [VOICE-SYNC]), `autodub/pipeline.py` (refine sau ASR; tts_actual_duration; VOICE_SPEED legacy gate + guard `_apply_voice_speed`; warning VIDEO_SPEED), `autodub/config.py` (5 settings mới + comment)
- Docs: `docs/VOICE_SYNC_REVERSE_ENGINEERING.md`, `docs/VOICE_SYNC_DESIGN.md`, `docs/VOICE_SYNC_BENCHMARK.md` (sinh từ test)

**Test:** full suite **728 passed** (690 cũ + 38 mới; 690 cũ gồm 630 gốc + 60 của asr-accuracy TASK-1..4). Bug HIGH duy nhất (gate legacy bỏ sót `_apply_voice_speed`) bắt trong review TASK-4 và sửa ngay.

**Còn lại (ngoài scope):** đo trên video thật (CHƯA XÁC ĐỊNH); compaction bản dịch tự động cho câu VI >1.15× (chỉ flag); asr-accuracy-boost TASK-5→7 vẫn TẠM DỪNG.

---

## asr-accuracy-boost — HOÀN THÀNH TOÀN BỘ ✅ (TASK-1 -> TASK-7)

## TASK-7 — Integration Test & Final Audit ✅
- **Ngày:** 2026-09-02
- **File:** `tests/test_asr_accuracy_integration.py` (NEW, E2E flow test), `.artifacts/reviews/final-audit-asr-accuracy-boost.md` (Final Audit Report).
- **Kết quả Regression:** **1027 / 1027 passed (100%)** trong 153s.
- **Audit:** PASS toàn bộ 11/11 Acceptance Criteria.

## TASK-6 — Pipeline wiring + settings + ASR source ✅
- **Ngày:** 2026-09-02
- **File:** `autodub/config.py` (`asr_use_vocals`), `autodub/pipeline.py` (`_asr_source`, Step 3 OCR/Fusion integration), `tests/test_pipeline_asr_source.py` (NEW, 2 tests), `tests/test_pipeline_wiring.py` (NEW, 1 test).
- **Kết quả:** 3/3 tests pass. Nối hoàn chỉnh Step 3 với vocals 16kHz resample và OCR fusion fail-safe.
- **Code review:** PASS (`.artifacts/reviews/TASK-6.md`).

## TASK-5 — Fusion engine + scoring ✅
- **Ngày:** 2026-09-02
- **File:** `autodub/text/fusion.py` (hằng số `W_*`, hằng số ngưỡng, `fuse()`), `tests/test_fusion_scoring.py` (NEW, 7 tests), `tests/test_fusion_invariants.py` (NEW, property tests).
- **Kết quả:** 18/18 tests pass. Invariants thỏa mãn: start < end, non-overlapping, len(fused) >= len(asr), passthrough an toàn.
- **Code review:** PASS (`.artifacts/reviews/TASK-5.md`).

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
