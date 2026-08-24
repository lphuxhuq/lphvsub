# AUDIO DUB — Reverse Engineering (Phase 1 + 2)

> Truy vết thực tế của đường âm thanh lồng tiếng theo 10 câu hỏi của spec,
> file:function:khai báo kèm theo. Không code trong phase này.
> Ngày: 2026-08-23 · Cây code: `main` @ `d98dade`.

## Luồng end-to-end (trace)

```
SOURCE VIDEO
  │ Step 2  extract_audio_dual          (pipeline.py:317) → original_audio.wav 16k (ASR)
  │                                          + original_audio_hq.wav 44.1k (mix)
  │ Step 2.5 _resolve_background        (pipeline.py:1459)
  │     ├─ bg_mode="demucs" → no_vocals.wav (bỏ giọng TQ, gain 0dB)
  │     ├─ bg_mode="duck"   → GIỮ NGUYÊN hq audio, gain tĩnh = bg_duck_db (−5dB)
  │     └─ bg_mode="none"   → im lặng
  │ Step 3  transcribe → transcript_original.json (start/end theo VAD + gap-rescan)
  │          refine_speech_boundaries   (speech/boundaries.py) → speech_start/end/duration
  │ Step 5  TTS → data/segments/seg_XXXXX.wav (CapCut/VieNeu)
  │          postprocess_voice_clip     (media/audio.py) — loudnorm + TRIM LẶNG ĐẦU (e2da471)
  │ Step 6  apply_soft_timing           (media/timing.py:194)
  │          └─ plan_voice_placements   (media/timing.py:82)
  │               _natural() = speech_start  → dub_start ≈ speech_start (drift cap 0.15s)
  │          merge_segments             (media/audio.py:485)
  │          └─ numpy block-mixer 60s: nền (đã gain tĩnh) × _duck_envelope + clip TTS
  │ Step 7  merge_video                 (media/video.py:191) — mux video + audio đã mix
```

## 10 câu hỏi — câu trả lời kèm bằng chứng

1. **Audio gốc extract ở đâu?** `extract_audio_dual` (media/audio.py:147) —
   một lệnh ffmpeg ra 2 bản: 16 kHz mono cho ASR + 44.1 kHz stereo cho mix.
2. **Audio gốc bị replace ở đâu?** KHÔNG bị replace ở đâu cả. `bg_mode`
   quyết định nó đi đâu: `duck` = giữ nguyên làm nền (chỉ gain tĩnh
   `bg_duck_db`), `demucs` = thay bằng bản tách giọng `no_vocals.wav`,
   `none` = bỏ. Đường đang dùng của user là **duck**.
3. **ASR tạo `start/end` ở đâu?** Paraformer worker (2-pass VAD + pass-3
   gap-rescan, asr_paraformer_worker.py) hoặc Whisper; refine RMS thu hẹp
   thành `speech_start/speech_end` (speech/boundaries.py:72).
4. **TTS tạo ở đâu?** `_synthesize_segments` (pipeline.py Step 5) →
   `data/segments/seg_<id>.wav`, hậu kỳ từng clip trong
   `postprocess_voice_clip` (media/audio.py:240).
5. **TTS đặt lên timeline ở đâu?** `plan_voice_placements._natural()`
   (media/timing.py:104) lấy `speech_start` làm onset; mutate `seg["start"]`;
   `merge_segments` (media/audio.py:555) rải clip theo `seg["start"]` tuyệt
   đối — không cộng dồn.
6. **Original audio giữ hay bỏ?** Ở chế độ duck: GIỮ — đây vốn là mix 2
   track. Demucs: giọng TQ bị bỏ. None: bỏ.
7. **Final audio tạo ở function nào?** `merge_segments` (media/audio.py:485)
   — streaming block 60 s, nền chuẩn hoá bằng ffmpeg (gain/apad/atrim) rồi
   overlay từng clip TTS + envelope duck + `_soft_limit` (tanh mềm, không
   clip cứng).
