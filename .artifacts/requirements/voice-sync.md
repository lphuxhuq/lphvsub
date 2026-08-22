# Phân tích yêu cầu — voice-sync (dub tiếng Việt khớp hình)

> Feature: `voice-sync`. Nguồn: spec user (17 phase) + RE/root-cause `docs/VOICE_SYNC_REVERSE_ENGINEERING.md` (RC-S1..S5). Skill file: `.artifacts/requirements/voice-sync.md`.

## 1. Mục tiêu

Voice lồng tiếng Việt khớp với video: dub bắt đầu đúng thời điểm speech thật (onset), từng câu TTS được fit vào slot của chính nó (per-segment tempo, silence-aware) thay vì shift dây chuyền/speed toàn cục/làm chậm video. Drift không tích luỹ; VIDEO_SPEED mặc định 1.0 và không còn là cơ chế sync chính.

## 2. User Story

- Người xem không nhận ra giọng đọc "trễ hơn" hoặc "chèn nhau" so với môi/âm thanh gốc.
- Người làm sub muốn biết chính xác câu nào bị fit bằng cách nào (tempo/silence/compaction) và drift bao nhiêu — qua log `[VOICE-SYNC]` + benchmark.
- User muốn mặc định video giữ tốc độ gốc; làm chậm video chỉ khi tự ý chọn (kèm warning lip-sync).

## 3. Functional Requirements

### Nhóm A — Speech boundary refinement (RC-S3, spec Phase 4-5)

- **FR-A1**: Hàm `refine_speech_boundaries(segments, audio_path, ...) -> segments` module riêng (đề xuất `autodub/speech/boundaries.py`): với mỗi segment, tính `speech_start`/`speech_end` sát biên speech thật từ energy/RMS (numpy có sẵn; không thêm dependency) trên biên hẹp hơn của VAD window.
- **FR-A2**: Nguyên tắc refine: chỉ thu hẹp (speech_start ≥ vad_start, speech_end ≤ vad_end), giữ nguyên nếu biên đã tốt (delta < ngưỡng ~80ms), không tạo overlap kề, không cắt mất âm (margin an toàn 30-60ms), không xóa silence có ý nghĩa (chỉ shave phần im lặng đầu/cuối).
- **FR-A3**: Mỗi segment giữ cả hai: `vad_start`/`vad_end` (coarse) và `speech_start`/`speech_end` (refined) để debug (spec Phase 5). `start`/`end` gốc KHÔNG đổi ở bước này (consumer cũ không đổi ý nghĩa).
- **FR-A4**: Áp dụng cho cả Paraformer (biên VAD thô) lẫn Whisper (biên word-based — thường đã tốt, refine gần như no-op).

### Nhóm B — Timing data model (spec Phase 3/13)

- **FR-B1**: Bổ sung field theo TUẦN TỰ, không đụng field cũ (`start`/`end`/`duration` giữ nguyên semantic hiện tại để không phá resume-cache `transcript_vi.json` pipeline.py:383-390, editor, SRT):
  - `speech_start`, `speech_end`, `speech_duration` (từ nhóm A)
  - `tts_actual_duration` (gán sau TTS từ `TTSResult.actual_duration`)
  - `dub_start`, `dub_end`, `dub_duration` (kết quả scheduler)
  - `tempo_factor`, `timing_adjustment` (none|tempo|silence+tempo|overlap), `timing_reason`
- **FR-B2**: `source_start/source_end/source_duration` là alias đọc-hiểu cho `start/end/duration` hiện có trong doc — KHÔNG thêm field trùng (tránh double source of truth); ghi rõ trong design.

### Nhóm C — Per-segment TTS fitting (RC-S2, spec Phase 6)

