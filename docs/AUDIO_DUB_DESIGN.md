# AUDIO DUB — Thiết kế (Phase 3)

> Đích: dubbing thực tế — khi nhân vật TQ cất tiếng, giọng VI phát gần
> đồng thời; hai track chồng nhau; TQ duck xuống nền THEO CÂU NÓI TQ;
> video giữ tốc độ gốc. Đối chiếu gap từ AUDIO_DUB_REVERSE_ENGINEERING.md.

## Kiến trúc đích (khớp sơ đồ spec Phase 3)

```
SOURCE VIDEO
     │
     ├── ORIGINAL AUDIO (giữ nguyên, KHÔNG replace)
     │       └── Speech-aware ducking:
     │             ngoài speech = mức nền (bg_duck_db, wizard −5dB)
     │             trong speech  = ORIGINAL_VOICE_DUCK_DB (mặc định −16dB)
     │             attack DUCK_ATTACK_MS / release DUCK_RELEASE_MS
     │
     └── VIETNAMESE TTS
             └── dub_start = speech_start − DUB_PRE_ROLL_MS (mặc định 0)
             └── lặng đầu clip đã trim (guard 120ms)
             └── natural tempo; KHÔNG ép về duration gốc
             ↓
        AUDIO MIXER (merge_segments — numpy block, _soft_limit)
             ↓
        FINAL AUDIO (1 stream = mix thật của 2 track)
             ↓
      VIDEO + FINAL AUDIO (merge_video)
```

## Thay đổi

### 1. Duck theo SPEECH SEGMENT TQ (gap C — thay đổi lõi)

`merge_segments` (media/audio.py) nhận thêm:

```python
speech_intervals: list[tuple[float, float]] | None  # (speech_start, speech_end) — timeline đã rescale
speech_duck_db: float                               # DIP tương đối so nền tĩnh
duck_attack_s / duck_release_s: float
```

- Envelope `_duck_envelope` đổi nguồn interval từ dub-interval sang
  `speech_intervals` và nhận attack/release làm tham số (bỏ hardcode).
- `dip_db = ORIGINAL_VOICE_DUCK_DB − bg_duck_db` (caller tính) — tổng
  mức TQ khi đang nói đúng bằng `ORIGINAL_VOICE_DUCK_DB`; ngoài speech
  nền về mức tĩnh như cũ. Không bao giờ boost (clamp dip ≤ 0).
- `BG_DUCK_VOICE_DB` cũ giữ nguyên cho chế độ **demucs** (duck nhạc nền
  khi có giọng VI); chế độ **duck** chuyển hoàn toàn sang hệ mới.

### 2. Settings mới (config.py + tab Cài đặt + .env.example)

| Khóa | Mặc định | Phạm vi | Ý nghĩa |
|---|---|---|---|
| `ORIGINAL_VOICE_DUCK_DB` | −16 | −30…0 | Mức TỔNG tiếng TQ khi nhân vật đang nói |
| `DUCK_ATTACK_MS` | 80 | 10…500 | Thời gian trượt xuống |
| `DUCK_RELEASE_MS` | 140 | 10…1000 | Thời gian trượt lên |
| `DUB_PRE_ROLL_MS` | 0 | 0…80 | Đẩy sớm onset VI (mặc định 0) |

Preset (ghi trong hint, chỉnh bằng slider): NATURAL −16 · CLEAR
VIETNAMESE −20 · BALANCED −12. Headroom: mixer cộng mẫu +
`_soft_limit` (tanh mềm) như hiện tại — không clipping.

### 3. Pre-roll (gap B, nhỏ)

`plan_voice_placements(..., pre_roll_s=0.0)` — `_natural()` =
`max(0, speech_start − pre_roll_s)`. `apply_soft_timing` đọc
`settings.dub_pre_roll_ms`. Ưu tiên scheduler giữ nguyên như spec Phase 10:
`dub_start = speech_start` → natural → mượn lặng → nén nhẹ (≤1.15×) →
overlap nhỏ chỉ là fallback. KHÔNG slow video; VIDEO_SPEED ≠ 1 chỉ là
compatibility mode (đã scale đồng đủ 3 tầng sau fix 28f73c8).

### 4. Không đụng

- Placement per-segment (voice-sync) — đã đạt `speech_start_error ≈ 0`.
- Không ép `dub_duration == source_duration`; VN dài/ngắn hơn đều hợp lệ.
- Không đổi demucs/none; không đổi merge_video; không amix/adelay.

## Test (Phase 13 — tests/test_audio_dub_mix.py)

5 scenario của spec ở 3 tầng: `_duck_envelope` thuần (gain đo được theo
khoảng), `plan_voice_placements` (onset khớp speech_start, không bám
dub-end câu trước), và `merge_segments` integration với WAV thật (đo RMS
nền trong/ngoài speech ≈ tỉ lệ dip; onset VI đo bằng năng lượng).

## Render test (Phase 14 — scripts/render_audio_dub_test.py)

Cửa sổ 60s của video thật (prefetch còn trên máy): audio gốc thật, speech
intervals giả lập đều, "giọng VI" = tone đặt đúng onset qua đúng code
`merge_segments` + duck mới; mux bằng `merge_video`. Đo bằng ffprobe +
numpy: 1 audio stream, peak ≤ −1 dBFS, mức nền trong speech ≈ −16dB so
ngoài speech, 2 track chồng (năng lượng VI + nền cùng tồn tại trong cửa
sổ speech). Kết quả + benchmark trước/sau ghi vào
`docs/AUDIO_DUB_TEST_REPORT.md`.
