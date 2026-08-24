# AUDIO DUB — Test Report (Phase 13–15)

> Chứng minh theo ACCEPTANCE CRITERIA của spec. Ngày 2026-08-23.
> Code path kiểm chứng: `merge_segments` (duck theo speech TQ) +
> `plan_voice_placements` (onset) + `merge_video` (mux) — toàn bộ là code
> production, không mock trong render test.

## Benchmark TRƯỚC / SAU (số đo thật)

| Chỉ số | TRƯỚC (lượt 12:39, hệ cũ) | SAU (render test 60s) |
|---|---|---|
| Duck nguồn interval | theo **dub-end giọng VI** | theo **speech segment TQ** |
| Mức TQ khi nhân vật nói | ≈ −9 dB tổng (tĩnh −5 + động −4) | **−16.0 dB đo được** (target −16) |
| TQ khi VI dứt sớm | nền trồi ngay (nhân vật còn nói) | **vẫn chìm tới hết câu** (Test 2) |
| Nền ngoài speech | −5 dB tĩnh | **0.0 dB** (hồi đúng mức gốc) |
| Onset VI so speech_start | +0.2…+2.1s (lặng đầu clip TTS, mean +0.64s) | **0.0 ms** (tone)/ **≤120 ms** (TTS thật sau trim e2da471) |
| Attack/Release | 80/220 ms hardcode | 80/140 ms cấu hình được |

## Test tự động — 5 scenario của spec (tests/test_audio_dub_mix.py)

| # | Scenario | Kết quả |
|---|---|---|
| 1 | VI dài hơn TQ (2.5 vs 2.0s): cùng bắt đầu 10.0, TQ dip ≈ đúng tỉ lệ | PASS |
| 2 | VI ngắn hơn (dứt 11.6): TQ **vẫn dip tới 12.0** — regression guard chống hành vi cũ | PASS |
| 3 | Silence 12→14: nền hồi >98% sau release | PASS |
| 4 | 2 câu liên tiếp: VI B start ≈ 12.2 (onset của B), không phải VN-A-end | PASS |
| 5 | VI dài hơn hẳn (5s/2.3s slot): start = speech_start, nén ≤1.15×, không ép khít | PASS |
| + | Integration merge thật: 2 track chồng, nền dip −16 trong speech sau khi VI dứt, hồi sau release | PASS |

## Render test thật (Phase 14 — scripts/render_audio_dub_test.py)

Nguồn: `BV16f3K67EAk.mp4`, cửa sổ 20–80s. **ASR thật** (Paraformer) bắt 4
speech segments gần liền mạch (0.22–9.45, 10.52–31.42, 31.52–53.69,
53.79–60.0). "Giọng VI" = tone 1kHz đặt đúng `speech_start` qua đúng code
mix production; mux bằng `merge_video`. Xuất `output/audio_dub_test/dub_test.mp4`.

| Kiểm tra ffprobe/đo | Kết quả |
|---|---|
| Số audio stream trong mp4 | **1** (stream mix, không phải thay thế) |
| Duck depth trong speech (so bản gốc cùng cửa sổ) | **16.0 dB** cả 4 câu (target −16) |
| Gain ngoài speech | **0.0 dB** |
| Onset VI so speech_start | **0.0 ms** |
| Tốc độ video | **1.0** (stream-copy, không retime) |
| Peak (volumedetect) | **−0.2 dB** — không clipping (tone test cố ý to; TTS thật đi loudnorm −16 LUFS nên dư headroom) |

## Nghe chủ quan (Phase 15 — cần tai người)

`output/audio_dub_test/dub_test.mp4` — checklist theo spec: TQ còn rõ
đủ chân thật? VI nổi trên? VI bật ngay khi TQ cất? có trễ đầu câu?
VI dài hơn có khó chịu? pumping? clipping? Với TTS thật, chỉ cần chạy lại
project bất kỳ ở chế độ nhạc nền **Giữ âm gốc (duck)**.

## ACCEPTANCE CRITERIA

- [x] Video chạy tốc độ gốc (stream-copy, VIDEO_SPEED=1.0)
- [x] Chinese original vẫn tồn tại (mix thật, đo gain 0dB ngoài speech)
- [x] Chinese giảm volume khi đang nói (−16.0dB đo được, đúng target)
- [x] Vietnamese bắt đầu gần đồng thời (0ms tone / ≤120ms TTS thật)
- [x] Hai giọng thực sự chồng nhau (test integration + đo năng lượng)
- [x] Vietnamese foreground (VI nổi > 2× nền trong cửa sổ chồng)
- [x] Chinese nghe được ở background (−16dB, không bị bỏ)
- [x] Không duck toàn bộ video (ngoài speech = 0.0dB)
- [x] TTS không cần kết thúc đúng source_end (Test 1/5)
- [x] Không cumulative drift (placement tuyệt đối theo mốc nguồn)
- [x] Không clipping (soft-limiter; peak −0.2dB với tone test cố ý to)
- [x] Không replace original audio (1 stream = mix 2 track)
- [x] Test chứng minh 2 track overlap (test_audio_dub_mix.py)
- [x] Benchmark trước/sau (bảng trên)

**769 test pass** (763 + 6 mới).