- **FR-C1**: `fit_voice_to_slot(wav_path, target_duration, min_speed=0.90, max_speed=1.15) -> FitResult{tempo_factor, rendered_path}` đặt trong module mới `autodub/media/voice_timing.py`: actual ≤ target → giữ natural (tempo 1.0); actual > target → tempo = actual/target, clamp max_speed.
- **FR-C2**: Khi vượt max_speed, xử lý theo THỨ TỰ (không ép quá giới hạn): (1) tận dụng silence sau segment (mở rộng slot đến `speech_start` của câu kế hoặc gap trừ min_gap), (2) tăng tempo đến max_speed, (3) đánh dấu `timing_adjustment=overlap` cho phần thiếu rất nhỏ (≤150ms) — KHÔNG shift câu sau, KHÔNG drift tích luỹ.
- **FR-C3**: Mọi clip sau fitting giữ `tempo_factor` riêng — không còn MỘT VOICE_SPEED áp cho toàn bộ (VOICE_SPEED thành legacy/optional, xem FR-E).

### Nhóm D — Adaptive scheduler (RC-S1, spec Phase 7)

- **FR-D1**: Thay chiến lược `shift → compress → overlap` của `plan_placements` bằng: `speech_start (refined) → target slot (speech_DURATION, không phải VAD duration) → natural TTS duration → silence-aware fit → per-segment tempo → dub_start/dub_end`.
- **FR-D2**: `dub_start ≈ speech_start` là bất biến ưu tiên: drift start mỗi segment ≤ `MAX_START_DRIFT` (mặc định 0.15s — chọn theo ngưỡng lip-sync cảm nhận; hằng số có tên, config được).
- **FR-D3**: Mỗi segment tham chiếu timeline nguồn (như hiện tại) — drift KHÔNG cộng dồn qua các câu (bảo toàn tính chất tốt hiện có của plan_placements).
- **FR-D4**: Silence-aware: TTS dài hơn slot một chút → dùng khoảng lặng TRƯỚC câu kế (đúng cơ chế `t = max(natural, prev_end+gap)` nhưng trần drift收紧 từ 1.5s → MAX_START_DRIFT, phần tràn chuyển qua per-segment tempo của FR-C).
- **FR-D5**: atempo ép buộc trần cũ 1.1 được thay bằng khoảng `[min_speed, max_speed]` của FR-C (0.90-1.15) —統 nhất MỘT chỗ tính speed (bỏ nhân chồng VOICE_SPEED × atempo).

### Nhóm E — VIDEO_SPEED / VOICE_SPEED (RC-S4/S2, spec Phase 8)

- **FR-E1**: Default `VIDEO_SPEED=1.0` giữ nguyên (đã là 1.0 — chỉ bỏ "khuyến nghị 0.82" trong comment/GUI hint thành "optional legacy, ảnh hưởng lip-sync").
- **FR-E2**: Khi user chủ động đặt VIDEO_SPEED ≠ 1.0: scale video/subs/audio timeline đúng như hiện nay (giữ nguyên cơ chế rescale) + log warning "may affect visual speech/lip synchronization".
- **FR-E3**: `VOICE_SPEED` global: giữ setting để tương thích ngược nhưng KHÔNG còn áp mặc định trong luồng sync mới (chỉ khi user bật legacy flag). GUI default đưa về 1.0 nếu đang ≠ 1.0.
- **FR-E4**: Không tự động thay đổi VIDEO_SPEED để giải quyết TTS duration (không có code path nào tự set).

### Nhóm F — Pipeline & merge (spec Phase 11-12)

- **FR-F1**: `_synthesize_segments`: sau khi có `TTSResult.actual_duration`, gán `seg["tts_actual_duration"]`; KHÔNG truyền `target_duration` vào engine (engine vẫn render natural — giữ interface).
- **FR-F2**: Scheduler mới chạy ở vị trí `apply_soft_timing` hiện tại (Step 6b), nhận wavs đã hậu kỳ; output mutate `dub_start/dub_end` + gán `seg["start"]=dub_start`, `seg["end"]=dub_end` (SRT/merge vẫn đọc start/end — một nguồn sự thật).
- **FR-F3**: `merge_segments` đã dùng `seg["start"]` + wav đo thật (RE mục G) — KHÔNG sửa, chỉ thêm assertion/test chứng minh placement dùng dub_start + actual wav.

