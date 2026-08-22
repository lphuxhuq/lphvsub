# VOICE SYNC — DESIGN

> Canonical design theo spec (docs/VOICE_SYNC_DESIGN.md). Requirement đã duyệt: `.artifacts/requirements/voice-sync.md` (DUYỆT 2026-08-22). RE/root-cause: `docs/VOICE_SYNC_REVERSE_ENGINEERING.md`. Review files các unit sẽ nằm ở `.artifacts/reviews/`.

## 1. Requirement đã duyệt

7 nhóm FR (A refine boundaries · B data model · C per-segment fitting · D adaptive scheduler · E VIDEO/VOICE_SPEED legacy · F pipeline/merge · G logging/benchmark) + 14 AC. Điểm chờ quyết → chốt ở mục 20.

## 2. Kiến trúc hiện tại liên quan (từ RE)

```
ASR (VAD boundary coarse) → translate → TTS natural (target=None)
→ [retime ×scale nếu VIDEO_SPEED<1] → VOICE_SPEED atempo toàn cục
→ plan_placements (shift trần 1.5s + atempo ≤1.1 hiếm) → merge (start + wav thật)
```

## 3. Kiến trúc đề xuất

```
ASR → refine_speech_boundaries (NEW speech/boundaries.py, RMS numpy)
        seg += {vad_start, vad_end, speech_start, speech_end, speech_duration}
     → annotate_slots (slot budget theo speech_duration — speech thật)
     → translate → TTS natural → seg["tts_actual_duration"] = TTSResult
     → [Step 5.5 VIDEO_SPEED legacy: như cũ + warning lip-sync]
     → postprocess loudnorm (VOICE_SPEED legacy chỉ khi bật flag)
     → plan_voice_placements (timing.py — scheduler mới) + fit_voice_to_slot
        (NEW media/voice_timing.py): dub_start ≈ speech_start (drift ≤0.15s),
        slot = speech_duration + trailing silence, per-segment tempo [0.9..1.15]
        → seg += {dub_start, dub_end, dub_duration, tempo_factor,
                  timing_adjustment, timing_reason}; start/end = dub (một nguồn sự thật)
     → merge_segments (KHÔNG đổi) → mux
```

## 4. Component thay đổi

### C1 — `autodub/speech/boundaries.py` (NEW) — FR-A

```python
def refine_speech_boundaries(segments, wav_path, settings) -> list[dict]
```
- Đọc 16k mono wav MỘT lần (wave + numpy, như audio.py pattern).
- Frame RMS: cửa 25ms, hop 10ms trên từng window `[vad_start, vad_end]`.
- Ngưỡng: `thresh = peak_rms × ENERGY_RATIO (0.12, ≈ -18dB dưới đỉnh)`.
  Guard: `peak_rms < ABS_FLOOR (0.004)` → giữ nguyên cả hai biên (đoạn gần im).
- `speech_start_raw` = frame đầu vượt ngưỡng − `LEAD_MARGIN_S` (0.06);
  `speech_end_raw` = frame cuối + `TAIL_MARGIN_S` (0.06).
- Chỉ THU HẸP vào `[vad_start, vad_end]`; side nào thu hẹp < `REFINE_MIN_DELTA_S` (0.08) → giữ biên cũ (FR-A2 "đã tốt").
- Bảo toàn: `speech_duration ≥ max(0.2, 0.25 × vad_duration)`, nếu không → giữ nguyên.
- Không tạo overlap (chỉ thu hẹp + vad windows không giao).
- Gán field; **không đụng** `start/end/duration`.
- Config: `speech_boundary_refine: bool = True` (env `SPEECH_BOUNDARY_REFINE`).

### C2 — `autodub/media/voice_timing.py` (NEW) — FR-C

