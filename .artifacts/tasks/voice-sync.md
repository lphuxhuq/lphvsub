# Task Breakdown — voice-sync

> Design đã duyệt: `docs/VOICE_SYNC_DESIGN.md` (2026-08-22). Mỗi unit = hiểu → code → test → review; unit sau chỉ chạy khi unit trước PASS.

## 1. Dependency Graph

```
TASK-1 (boundaries.py refine)  ──┐
TASK-2 (voice_timing.py fit)  ──┼─► TASK-3 (scheduler mới trong timing.py)
                                  │        ↓
                                  │   TASK-4 (pipeline wiring + config + VOICE_SPEED legacy)
                                  │        ↓
                                  │   TASK-5 (logging [VOICE-SYNC] — gộp vào scheduler/apply nếu gọn)
                                  │        ↓
                                  └──► TASK-6 (benchmark fixtures + docs + final audit)
```

TASK-1 và TASK-2 độc lập nhau (làm song song được).

## 2. Danh sách Unit

### TASK-1 — `refine_speech_boundaries` + config

**Mục tiêu:** FR-A — thu hẹp biên VAD về biên speech thật bằng RMS energy; field `vad_*`/`speech_*`; không đụng `start/end/duration`.

**Dependency:** Không.

**File được phép sửa:**
- `autodub/speech/boundaries.py` (NEW)
- `autodub/config.py` (chỉ thêm `speech_boundary_refine` + env)
- `tests/test_speech_boundaries.py` (NEW — fixture wav sinh bằng numpy stdlib wave)

**File không được sửa:** timing.py, pipeline.py, audio.py, mọi file khác.

**Thay đổi dự kiến:** đúng design C1 (frame RMS 25ms/10ms hop, ngưỡng peak×0.12, ABS_FLOOR 0.004, margin 60ms, chỉ thu hẹp, min-delta 80ms, guard speech_duration ≥ max(0.2, 0.25×vad_dur)).

**Acceptance Criteria:**
- AC-4 (Case 4): VAD 10→12.2 với speech thật 10.4→11.8 (fixture sin-burst) → speech_* = ~10.4/11.8 (±60ms margin).
- Bất biến: vad_start ≤ speech_start ≤ speech_end ≤ vad_end; start/end/duration của input KHÔNG đổi.
- Biên đã tốt (delta < 80ms) → giữ nguyên; đoạn gần im (peak < floor) → giữ nguyên.
- 690 test cũ PASS.

**Test:** fixture wav 16k mono tự sinh (sine burst + silence); 6-8 unit test.

**Rủi ro:** fixture không giống speech thật → chọn tham số bảo thủ (chỉ thu hẹp + fallback).

**Rollback:** `SPEECH_BOUNDARY_REFINE=false`; module mới chưa ai gọi.

---

### TASK-2 — `fit_voice_to_slot` + config

**Mục tiêu:** FR-C — quyết định tempo per-clip + render atempo (cache mtime).

**Dependency:** Không (song song TASK-1).

**File được phép sửa:**
- `autodub/media/voice_timing.py` (NEW)
- `autodub/config.py` (chỉ thêm `voice_fit_min_speed`/`voice_fit_max_speed` + env)
- `tests/test_voice_timing_fit.py` (NEW — wav fixture)

**File không được sửa:** timing.py, audio.py (chỉ import `apply_atempo`), pipeline.py.

**Thay đổi dự kiến:** design C2: FitResult + pure `_decide_tempo(actual, available, min_speed, max_speed, min_worthwhile)` + render qua `apply_atempo` vào out_dir (cache: dst mới hơn src và đúng thời lượng kỳ vọng thì bỏ qua — copy pattern timing.py:173-179).

**Acceptance Criteria:**
- actual ≤ target → tempo 1.0, KHÔNG render.
- want ≤ max_speed → tempo=want (render khi ≥ 1.02).
- want > max_speed → tempo=max_speed, KHÔNG vượt.
- KHÔNG bao giờ tempo < 1.0 (stretch).
- Cache hit không chạy ffmpeg lần 2 (mock counter).
- 690+ test cũ PASS.

