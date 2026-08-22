# Code Review — voice-sync TASK-1 → TASK-5

> Review từng unit thực hiện xong; chi tiết bug bắt được trong quá trình ghi ở từng mục. Full suite cuối: **728 passed** (690 cũ + 38 mới), 0 regression.

## TASK-1 — refine_speech_boundaries ✅
- `autodub/speech/boundaries.py` (NEW ~110 dòng), `config.py` (+`speech_boundary_refine`), `tests/test_speech_boundaries.py` (8 test).
- AC-4 đạt (VAD 10→12.2 → speech ~10.34/11.86); bất biến chỉ-thu-hẹp + không đụng start/end/duration có test; guard near-silent/min-duration; input không mutate; wav hỏng → fallback.
- Bug bắt trong dev: dòng rác trong fixture helper (`if False else`) — dọn trước khi chạy.
- **PASS**

## TASK-2 — fit_voice_to_slot ✅
- `autodub/media/voice_timing.py` (NEW), config (+2 settings), `tests/test_voice_timing_fit.py` (9 test).
- `_decide_tempo` thuần toán mọi nhánh; render thật qua ffmpeg đo lại duration (2.2s→~2.0s @1.1); cap 1.15; KHÔNG stretch (test bất biến); cache hit 0 render (counter).
- **PASS**

## TASK-3 — plan_voice_placements ✅
- Thay `plan_placements` (timing.py); `apply_soft_timing` đọc settings mới + gán dub_*/tempo_factor/timing_adjustment; TimingReport schema GIỮ NGUYÊN (segments_compressed nghĩa "tempo>1" như cũ — quality_report không đổi).
- 2 file test cũ cập nhật CÓ CHỦ ĐÍCH, ghi rõ semantic mới:
  - `test_overflow_shifts_next_segment_not_speed` (shift 1.1s) → thay bằng `test_onset_kept_when_tts_longer` + `test_silence_to_next_speech_is_borrowed_first`: onset giữ + silence mượn trước tempo.
  - `test_min_gap_respected` → `test_min_gap_yields_to_onset_priority`: drift-cap ưu tiên min-gap (overlap 50ms được ghi nhận thay vì đẩy start).
  - `test_apply_soft_timing_mutates_timeline`: cập nhật theo tempo-render + drift ≤0.15 + field dub_*.
- Bug bắt trong dev (test authoring, code đúng): kỳ vọng tempo 1.1 trong TH silence đủ chỗ (scheduler đúng là mượn silence); kỳ vọng min-gap 4.2 trong TH drift-cap kẹp còn 4.15.
- Case 1/2/3/6/7 + property (drift ≤0.15, không cộng dồn, không stretch) pass.
- **PASS**

## TASK-4 — pipeline wiring ✅
- 3 điểm chèn surgical: refine sau ASR (chạy cả resume-cache — idempotent), `seg["tts_actual_duration"]` trong `_one` (cả nhánh cached lẫn fresh), legacy gate VOICE_SPEED; warning VIDEO_SPEED ở Step 5.5; comment config bỏ "khuyến nghị 0.82".
- **BUG HIGH bắt và sửa ngay**: gate ban đầu chỉ kẹp biến `voice_speed` cục bộ nhưng Step 6a vẫn rơi vào `_apply_voice_speed` (đọc thẳng raw setting 1.3 → atempo toàn cục vẫn chạy). Sửa: guard `voice_speed_legacy` ngay đầu `_apply_voice_speed` + warning khi legacy on.
- Test: defaults, env legacy, _apply_voice_speed off/on (counter), source-wiring smoke. **PASS**

## TASK-5 — log [VOICE-SYNC] ✅
- Implement gộp trong `apply_soft_timing` (cùng file — như breakdown cho phép). Format đủ trường spec; sample log_every; câu tempo/overlap luôn log.
- Test: field presence, sampling bound, fitted-always-logged. **PASS**

## Security / Performance / Scope
- Không surface mới; refine 1 lượt numpy RMS; render chỉ clip tempo≠1 (cache giữ nguyên pattern).
- File bảo vệ (design mục 17) không đụng: audio.py, retime.py, tts/*, srt.py, subtitles.py, editor.py, GUI. Đổi: timing.py, pipeline.py, config.py + 2 module NEW — đúng budget (~450 dòng production).