```python
@dataclass
class FitResult:
    tempo_factor: float      # 1.0 = giữ natural
    out_path: str            # path wav sau fit (== input khi tempo 1.0)
    rendered: bool           # có chạy atempo không

def fit_voice_to_slot(wav_path, target_duration, out_dir, *,
                      min_speed=0.90, max_speed=1.15,
                      min_worthwhile=1.02) -> FitResult
```
- `actual = wav_duration_s(wav)`; `actual ≤ target` → tempo 1.0, không render.
- `want = actual/target`; `want ≤ max_speed` → tempo=want (bỏ qua nếu < min_worthwhile).
- `want > max_speed` → tempo=max_speed (phần thiếu còn lại là quyết định của SCHeduler: overlap/flag — fit không tự vượt).
- `min_speed` chỉ là chặn dưới hợp đồng; KHÔNG bao giờ kéo dài (stretch) — natural được giữ (FR-C1).
- Render qua `apply_atempo` có sẵn; cache mtime như segments_timed.

### C3 — Scheduler `plan_voice_placements` trong `timing.py` — FR-D (thay trực tiếp `plan_placements`)

```python
def plan_voice_placements(segments, durations, *,
                          max_start_drift_s, min_gap_s,
                          min_speed, max_speed) -> tuple[list[dict], TimingReport]
```
Từng câu i (THUẦN TOÁN, không đụng file — render vẫn ở apply):
1. `natural = speech_start` (fallback `seg["start"]` — transcript cũ/resume không có field mới).
2. `slot = speech_duration` (fallback `duration` / `end-start`), floor 0.3s.
3. `start = clamp(max(natural, prev_dub_end + min_gap_s), natural, natural + max_start_drift_s)`
   → drift = start − natural ≤ 0.15s theo xây dựng (FR-D2/D3: tham chiếu nguồn, không cộng dồn).
4. Silence-aware: `usable_end = next_speech_start − min_gap_s` (câu cuối: +`TAIL_SILENCE_S` 1.0s);
   `available = max(slot, usable_end − start)`.
5. Tempo: gọi đúng logic fit (chia sẻ hàm pure `_decide_tempo(actual, available, min_speed, max_speed)`)
   → `tempo`, `timing_adjustment` ∈ none | silence | tempo | silence+tempo | overlap.
6. `residual = actual/tempo − available`; residual ≤ 0.150 → chấp nhận (overlap flag);
   residual lớn hơn → `timing_reason="needs_compaction"` (chỉ báo cáo — không tự dịch lại, ngoài scope).
7. `dub_end = start + actual/tempo`; placements[i] = {start, tempo, adjustment, reason, drift, slot, available}.

`apply_soft_timing` (giữ tên + call-site pipeline không đổi):
- gọi `plan_voice_placements`, render tempo≠1 (cache cũ giữ nguyên), mutate
  `start/end` = dub + gán `dub_start/dub_end/dub_duration/tempo_factor/timing_adjustment/timing_reason`.
- Log `[VOICE-SYNC]` per segment (format spec Phase 16, sample log_every như TTS).
- `TimingReport` mở rộng thêm: `segments_fitted` (tempo>1), `max_drift_s` = drift thật (≤0.15), `segments_overlapped` giữ nghĩa cũ.

### C4 — Pipeline — FR-F/E

- Sau Step 3 (trước `annotate_slots`, pipeline.py:441): gọi `refine_speech_boundaries` khi bật.
- `_synthesize_segments._one`: sau khi có result → `seg["tts_actual_duration"] = result["actual_duration"]` (dict mutate an toàn — segments là shared list).
- Step 6a: `voice_speed` chỉ áp khi `settings.voice_speed_legacy` (mới, default False); mặc định speed=1.0 (chỉ loudnorm+fade).
- Step 5.5: thêm 1 dòng warning khi VIDEO_SPEED<0.999: "may affect visual speech/lip synchronization" + comment config.py:176-180 đổi khuyến nghị 0.82 → "optional legacy; ảnh hưởng lip-sync".
- Step 6b: `apply_soft_timing` internals mới (C3) — call-site pipeline.py:636-641 KHÔNG đổi.
- Scheduler dùng `speech_*` có mặt; resume với transcript cũ (không field) → fallback tự động (C3 bước 1-2).

### C5 — Config mới (`config.py`)

| Setting | Default | Env | Ghi chú |
|---|---|---|---|
| `speech_boundary_refine` | true | `SPEECH_BOUNDARY_REFINE` | FR-A |
| `timing_max_start_drift_s` | **0.15** | `TIMING_MAX_START_DRIFT_S` (clamp 0-1.5) | thay nghĩa `timing_max_drift_s` cũ — giữ field cũ cho compat, scheduler mới KHÔNG đọc |
| `voice_fit_min_speed` | 0.90 | `VOICE_FIT_MIN_SPEED` | chặn dưới hợp đồng |
| `voice_fit_max_speed` | 1.15 | `VOICE_FIT_MAX_SPEED` (clamp 1.0-1.3) | trần atempo per-segment |
| `voice_speed_legacy` | false | `VOICE_SPEED_LEGACY` | bật = hành vi VOICE_SPEED toàn cục cũ |

`timing_max_atempo` cũ: giữ (compat) — scheduler mới đọc `voice_fit_max_speed`.

## 5. Data Flow

`16k wav → RMS → speech_* fields → slot budget → dịch → TTS natural + tts_actual_duration → scheduler (placement thuần toán) → render tempo per clip (cache (id,tempo)) → segments_timed → merge (start + wav thật)`. Field mới song song, không thay thế field cũ.

## 6. Control Flow

- `soft_timing_fit=false` → bỏ qua scheduler (như cũ). `speech_boundary_refine=false` → dùng biên VAD (fallback như transcript cũ).
- VIDEO_SPEED≠1 (user chủ động): rescale như cũ — scheduler chạy SAU rescale trên timeline retimed (slot đã scale) — đúng vì mọi mốc đều cùng scale.
- Lỗi refine (wav hỏng...) → warning + giữ biên VAD. Lỗi render atempo một clip → giữ clip gốc + giảm tempo về 1 + overlap flag (fail-safe như timing.py hiện tại).

## 7. Database — không có.

## 8. API Contract (internal)

- `plan_placements` bị THAY bằng `plan_voice_placements` (module-internal, chỉ timing.py + tests gọi — grep xác nhận không caller ngoài).
- `apply_soft_timing` giữ nguyên signature/return — pipeline không đổi.
- `TTSResult`/`synthesize`/`merge_segments` KHÔNG đổi.

## 9. UI Contract — không đổi struct; hint VIDEO_SPEED trong GUI text nếu nằm trong scope unit (low priority, tách PR nhỏ).

## 10. Validation

- refine: `vad_start ≤ speech_start ≤ speech_end ≤ vad_end`; speech_duration > 0; không giao kề (theo xây dựng).
- scheduler: `0 ≤ drift ≤ max_start_drift_s`; `tempo ∈ [1.0, max_speed]`; sort theo dub_start; `dub_duration = tts_actual/tempo`; overlap mới ≤ 0.150 trừ flag needs_compaction.

## 11. Error Handling

Mục 6. Thêm: clip 0s/None duration → skip fit, giữ hành vi `dur = durations[i] or 0.0` như cũ.

## 12. Security — không đổi (local, không exec input ngoài).

## 13. Performance

- refine: 1 lượt numpy RMS — < 1s / 10 phút video (NFR-4).
- fitting: chỉ render lại clip tempo≠1 — cùng chi phí segments_timed hiện tại.
- scheduler: O(n) thuần toán như cũ.

## 14. Testing (map AC)

- `tests/test_speech_boundaries.py`: fixture wav sin-burst + silence (sin wav sinh bằng numpy, không file nhị phân): thu hẹp đúng, margin, giữ nguyên khi delta nhỏ, guard gần-im, không đụng start/end.
- `tests/test_voice_timing_fit.py`: tempo decision mọi nhánh (AC-2/3).
- `tests/test_timing_scheduler.py`: 9 case spec (AC-1→9) + property test random (AC-10) + drift không cộng dồn (Case 6).
- `tests/test_voice_sync_logging.py`: format `[VOICE-SYNC]` đủ trường (AC-11).
- `tests/test_voice_sync_benchmark.py`: fixtures A(chậm)/B(nhanh)/C(VI-dài) → sinh `docs/VOICE_SYNC_BENCHMARK.md` đủ metric (AC-12); assert placement merge (AC-14).
- Regression: 690 test cũ PASS (AC-13); test retime/srt/timing cũ chỉnh theo hành vi mới của plan_placements (nếu assert shift 1.5s cũ → cập nhật语义 mới).

