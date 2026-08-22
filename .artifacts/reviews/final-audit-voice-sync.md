# FINAL AUDIT — voice-sync

## Feature

Voice-sync: dub tiếng Việt khớp hình — speech boundary refinement + per-segment tempo fitting + adaptive scheduler (thay shift 1.5s) + legacy hóa VIDEO/VOICE_SPEED + logging/benchmark.

## Requirement Matrix

| Requirement (`.artifacts/requirements/voice-sync.md`) | Implementation | Test | Status |
|---|---|---|---|
| FR-A1-A4 refine boundaries (chỉ thu hẹp, giữ vad_*+speech_*, không đụng field cũ) | `autodub/speech/boundaries.py` | `test_speech_boundaries.py` 8 test (AC-4/Case 4) | PASS |
| FR-B1/B2 field mới song song, KHÔNG field trùng source_* | timing.py apply + pipeline `_one` gán `tts_actual_duration`; design ghi alias tài liệu | test apply gán dub_*/duration giữ gốc | PASS |
| FR-C1-C3 fit_voice_to_slot (min 0.9/max 1.15, silence→tempo→overlap ≤150ms, không stretch, không shift dây chuyền) | `autodub/media/voice_timing.py` + scheduler | `test_voice_timing_fit.py` 9 + `test_timing.py` (Case 1/2/3) | PASS |
| FR-D1-D5 scheduler: onset ≈ speech_start ≤0.15s, silence-aware, không drift tích luỹ, tempo một chỗ | `plan_voice_placements` (timing.py) | Case 6/7 + property + benchmark A/B/C | PASS |
| FR-E1-E4 VIDEO_SPEED=1.0 mặc định + warning; VOICE_SPEED legacy; không auto-set | config comment đổi, warning Step 5.5, `voice_speed_legacy` gate (guard cả `_apply_voice_speed`) | `test_pipeline_wiring_voice.py` 6 test (AC-8/9) | PASS |
| FR-F1/F2/F3 wiring + merge dùng start+wav thật | pipeline 3 điểm chèn; merge KHÔNG đổi (RE xác nhận đúng sẵn) | AC-14 `test_merge_places_clip_at_dub_start` (RMS cửa sổ im/lạnh/ồn) | PASS |
| FR-G1 log [VOICE-SYNC] đủ trường, sample | apply_soft_timing | `test_voice_sync_logging.py` 3 test (AC-11) | PASS |
| FR-G2 benchmark 3 fixtures đủ metric | `test_voice_sync_benchmark.py` sinh `docs/VOICE_SYNC_BENCHMARK.md` (AC-12) | 6 test | PASS |
| NFR-3 full suite cũ | — | **728 passed** (690 cũ + 38 mới), 0 fail | PASS |
| NFR-1 ≤600 dòng production | ~450 dòng (2 NEW + 3 MODIFY) | diff review | PASS |
| NFR-5 không dependency mới | numpy/ffmpeg có sẵn | — | PASS |

## Architecture

Đúng `docs/VOICE_SYNC_DESIGN.md`: refine sau ASR (idempotent, chạy cả resume) → annotate_slots theo speech thật → TTS natural + tts_actual_duration → scheduler mới thay plan_placements (call-site `apply_soft_timing` pipeline KHÔNG đổi) → merge không đụng. TimingReport schema giữ nguyên → quality_report/timing_guide không vỡ.

## Integration

- Resume: transcript cũ thiếu field mới → `_resolve_slot`/`_natural` fallback `start/duration` — test `test_no_intervention...`, `test_missing_duration...`.
- Editor: dùng slot target như cũ; field mới optional không bắt buộc.
- VIDEO_SPEED≠1: scheduler chạy sau rescale trên timeline đã scale (mọi mốc cùng scale) + warning.

## Regression

728 passed. 2 test timing cũ được thay CÓ CHỦ ĐÍCH theo semantic mới (ôn lại ở review file; mỗi thay đổi ghi rationale trong tên/comment test mới).

## Security

Không surface mới. Không đổi exec/network.

## Performance

Refine 1 lượt RMS (tests chạy 0.4s cho cả suite mới); render chỉ clip tempo≠1 với cache mtime — như segments_timed cũ.

## Code Quality

Không duplicate (tempo decision dùng chung `_decide_tempo`); không debug code; hằng số named (TAIL_SILENCE_S, ALLOWED_RESIDUAL_S, MIN_SLOT_S, ENERGY_RATIO...); convention comment tiếng Việt giữ đúng giọng file.

## Documentation

`docs/VOICE_SYNC_REVERSE_ENGINEERING.md` (Phase 1-2) · `docs/VOICE_SYNC_DESIGN.md` · `docs/VOICE_SYNC_BENCHMARK.md` (sinh từ test) · reviews + tasks + progress ở `.artifacts/`.

## Rủi ro còn lại

1. **CHƯA XÁC ĐỊNH**: hiệu quả trên video Douyin thật (có môi) — benchmark là fixtures tổng hợp; cần 1 lần chạy thủ công để xác nhận cảm quan.
2. Refine RMS trên bản trộn nhạc có thể kém — sẽ cải thiện khi feature asr-accuracy-boost (TASK-5→7 đang tạm dừng) đưa vocals vào ASR.
3. Câu VI dài >1.15× chỉ được FLAG `needs_compaction` — compaction bản dịch tự động ngoài scope (theo requirement mục 14).

## Kết luận

**PASS**