### Nhóm G — Logging & benchmark (spec Phase 15-16)

- **FR-G1**: Log `[VOICE-SYNC]` per segment theo format spec (source range, natural, available_slot, tempo, final, adjustment, drift) — sample log như TTS (log_every) để không ngập UI.
- **FR-G2**: `docs/VOICE_SYNC_BENCHMARK.md` sinh từ test合成 fixtures (3 video A/B/C) đo: speech onset/end error, dub onset/end error, max/avg drift, số overlap, số forced compression, video speed. Đo được bằng unit test trên fixture wavs (không cần video thật để CI).

## 4. Non-functional Requirements

- **NFR-1**: Không rewrite — tổng diff production dự kiến ≤ ~600 dòng, không đổi public API TTS/merge/SRT.
- **NFR-2**: Resume-safe: mọi file trung gian (clip đã fit) cache theo (id, tempo) như pattern segments_timed hiện tại; transcript cache 3 field cũ không đổi.
- **NFR-3**: Full suite cũ (690 test) PASS suốt quá trình làm.
- **NFR-4**: Refine + fitting thuần CPU numpy/ffmpeg có sẵn, thêm < 2s/video cho refine (một lượt RMS).
- **NFR-5**: Không thêm dependency mới.
- **NFR-6**: Editor/GUI không gãy: field mới là optional, editor không bắt buộc đọc.

## 5. Hành vi hiện tại (tóm tắt từ RE)

TTS natural (target=None) → [retime nếu VIDEO_SPEED<1] → VOICE_SPEED atempo toàn cục → soft-timing shift (trần 1.5s) + atempo ≤1.1 hiếm hoi → merge đặt theo start + wav thật. Root cause RC-S1..S5 (xem RE).

## 6. Module bị ảnh hưởng

| Module | Thay đổi |
|---|---|
| `autodub/speech/boundaries.py` (NEW) | refine_speech_boundaries |
| `autodub/media/voice_timing.py` (NEW) | fit_voice_to_slot |
| `autodub/media/timing.py` | scheduler mới (giữ plan_placements legacy hoặc thay thế trực tiếp — chốt design) |
| `autodub/pipeline.py` | gán tts_actual_duration; gọi boundaries sau ASR; gọi scheduler mới; bỏ VOICE_SPEED mặc định |
| `autodub/config.py` | MAX_START_DRIFT, min/max_speed; comment VIDEO_SPEED; legacy flag |
| `autodub/media/audio.py` | CHỈ thêm assertion/doc nếu cần — không đổi merge |
| GUI settings_fields.py | hint VIDEO_SPEED (nếu nằm trong scope cho phép — xem design) |

## 7. Dependency

numpy (có sẵn), ffmpeg atempo (có sẵn `apply_atempo`). Không dependency mới.

## 8. Constraint

- Timeline `start/end` single source of truth cho SRT/merge — field mới bổ sung, không thay thế.
- `.venv-asr` không đụng (refine chạy ở main env trên file 16k wav).
- Worker ASR standalone: không thêm field protocol (refine dùng output hiện có).
- Windows/Git Bash.

## 9. Edge Cases

- TTS ngắn hơn slot nhiều → giữ natural, KHÔNG kéo dài/nhân silence.
- Slot = 0 (speech_duration ~ 0 sau refine quá sát) → min slot 0.3s.
- Câu đầu/cuối video (không có silence kề) → chỉ tempo.
- VIDEO_SPEED ≠ 1 + scheduler mới: slot tính trên timeline retimed (đã scale) — phải thử nghiệm riêng (Case 9).
- Câu kề speech gap < 60ms (nói dính) → không dồn trễ, chỉ tempo.
- Wav lỗi/0s → fallback giữ hành vi cũ + log.
- Editor re-synth 1 câu → vẫn dùng scheduler mới cho câu đó (target_duration=slot).

## 10. Security

Không surface mới (toàn bộ local). Không đổi network/exec.

## 11. Performance