**Test:** pure `_decide_tempo` mọi nhánh + render thật bằng ffmpeg tại chỗ (wav 0.5s fixture, atempo 1.1 → đo lại duration).

**Rủi ro:** atempo đổi pitch nhẹ — có sẵn trong project (đã dùng), chấp nhận.

**Rollback:** module mới chưa ai gọi.

---

### TASK-3 — Scheduler `plan_voice_placements` thay `plan_placements`

**Mục tiêu:** FR-D — drift ≤ 0.15s, silence-aware, per-segment tempo; mở rộng `apply_soft_timing` gán field dub_*.

**Dependency:** TASK-1 (dùng speech_* — fallback khi vắng), TASK-2 (`_decide_tempo` chia sẻ).

**File được phép sửa:**
- `autodub/media/timing.py`
- `autodub/config.py` (chỉ thêm `timing_max_start_drift_s` + env clamp 0-1.5)
- `tests/test_timing.py` (cập nhật assertion theo semantic mới)
- `tests/test_timing_scheduler.py` (NEW)

**File không được sửa:** pipeline.py (call-site apply_soft_timing giữ nguyên), audio.py, srt.py.

**Thay đổi dự kiến:** design C3: hàm mới `plan_voice_placements` (thuần toán) THAY `plan_placements`; `apply_soft_timing` gọi hàm mới, mutate start/end=dub + gán dub_start/dub_end/dub_duration/tempo_factor/timing_adjustment/timing_reason; TimingReport += segments_fitted, max_drift_s = drift thật; giữ render/cache hiện tại.

**Acceptance Criteria:**
- AC-1..AC-3, AC-6, AC-7 (Case 1/2/3/6/7) pass unit test scheduler.
- AC-10: property test random — drift ≤ max_start_drift_s mọi câu, không cộng dồn, sort, dub_duration > 0, overlap mới ≤ 0.150 (trừ needs_compaction flag).
- Fallback: segments KHÔNG có speech_* (transcript cũ) → dùng start/duration — kết quả vẫn hợp lệ.
- test_timing.py cũ cập nhật theo hành vi mới (không còn shift 1.5s).
- Full suite PASS.

**Test:** 9 case spec + property random seed cố định (stdlib random).

**Rủi ro:** test cũ gắn chặt hành vi shift cũ → review từng assertion, đổi có chủ đích (ghi trong review file).

**Rollback:** revert unit (scheduler là thay thế trực tiếp — không flag song song, đã quyết định ở design mục 20.1).

---

### TASK-4 — Pipeline wiring + VOICE_SPEED legacy + VIDEO_SPEED warning

**Mục tiêu:** FR-B1 (tts_actual_duration), FR-E (legacy flags + warning), FR-F1/F2 (chèn refine, gán field).

**Dependency:** TASK-1, TASK-3.

**File được phép sửa:**
- `autodub/pipeline.py` (3 điểm: sau ASR gọi refine; `_one` gán tts_actual_duration; Step 6a đọc voice_speed_legacy; Step 5.5 warning)
- `autodub/config.py` (`voice_speed_legacy` + comment VIDEO_SPEED)
- `tests/test_pipeline_wiring_voice.py` (NEW)