8. **Filter nào đang dùng?** KHÔNG dùng `amix`/`adelay`/`sidechaincompress`.
   Mixer là numpy thủ công; ducking là `_duck_envelope` (media/audio.py:388)
   — cosine smoothstep, attack 80 ms / release 220 ms **hardcode**
   (`_DUCK_ATTACK_S`/`_DUCK_RELEASE_S`), gain `10^(duck_db/20)` trong khoảng
   có giọng.
9. **VIDEO_SPEED ảnh hưởng audio?** CÓ — nền bị atempo ×speed
   (`slow_background`), timeline TTS + speech_* bị rescale ×1/speed
   (media/retime.py:125, fix 28f73c8). Hiện user để 1.00.
10. **VOICE_SPEED áp ở đâu?** Chỉ chế độ legacy (`voice_speed_legacy=true`)
    — atempo gộp trong `postprocess_voice_clip`. Mặc định tắt.

## Phase 2 — Root cause A/B/C/D

### A. Original Chinese audio có còn trong final video không?

**CÓ** khi `bg_mode="duck"` (đường user đang chạy): final = original
(gain tĩnh −5 dB, dip thêm khi có giọng VI) + TTS tiếng Việt. Kiến trúc
mix 2 track **không broken**. (Demucs/none thì không — đúng theo thiết kế
của từng chế độ.)

### B. TTS có start cùng `speech_start` không?

**CÓ.** Scheduler ghim `dub_start = speech_start` (drift cap 0.15 s, chỉ
trượt khi clip trước còn đang nói). Từ commit e2da471, lặng đầu clip TTS
bị trim (guard 120 ms) nên giọng VI bật **≈120 ms** sau onset TQ — đo thực
tế trên bản 12:39. Gap còn lại: chưa có `PRE_ROLL_MS` (mặc định 0 là đúng
theo spec; chỉ cần thêm tuỳ chọn).

### C. Chinese có duck theo speech segment không?

**CHƯA ĐÚNG — đây là gap chính.** `_duck_envelope` đang duck theo
**interval giọng VI** (`duck_intervals` xây từ `seg_index` = placement
dub, media/audio.py:567) chứ không phải theo **speech segment tiếng TQ**
(`speech_start→speech_end`). Hệ quả:
- VI đọc xong sớm (TTS ngắn hơn) → nền TQ trồi về mức đầy **ngay khi
  nhân vật còn đang nói** (vi phạm Test 2/3 của spec).
- Depth nông: dip động chỉ `bg_duck_voice_db` (user −4 dB) trên nền tĩnh
  −5 dB → tổng ≈ −9 dB khi có giọng, trong khi spec muốn −14…−20 dB.
- Attack 80/release 220 ms hardcode, không cấu hình được.

### D. Hai audio track có thực sự được mix không?

**CÓ.** `merge_segments` cộng mẫu thật: block nền (đã áp envelope +
static gain) `+=` mẫu TTS, rồi `_soft_limit` + clamp int16. Không có
replace, không có track riêng trong file cuối (1 stream AAC = mix).

## Kết luận gap (dẫn sang AUDIO_DUB_DESIGN.md)

| # | Gap | Mức |
|---|---|---|
| 1 | Envelope duck theo **dub interval** thay **speech segment TQ** | sửa nguồn interval |
| 2 | Mức duck khi nói quá nông (−9 vs −14…−20 dB), không có setting riêng | setting `ORIGINAL_VOICE_DUCK_DB` |
| 3 | Attack/release hardcode | settings `DUCK_ATTACK_MS`, `DUCK_RELEASE_MS` |
| 4 | Không có pre-roll tuỳ chọn | setting `DUB_PRE_ROLL_MS` (mặc định 0) |
| 5 | Chưa có test 5 scenario của spec + render test + benchmark | test + docs |

Phần CŨN LẠI đã đạt yêu cầu spec: placement = speech_start (B), mix 2
track thật (D), không ép TTS về duration gốc, không slow video, không
cumulative drift.