- Refine: 1 lượt RMS numpy trên 16k mono — < 1s cho video 10 phút.
- Fitting: chỉ render lại clip có tempo ≠ 1 (ffmpeg atempo per clip — như segments_timed hiện tại).
- Scheduler: thuần toán như cũ.

## 12. Acceptance Criteria

| # | Criterion (map Case spec) | Kiểm tra |
|---|---|---|
| AC-1 | Case 1: TTS 1.6s / source 2.0s → không gap bất thường, dub_start = speech_start, câu sau không shift | Unit scheduler |
| AC-2 | Case 2: TTS 2.2s / 2.0s → tempo 1.1 (≤1.15), video KHÔNG chậm, drift < 0.15s | Unit scheduler |
| AC-3 | Case 3: TTS 3.0s / 2.0s → KHÔNG ép 1.5x; dùng silence; report adjustment đúng | Unit fit + report |
| AC-4 | Case 4: VAD 10→12.2, speech 10.4→11.8 → final 10.4→11.8 | Unit refine |
| AC-5 | Case 5: ASR thiếu text → không crash, timing giữ, có hook | Unit (empty chunk path) |
| AC-6 | Case 6: A=2.5 B=2.8 C=3.0 liên tiếp → drift không tăng dần theo A+B+C | Unit scheduler 3 câu |
| AC-7 | Case 7: gap 1s → scheduler dùng silence, dub_end có thể vượt source_end nhưng < speech_start(B) | Unit scheduler |
| AC-8 | Case 8: VIDEO_SPEED=1.0 → không gọi retime (đã có — giữ test) | Regression |
| AC-9 | Case 9: VIDEO_SPEED=0.82 → timeline đồng bộ + warning lip-sync | Unit + log assert |
| AC-10 | Bất biến scheduler: mọi segment drift_start ≤ 0.15s, không overlap mới (trừ overlap flag ≤150ms), sort theo dub_start, dub_duration > 0 | Property test random |
| AC-11 | `[VOICE-SYNC]` log đủ trường spec, sample không ngập | Log capture test |
| AC-12 | Benchmark fixtures A/B/C sinh docs/VOICE_SYNC_BENCHMARK.md với đủ metric | Test sinh file |
| AC-13 | Full suite cũ PASS | CI |
| AC-14 | Placement merge dùng start + wav thật (FR-F3) | Test merge với wav fixture |

## 13. Điểm chưa rõ

1. **`plan_placements` cũ giữ làm legacy hay thay hẳn?** — Cân nhắc: thay trực tiếp (đơn giản, có test bọc) vs flag切换 (an toàn, thêm nhánh). *Giả định an toàn: thay trực tiếp + giữ `soft_timing_fit` làm flag bật/tắt toàn bộ scheduler mới (off = bỏ qua fitting như hiện tại khi false).*
2. **MAX_START_DRIFT = 0.15s có quá chặt khi speech-detect onset trễ?** — Quan trọng vì quyết định có đạt AC-10 không. *Giả định: 0.15s chọn theo ngưỡng cảm nhận AV; benchmark fixture sẽ xác nhận và có thể chỉnh.*
3. **Refine chạy trước hay sau translate?** — Trước (ngay sau ASR) để slot budget cho dịch đúng speech thật. *Giả định: ngay sau ASR, trước annotate_slots.*
4. **VOICE_SPEED legacy flag tên gì và GUI default?** — *Giả định: `VOICE_SPEED_LEGACY=false` mặc định; GUI không đổi struct, chỉ hint.*

## 14. Ngoài phạm vi

- Không làm OCR/ASR cross-check (Phase 9 spec) — thuộc feature asr-accuracy-boost đang tạm dở (TASK-5→7), tách riêng.
- Không sửa TTS engine render duration (interface đã đủ).
- Không đổi merge_segments algorithm (đã đúng).
- Không benchmark bằng video thật cần download (dùng fixtures tổng hợp; đo trên video thật là việc thủ công sau).
- Không đụng editor UI ngoài tối thiểu.

TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH
