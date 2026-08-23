# Bug Fix Final Report — av-desync-videospeed

## Bug

Video xuất ra bị lệch giọng đọc so với hình: chỉ khớp vài giây đầu, lệch tăng
dần (8.7%/giây với VIDEO_SPEED=0.92). Lượt lỗi: `output/VN/20260822160103_vi`.

## Root Cause

`rescale_segments()` (`autodub/media/retime.py`) chỉ rescale
`start/end/duration` khi làm chậm video, bỏ sót field `speech_start` /
`speech_end` / `speech_duration` / `vad_start` / `vad_end` do
`refine_speech_boundaries` sinh ra (timeline gốc). Scheduler voice-sync
(commit `519480a`) đặt onset theo `speech_start` → mọi clip giọng quay về
timeline gốc trong khi hình bị kéo dài ×1/speed → lệch tích lũy.

Chi tiết: `.artifacts/bug-fixes/av-desync-videospeed-root-cause.md`

## Fix

`rescale_segments()` rescale thêm 5 field voice-sync khi chúng tồn tại
(presence check — transcript cũ không có field thì behavior y nguyên).
Scheduler timing (`timing.py`) tự đọc đúng timeline làm chậm, không phải sửa.
Cả 3 caller đều được phủ: `apply_video_speed`, `defer_video_speed` (đường
bị bug), và editor (không đổi).

## Files Changed

- `autodub/media/retime.py` — `rescale_segments()`: +14 dòng (logic + guard
  docstring về `dub_*` cho caller tương lai).
- `tests/test_timing_alignment.py` — +36 dòng, 2 regression test.

## Tests

- `test_rescale_segments_scales_speech_fields` — mọi field được rescale;
  segment không có field giữ behavior cũ.
- `test_voice_placements_follow_rescaled_speech_timeline` — tái hiện đúng
  bug với số liệu lượt chạy thật (speech_start=0.156, TTS 3.218s, scale
  1/0.92): placement phải ≈0.170, không rơi về 0.156.

## Regression Tests

Toàn suite: **730 passed** (728 cũ + 2 mới), 0 fail. Trọng điểm xanh:
`test_retime.py` (10 test), `test_timing_alignment.py` (7 test), các test
voice-sync của `519480a`.

## Review

- Root cause giải quyết triệt để? CÓ — placement giờ cùng timeline với hình
  (end-to-end verify bằng số liệu lượt lỗi: câu 1 tại 0.170 thay vì 0.156;
  câu 59 tại ~406.9 thay vì 374.4).
- Đúng design? CÓ — diff khớp 100% design đã duyệt, chỉ 2 file trong scope.
- Sửa triệu chứng? KHÔNG — sửa tại nguồn duy nhất phát sinh timeline.
- Regression? KHÔNG — 730/730 pass; đường VIDEO_SPEED=1.0 và editor không
  đổi hành vi (presence check + test).
- Security/Performance? Không vấn đề (số học thuần, +5 dict check/segment).
- Severity còn lại: INFO — guard `dub_*` chỉ là docstring cho caller tương
  lai, không có việc phải làm ngay.

Verdict: **PASS**

## Remaining Risks

- Caller tương lai nào gọi `rescale_segments` SAU `apply_soft_timing` sẽ để
  lại field `dub_*` stale — đã ghi guard trong docstring.
- Video đã xuất hỏng (`20260822160103_vi`) không tự sửa — cần chạy lại
  project (auto-clean đã xoá TTS cache nên TTS chạy lại; bản dịch/transcript
  còn, không tốn thêm).
- Sau khi chạy lại, nên nghe spot-check 1-2 câu ở giữa/cuối video (ví dụ câu
  59 quanh ~407s) để xác nhận bằng tai.

## Final Status

PASS