**File không được sửa:** timing.py, boundaries.py, voice_timing.py nội dung; audio.py; retime.py (warning log đặt ở pipeline caller); tts/*; srt.py; editor.py; GUI.

**Thay đổi dự kiến:** đúng design C4. `speed_in_post`/`_apply_voice_speed` chỉ kích hoạt khi `settings.voice_speed_legacy and voice_speed≠1`.

**Acceptance Criteria:**
- AC-8: VIDEO_SPEED=1.0 → không gọi retime (test có sẵn giữ nguyên).
- AC-9: VIDEO_SPEED=0.82 → warning lip-sync xuất hiện (log capture), pipeline vẫn chạy.
- VOICE_SPEED=1.3 + legacy=false → KHÔNG clip nào bị atempo toàn cục (mock counter ffmpeg).
- VOICE_SPEED=1.3 + legacy=true → hành vi cũ giữ nguyên.
- Resume với transcript cũ (không field mới) → pipeline chạy bình thường (test integration nhỏ với fixture).
- Full suite PASS.

**Test:** monkeypatch như pattern TASK trước; test wiring với scheduler stub.

**Rủi ro:** đụng vùng pipeline lớn → chỉ chèn surgical, diff review từng hunk.

**Rollback:** env `VOICE_SPEED_LEGACY=true` trả VOICE_SPEED; refine off bằng 1 flag; scheduler đã thay ở TASK-3 (rollback riêng unit đó).

---

### TASK-5 — Logging `[VOICE-SYNC]`

**Mục tiêu:** FR-G1 — log per segment đúng format spec, sample log_every.

**Dependency:** TASK-3 (nơi phát log: trong apply_soft_timing sau placement).

**File được phép sửa:**
- `autodub/media/timing.py` (chỉ phần log)
- `tests/test_voice_sync_logging.py` (NEW)

**File không được sửa:** các file khác.

**Thay đổi dự kiến:** log `[VOICE-SYNC] segment=N source: a→b (d=…) tts: natural=… available=… tempo=… final: a→b adjustment=… drift=…`; sample: log_every như TTS (1 nếu ≤60 câu, ngược lại total//100).

**Acceptance Criteria:** AC-11 — đủ trường, không log tất cả khi video dài (đếm dòng < ~110 với 1000 câu), log đủ khi speed_adjusted/overlap.

**Test:** caplog pytest đếm + parse field.

**Rủi ro:** log quá dài chuỗi — truncate text không log nội dung câu (chỉ số).

**Rollback:** log only — vô hại.

---

### TASK-6 — Benchmark fixtures + docs + final audit

**Mục tiêu:** FR-G2 + AC-12/13/14 — sinh `docs/VOICE_SYNC_BENCHMARK.md` từ fixtures A/B/C, assert merge placement, final-audit skill.

**Dependency:** TASK-4, TASK-5.

**File được phép sửa:**
- `tests/test_voice_sync_benchmark.py` (NEW — fixtures wav tự sinh + metric)
- `docs/VOICE_SYNC_BENCHMARK.md` (sinh từ test)
- `.artifacts/reviews/final-audit-voice-sync.md` (NEW)

**File không được sửa:** production code (lỗi phát hiện → unit fix riêng theo skill fix-bug).

**Acceptance Criteria:**
- Benchmark có đủ metric spec: speech onset/end error, dub onset/end error, max/avg drift, số overlap, số forced compression, video speed — với 3 fixture A (chậm)/B (nhanh)/C (VI dài 1.4×).
- AC-14: merge đặt clip đúng (start + wav thật) trên fixture.
- Ma trận 14 AC trong final audit; kết luận PASS/FAIL.
- Full suite PASS.

**Rủi ro:** không có video thật → benchmark là fixtures tổng hợp; ghi rõ CHƯA XÁC ĐỊNH phần đo thực tế (đề xuất user chạy 1 video mẫu sau).

**Rollback:** N/A (test + doc).

---

## 3. Thứ tự thực hiện

1. **TASK-1 ∥ TASK-2** (độc lập).
2. **TASK-3** (sau 1+2).
3. **TASK-4** (sau 3).
4. **TASK-5** (sau 3, có thể làm ngay sau TASK-3 trước TASK-4 nếu tiện).
5. **TASK-6** cuối — final-audit skill.

Sau mỗi unit: code-review skill + full suite trước khi sang unit kế. (Theo chỉ dẫn trước đó của user, tôi sẽ chạy liền mạch TASK-1→TASK-6 không dừng chờ giữa các unit, trừ khi phát hiện vấn đề ảnh hưởng kiến trúc.)

## 4. Change Budget

- Production: 2 file NEW (`boundaries.py` ~120 dòng, `voice_timing.py` ~110 dòng) + MODIFY `timing.py` (~150 dòng đổi), `pipeline.py` (~40 dòng chèn), `config.py` (~25 dòng) — tổng ≤ ~450 dòng, dưới trần 600 của NFR-1.
- Tests: 5 file NEW + cập nhật `test_timing.py`.
- Không đụng danh sách file bảo vệ của design mục 17.

TRẠNG THÁI: CHỜ DUYỆT TASK