## 15. Migration/Rollback

- Rollback toàn bộ: `SPEECH_BOUNDARY_REFINE=false` + `timing_max_start_drift_s=1.5` + `voice_fit_max_speed=1.0`? — không hoàn toàn (scheduler đã thay plan_placements). Rollback đúng cấp độ: `soft_timing_fit=false` tắt scheduler; hoặc git revert unit scheduler. Không migration dữ liệu (field mới optional, resume không cần).

## 16. File dự kiến thay đổi

- NEW `autodub/speech/boundaries.py`, `autodub/media/voice_timing.py`
- MODIFY `autodub/media/timing.py` (scheduler mới + apply mở rộng), `autodub/pipeline.py` (3 điểm chèn nhỏ), `autodub/config.py` (5 settings + comment VIDEO_SPEED)
- NEW tests (mục 14, ~5 file) + chỉnh `tests/test_timing.py` theo semantic mới
- `docs/VOICE_SYNC_BENCHMARK.md` (sinh từ test)

## 17. File không được tự ý thay đổi

`autodub/media/audio.py` (merge/postprocess/atempo — chỉ import), `autodub/media/retime.py` (chỉ thêm warning ở caller), `autodub/speech/tts/*`, `autodub/text/srt.py`/`subtitles.py`, editor.py, GUI struct, worker ASR, mọi file feature asr-accuracy-boost đang dở.

## 18. Rủi ro

| Rủi ro | Giảm thiểu |
|---|---|
| MAX_START_DRIFT 0.15 quá chặt → nhiều câu bị ép tempo ở đầu | benchmark fixture + trần 1.5s vẫn đọc được từ env (0-1.5 clamp) |
| RMS refine sai trên nhạc to (ASR nghe bản trộn) | guard ABS_FLOOR + chỉ thu hẹp + fallback field; feature vocals-cho-ASR (asr-accuracy TASK-6) sẽ cải thiện đầu vào |
| Scheduler thay plan_placements → test cũ assert hành vi shift cũ | cập nhật test cùng unit, review đối chiếu từng assertion cũ |
| VI dài quá 1.15× → overlap còn lại | flag needs_compaction hiện report; compaction tự động ngoài scope (spec cho phép dừng ở report) |
| Editor re-synth chưa biết tempo_factor | field optional; editor dùng slot target như cũ |

## 19. Phương án đã cân nhắc

1. **Flag切换 scheduler cũ/mới** — loại: plan_placements là module-internal, `soft_timing_fit` đã là flag tổng; hai scheduler song song = dead code + double maintenance.
2. **Stretch (tempo<1) khi TTS ngắn** — loại: kéo dài giọng đọc nhân tạo kém tự nhiên; giữ natural (đúng FR-C1).
3. **Refine bằng word-timestamps Paraformer** — không có (chỉ Whisper có); RMS là lựa chọn engine-agnostic, nhẹ.
4. **Đổi merge_segments sang adelay ffmpeg** — loại: numpy mixer hiện tại đúng và nhanh hơn.
5. **Compaction bản dịch tự động khi residual lớn** — ngoài scope requirement (chỉ flag).

## 20. Quyết định thiết kế (chốt các điểm chờ của requirement mục 13)

1. **Thay trực tiếp `plan_placements`** — `soft_timing_fit` là flag bật/tắt tổng; không giữ scheduler cũ song song.
2. **MAX_START_DRIFT = 0.15s** mặc định (clamp env 0→1.5) — benchmark sẽ xác nhận; hằng số named `timing_max_start_drift_s`.
3. **Refine chạy ngay sau ASR, trước `annotate_slots`** — slot budget dịch bám speech thật.
4. **`voice_speed_legacy=false`** mặc định; bật → hành vi VOICE_SPEED toàn cục cũ nguyên vẹn.
5. `source_*` KHÔNG tạo field mới — alias tài liệu của `start/end/duration` (tránh double source of truth).
6. Scheduler đọc field mới nhưng **fallback đầy đủ** khi vắng mặt (resume/edit cũ) — không bắt buộc migrate.

TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ
