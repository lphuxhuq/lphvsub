# FINAL AUDIT — Feature: `asr-accuracy-boost` (Tăng cường độ chính xác ASR tiếng Trung)

## 1. Feature Tổng quan
- **Mục tiêu:** Giải quyết triệt để 3 nguyên nhân gây mất chữ/sai chữ khi nhận dạng giọng nói tiếng Trung (ASR):
  1. *RC-1: VAD clipping* — cắt mất vài trăm ms đầu/cuối câu.
  2. *RC-2: Tạp âm & nhạc nền lớn* — làm giảm độ chính xác của ASR.
  3. *RC-3: Bỏ sót câu thoại* — VAD phát hiện tiếng nói nhưng ASR decode rỗng hoặc bỏ sót.
- **Giải pháp:**
  - VAD padding hai bên (`asr_vad_pad_s`) và empty-chunk signaling từ Paraformer worker.
  - Sử dụng trực tiếp `vocals.wav` đã tách từ Demucs (resample 16kHz mono sang `asr_vocals.wav`).
  - Selective OCR hard-sub (RapidOCR trong `.venv-ocr`) trên các suspect window kết hợp thuật toán Fusion Scoring 5 thành phần và 4 quy tắc ưu tiên.

---

## 2. Requirement & Acceptance Criteria Matrix

| Acceptance Criteria | Implementation | Test File | Trạng thái |
|---|---|---|---|
| **AC-1 (Passthrough)**: Không bật OCR hoặc không có hard-sub → giữ nguyên ASR | `autodub/text/fusion.py` | `tests/test_fusion_scoring.py` | **PASS ✅** |
| **AC-2 (Align & Merge)**: Bổ sung chữ thiếu đầu/cuối câu từ OCR không duplicate | `autodub/text/fusion.py` | `tests/test_fusion_alignment.py` | **PASS ✅** |
| **AC-3 (Suspect Detection)**: Gắn cờ đúng 4 heuristic (empty chunk, char rate, gap anomaly, unmatched OCR) | `autodub/text/fusion.py` | `tests/test_suspect_detection.py` | **PASS ✅** |
| **AC-4 (OCR Normalization)**: Chuẩn hóa chữ/số half-width, giữ CJK punct, merge frame liên tiếp trùng | `autodub/media/ocr.py` | `tests/test_ocr_normalize.py` | **PASS ✅** |
| **AC-5 (OCR Worker Protocol)**: JSON-lines protocol độc lập trong `.venv-ocr` | `autodub/media/ocr_worker.py` | `tests/test_ocr_normalize.py` | **PASS ✅** |
| **AC-6 (Selective OCR & Cache)**: Chỉ OCR các suspect window, cache theo hash | `autodub/media/ocr.py` | `tests/test_ocr_cache.py` | **PASS ✅** |
| **AC-7 (VAD Padding)**: Padding hai bên speech chunk không vượt biên | `autodub/speech/asr_paraformer_worker.py` | `tests/test_asr_worker_pad.py` | **PASS ✅** |
| **AC-8 (Empty Chunk Signaling)**: Worker emit `empty`/`num_empty` qua JSON-lines | `autodub/speech/asr_paraformer_worker.py`, `paraformer_transcriber.py` | `tests/test_paraformer_protocol.py` | **PASS ✅** |
| **AC-9 (ASR Source Demucs Vocals)**: `_asr_source` tự động chọn `vocals.wav` resample 16k mono | `autodub/pipeline.py` | `tests/test_pipeline_asr_source.py` | **PASS ✅** |
| **AC-10 (Timeline Invariants)**: Không đảo timeline, không chồng câu kề, len >= len(asr) | `autodub/text/fusion.py` | `tests/test_fusion_invariants.py` | **PASS ✅** |
| **AC-11 (Step 3 Wiring & Resume)**: Tích hợp an toàn Step 3, resume không chạy lại | `autodub/pipeline.py` | `tests/test_pipeline_wiring.py`, `tests/test_asr_accuracy_integration.py` | **PASS ✅** |

---

## 3. Architecture & Integration Review
- **Venv Isolation**: Độc lập tuyệt đối giữa các venv (`.venv-asr` cho Paraformer, `.venv-whisper` cho Whisper, `.venv-ocr` cho RapidOCR, `.venv-vieneu` cho VieNeu TTS).
- **Fail-safe Design**: Toàn bộ luồng OCR & Fusion được bọc `try...except`; nếu thiếu model, lỗi ffmpeg hoặc worker sập thì pipeline vẫn tự động fallback an toàn về ASR gốc mà không crash job lồng tiếng.
- **Tương thích ngược**: Format output `transcript_original.json` và `transcript_original.srt` giữ nguyên 100%, không phá vỡ các bước Dịch, Timing và TTS phía sau.

---

## 4. Regression & Performance Results
- **Full Regression Test Suite:** **1027 / 1027 tests PASSED (100%)** trong 153.13s (2 phút 33 giây).
- **Zero Breakage:** Toàn bộ 630 test gốc, cùng toàn bộ test của Voice-Sync, AI Viral Shorts Clipper và AI Subtitle Remover Inpaint đều pass hoàn toàn.

---

## 5. Kết luận
`PASS` — Toàn bộ các Unit từ TASK-1 đến TASK-7 của `asr-accuracy-boost` đã hoàn thành trọn vẹn, được kiểm thử đầy đủ và sẵn sàng đưa vào vận hành.
