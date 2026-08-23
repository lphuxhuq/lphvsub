# Fix Design — av-desync-videospeed

## Root Cause Đã Duyệt

`rescale_segments()` (`autodub/media/retime.py:125`) chỉ rescale
`start/end/duration`; scheduler voice-sync đặt onset theo `speech_start`
(field timeline gốc, không được rescale) → khi `VIDEO_SPEED < 1.0`, giọng
đọc đặt trên timeline gốc trong khi hình bị kéo dài ×1/speed → lệch tích lũy
(1/speed − 1) mỗi giây.

Xem chi tiết: `.artifacts/bug-fixes/av-desync-videospeed-root-cause.md`.

## Cách Sửa

Sửa MỘT hàm — `rescale_segments()` trong `autodub/media/retime.py`: rescale
thêm các field timeline voice-sync KHI CHÚNG TỒN TẠI (presence check bằng
`in`, không check truthiness vì `0.0` là giá trị hợp lệ):

- `speech_start`, `speech_end`, `vad_start`, `vad_end` → nhân `scale`
- `speech_duration` → nhân `scale` (toán học tương đương
  `(speech_end − speech_start) × scale`, khác biệt làm tròn ≤1ms — không
  consumer nào so строг bằng nhau)

Sau đó `plan_voice_placements._natural()`/`_resolve_slot()`
(`autodub/media/timing.py`) tự đọc đúng timeline làm chậm — placement giọng
về đúng vị trí hình, giữ nguyên độ chính xác refine (onset chuẩn 100-400ms).
Không đụng `timing.py`, `pipeline.py`, `video.py`, `boundaries.py`.

## Files Được Phép Sửa

1. `autodub/media/retime.py` — hàm `rescale_segments()` + docstring
2. `tests/test_timing_alignment.py` — thêm 2 regression test

## Files Không Được Sửa

Mọi file khác, đặc biệt: `timing.py`, `pipeline.py`, `video.py`,
`boundaries.py`, `editor.py`, `audio.py`, `config.py`, `.env`.

## Logic Trước

```python
def rescale_segments(segments: list[dict], scale: float) -> None:
    for seg in segments:
        seg["start"] = round(float(seg["start"]) * scale, 3)
        seg["end"] = round(float(seg["end"]) * scale, 3)
        seg["duration"] = round(seg["end"] - seg["start"], 3)
```

## Logic Sau

```python
def rescale_segments(segments: list[dict], scale: float) -> None:
    """Stretch every timestamp by ``scale`` (>1 = longer timeline), in place.

    Bao gồm cả field ``speech_*``/``vad_*`` của voice-sync khi có — scheduler
    timing đặt onset theo ``speech_start`` nên field nào sót sẽ giữ timeline
    cũ và kéo giọng lệch khỏi hình khi VIDEO_SPEED < 1.0.

    Callers must re-run :func:`autodub.text.translate_hint.annotate_slots`
    afterwards so slots reflect the stretched gaps.
    """
    for seg in segments:
        seg["start"] = round(float(seg["start"]) * scale, 3)
        seg["end"] = round(float(seg["end"]) * scale, 3)
        seg["duration"] = round(seg["end"] - seg["start"], 3)
        for a, b in (("speech_start", "speech_end"),
                     ("vad_start", "vad_end")):
            if a in seg and b in seg:
                seg[a] = round(float(seg[a]) * scale, 3)
                seg[b] = round(float(seg[b]) * scale, 3)
        if "speech_duration" in seg:
            seg["speech_duration"] = round(
                float(seg["speech_duration"]) * scale, 3)
```

(Comment guard trong code: các field `dub_*` không tồn tại ở thời điểm
rescale — rescale luôn chạy TRƯỜC `apply_soft_timing`; caller tương lai nào
rescale sau soft-timing phải tự xử lý `dub_*`.)

## Coverage các caller

| Caller | Đường | Sau fix |
|---|---|---|
| `retime.py:223` `apply_video_speed` | VIDEO_SPEED rời (không burn/blur) | đúng |
| `retime.py:283` `defer_video_speed` | VIDEO_SPEED gộp (burn/blur) — đường bug | đúng |
| `editor.py:516/535` xuất lại từ Trình chỉnh sửa | transcript đĩa không có `speech_*` | không đổi (presence check) |

## Validation / Error Handling / Backward Compatibility

- Pure arithmetic trên float đã có; không cần error handling mới.
- `VIDEO_SPEED = 1.0` (mặc định): `rescale_segments` không được gọi — zero
  change cho đa số user.
- Transcript cũ không có field `speech_*` (resume đời trước, editor): hành
  vi cũ y nguyên.
- `timing.py` đọc field theo timeline mà field mang — sau fix mọi field cùng
  một timeline.

## Regression Tests (thêm vào tests/test_timing_alignment.py)

1. `test_rescale_segments_scales_speech_fields` — segment có đủ 5 field
   `speech_*`/`vad_*`, scale 1/0.92: mọi field được nhân scale, làm tròn 3
   chữ số; segment không có field → chỉ đổi `start/end/duration` (behavior
   cũ).
2. `test_voice_placements_follow_rescaled_speech_timeline` — **regression
   của chính bug này**: segment mô phỏng lượt chạy thật
   (`speech_start=0.156`, `speech_duration=4.240`, TTS clip 3.218s), gọi
   `rescale_segments(segs, 1/0.92)` rồi `plan_voice_placements` → placement
   `start == 0.156 × scale ≈ 0.170` (trước fix: 0.156 — giọng về timeline
   gốc, lệch hình).

## Existing Tests

Chạy toàn suite (728 test đang pass theo commit 519480a), trọng điểm:
`tests/test_retime.py`, `tests/test_timing_alignment.py`, các test
voice-sync của commit 519480a.

## Risks

- Chênh lệch làm tròn ≤1ms giữa `speech_duration` nhân trực tiếp và
  `speech_end − speech_start` — không consumer so bằng nhau (slot floor
  0.3s, so sánh residual 0.15s) → không đáng kể.
- Caller nào trong tương lai rescale SAU soft timing sẽ để lại `dub_*`
  stale — đã ghi guard comment; ngoài scope.

## Rollback

Revert 1 hàm + 2 test. Không migration dữ liệu, không đổi format file.

## Change Budget

~12 dòng logic + docstring ở `retime.py`; ~45 dòng test.

## Approval Gate

TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA
