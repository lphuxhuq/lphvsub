# Root Cause Analysis — av-desync-videospeed

## Bug

Khi xuất video, giọng đọc (voice) và hình (video) không đồng bộ: chỉ khớp
vài giây đầu, sau đó lệch ngày càng lớn.

- **Expected**: giọng đọc câu N vang lên đúng lúc hình chiếu cảnh người nói
  câu N, suốt cả video.
- **Actual**: giọng đọc (và phụ đề ghi vào hình) chạy trước hình, lệch tăng
  dần theo thời gian.
- **Run bị lỗi**: `output/VN/20260822160103_vi` (16:01:03 ngày 22/08/2026 —
  lượt chạy đầu tiên SAU commit voice-sync `519480a` 15:55).
- **Frequency**: ALWAYS — mọi lượt chạy có `VIDEO_SPEED < 1.0` (file `.env`
  của người dùng: `VIDEO_SPEED=0.92`) sau commit `519480a`.
- **Severity**: CRITICAL — sản phẩm cuối (video lồng tiếng) hỏng toàn bộ
  phần giữa/cuối.

## Reproduction

`PARTIALLY REPRODUCED` — tái hiện bằng chứng cứ pháp y từ chính lượt chạy
bị lỗi (log + SRT + ffprobe + .env + code trace); không cần chạy lại
pipeline (tốn ~3 phút +CapCut/AI Studio). Chuỗi bằng chứng khép kín:

1. `logs/voxdub.log` dòng 334: `STEP 5.5: Slowing video (0.92x)` — đường
   `defer_video_speed` chạy (burn subs + blur → gộp setpts vào lượt mã hóa
   cuối). Video gốc 383 giây bị làm chậm thành ~416 giây.
2. `logs/voxdub.log` dòng 347-405 `[VOICE-SYNC]`: scheduler đặt mọi câu theo
   mốc **timeline gốc** — segment 1 `final: 0.156→3.374`, segment 59
   `final: 374.364→379.838`. Nếu timeline đã được rescale ×1.087 thì segment
   59 phải bắt đầu ở ~406.9s.
3. `output/VN/20260822160103_vi/transcript_vi.srt` (còn sót lại trước khi
   auto-clean): cue cuối kết thúc `00:06:19,838` = 379.838s — trùng khít
   placement timeline gốc ở (2).
4. `logs/voxdub.log` dòng 411: `Audio merged ... 415.5s` = 381.324 ×
   (1/0.92) + 1 — canvas audio tính từ `end` **đã rescale** (đúng timeline
   làm chậm), trong khi voice clip lại đặt ở vị trí timeline gốc (2).
5. `ffprobe dubbed_video.mp4`: video stream `415.933s` (hình ĐÃ làm chậm
   0.92x ✓), audio stream `415.483s`.
6. `.env` dòng 75: `VIDEO_SPEED=0.92`; `SOFT_TIMING_FIT=true`;
   `speech_boundary_refine` mặc định `true` (config.py:205).

Độ lệch thực tế: voice đặt ở t, hình tại t chiếu nội dung gốc của t×0.92 →
voice sớm hơn hình t×0.087 giây, cộng dồn: ~0.9s ở giây 10, ~5.2s ở giây 60,
~30s ở câu cuối (374s). Khớp triệu chứng "chỉ được vài giây đầu sau đó lệch".

## Symptom

Giọng đọc + phụ đề chạy trước hình, lệch tăng tuyến tính (1/speed − 1 mỗi
giây). Quality report vẫn báo "57/59 câu chuẩn" vì nó so dub với biên speech
trên CÙNG timeline gốc — tự nhất quán, không soi được lệch phía hình.

## Root Cause

`rescale_segments()` (`autodub/media/retime.py:125`) khi làm chậm video
chỉ rescale `start` / `end` / `duration`. Nhưng scheduler voice-sync mới
(commit `519480a`) đặt onset giọng đọc theo field `speech_start` (và slot
theo `speech_duration`) do `refine_speech_boundaries` sinh ra ở Step 3 —
những field này nằm trên timeline GỐC và **không bao giờ được rescale**.

Cụ thể `plan_voice_placements._natural()` (`autodub/media/timing.py:104`):
`seg.get("speech_start", seg.get("start", 0.0))` — ưu tiên `speech_start`
(timeline gốc) nên ghi đè placements (và mutate lại `start`/`end` ở
timing.py:258-270) về timeline gốc, vô hiệu hóa rescale vừa làm ở Step 5.5.
Hình xuất ra vẫn bị kéo dài ×1/0.92 → hai dòng thời gian lệch nhau một tỷ lệ
không đổi = lệch tích lũy.

## Call Flow

```
Step 3   refine_speech_boundaries (boundaries.py)
         → gắn speech_start/speech_end/speech_duration + vad_* (timeline GỐC)
Step 5.5 defer_video_speed (retime.py:233)   [VIDEO_SPEED=0.92, burn/blur]
         → rescale_segments (retime.py:125): CHỈ start/end/duration ×1.087
         → speech_*/vad_* giữ nguyên timeline gốc  ← LỖI
Step 6   apply_soft_timing → plan_voice_placements (timing.py)
         → _natural() đọc speech_start (GỐC) → đặt mọi clip về timeline gốc,
           mutate start/end đè lên giá trị đã rescale
         merge_segments (audio.py:485) đặt clip theo start (timeline gốc)
         trên canvas 415.5s (tính từ end đã rescale ở pipeline.py:613)
Step 7   merge_video (video.py:191) với speed=0.92
         → setpts=PTS/0.92: hình kéo dài 415.9s, audio giữ nguyên
→ voice/subs chạy trước hình, lệch t×0.087s
```

Đường rời `apply_video_speed` (retime.py:151, dùng khi không burn/blur) dính
cùng lỗi vì cũng gọi `rescale_segments`.

## Evidence

- Log lượt lỗi: `logs/voxdub.log` dòng 181-439 (đặc biệt 334, 336, 347, 405,
  408, 411, 419).
- File còn sót: `output/VN/20260822160103_vi/transcript_vi.srt` (cue cuối
  379.838s), `dubbed_video.mp4` (ffprobe: video 415.933s / audio 415.483s).
- `.env:75` `VIDEO_SPEED=0.92`.
- Code: `retime.py:125-134` (rescale thiếu field), `timing.py:104`
  (`_natural` ưu tiên speech_start), `boundaries.py:115-119` (sinh field),
  `pipeline.py:442-445` (refine chạy mặc định), `video.py:245-256` (setpts).

## Affected Files

- `autodub/media/retime.py` — `rescale_segments()` thiếu rescale
  `speech_start/speech_end/speech_duration/vad_start/vad_end` (nguồn lỗi).
- `autodub/media/timing.py` — consumer đọc field chưa rescale (nơi lộ lỗi).
- Không sửa ở Phase này.

## Contributing Factors

- `speech_boundary_refine` mặc định bật + người dùng để `VIDEO_SPEED=0.92`
  → luôn tái hiện.
- `total_duration` tính ở `pipeline.py:613` TRƯỚC `apply_soft_timing` — hai
  nguồn sự thật (end đã rescale vs placement chưa) cùng sống trên một canvas,
  che lỗi khi nhìn log tổng quan.
- Quality report so dub–speech cùng timeline gốc nên không phát hiện được.
- Hai feature (VIDEO_SPEED cũ, voice-sync mới ở `519480a`) giao nhau đúng
  chỗ không có test chung.

## Why Existing Tests Did Not Catch It

- 38 test mới của voice-sync test `plan_voice_placements` với segment KHÔNG
  qua `rescale_segments` (không có tình huống VIDEO_SPEED).
- Test VIDEO_SPEED cũ test `rescale_segments` với segment KHÔNG có field
  `speech_*` (transcript đời trước) → `_natural` rơi về `start` đã rescale,
  vẫn đúng.
- Không có test tích hợp "refine + rescale + soft timing" — đúng tổ hợp bị
  lỗi.

## Impact

- Mọi lượt chạy có `VIDEO_SPEED < 1.0` từ commit `519480a` (22/08/2026)
  trở đi: video xuất ra lệch tiếng-tăng-dần, hỏng hoàn toàn sau ~1 phút.
- Cả hai đường: defer (burn/blur) và rời (apply_video_speed).
- Trình chỉnh sửa (editor.py) tái xuất từ `transcript_vi.json` đã lưu cũng
  dùng placement timeline gốc — project cũ phải chạy lại sau khi fix.

## Regression Risk

- Sửa `rescale_segments` phải giữ an toàn cho transcript cũ KHÔNG có field
  `speech_*` (resume từ project đời trước) và cho `dub_*` (nếu rescale chạy
  sau soft timing — hiện không, nhưng field phải được xử lý đúng).
- Không được phá đường VIDEO_SPEED = 1.0 (không rescale, chiếm đa số user).

## Proposed Fix (sketch — chi tiết ở Fix Design)

Trong `rescale_segments()` (`retime.py`), rescale thêm các field timeline
khác khi chúng tồn tại: `speech_start`, `speech_end`, `speech_duration`,
`vad_start`, `vad_end` (duration ×scale; start/end ×scale). Sau đó
`_natural()`/`_resolve_slot()` tự đọc đúng timeline làm chậm — placement
tự động về đúng. Kèm regression test: segment có `speech_start` +
VIDEO_SPEED<1 → placement = speech_start × scale; và segment không có
field → behavior cũ.

## Alternatives Considered

1. Re-run `refine_speech_boundaries` SAU rescale — sai: file ASR wav vẫn
   timeline gốc, refine trên biên đã rescale sẽ đọc nhầm cửa sổ RMS.
2. Đánh dấu `timeline_rescaled` lên segment và đổi `_natural()` bỏ qua
  `speech_start` — giữ placement theo `start` (đã rescale): mất độ chính
   xác refine (onset lệch 100-400ms mỗi câu) — chất lượng voice-sync suy
   giảm ở mọi lượt VIDEO_SPEED<1.
3. Bỏ hẳn VIDEO_SPEED — thay đổi phạm vi sản phẩm, không phải fix bug.

## Scope

- Root cause này CHỈ xử lý lệch timeline do thiếu rescale field. Không đụng:
  lỗi drift 1.5s cũ (đã fix ở 519480a), fps/VFR, atempo, karaoke alignment.

## Unknowns

- Không còn unknown chặn việc fix. (Đã loại trừ: VFR/fps — ffprobe cho thấy
  video stream 415.93s đúng bằng 383×1.087; atempo/merge — canvas audio
  đúng 415.5s.)

## Approval Gate

TRẠNG THÁI: CHỜ DUYỆT NGUYÊN NHÂN
