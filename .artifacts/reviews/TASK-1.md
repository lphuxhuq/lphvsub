# Code Review — TASK-1 (asr-accuracy-boost)

## Phạm vi review

- `autodub/speech/asr_paraformer_worker.py` — padded_range + --vad-pad + empty signaling + restructure 2-pass
- `autodub/speech/paraformer_transcriber.py` — meta kwarg, parse `empty`, `--vad-pad` trong cmd, warning tổng
- `autodub/speech/transcriber.py` — `transcribe(meta=...)` truyền xuyên nhánh Paraformer
- `autodub/config.py` — `asr_vad_pad_s` + env `ASR_VAD_PAD_S` (clamp 0-1s)
- `tests/test_asr_worker_pad.py` (10 test), `tests/test_paraformer_protocol.py` (7 test)

## Requirement Compliance

| AC TASK-1 | Bằng chứng | Kết quả |
|---|---|---|
| `padded_range` bất biến `0≤s<e≤n`, `s≥prev_end`, mở rộng ≤ pad | `test_invariants_always_hold` (4 case biên) + `test_no_chunk_speech_decoded_twice` | ĐẠT |
| Timestamp `seg` không đổi khi có/không padding | Worker emit `round(orig_start/rate,3)`/`orig_end` — biên VAD gốc, không phụ thuộc decode range (asr_paraformer_worker.py pass 2) | ĐẠT |
| Empty chunk vào `meta["empty_chunks"]`; worker cũ không key → `[]`, không crash | `test_protocol_with_empty_chunks`, `test_old_protocol_without_empty_key` | ĐẠT |
| 630 test cũ PASS | Full suite 649 passed (630 cũ + 19 mới) | ĐẠT |

## Design Compliance

- C2: pad mặc định 0.3, clamp, timestamp VAD gốc — đúng. Protocol thêm-key (`empty`, `num_empty`) không đụng key cũ — đúng.
- C3: `meta` optional, nhánh Whisper không ghi key — đúng (docstring transcriber.py ghi rõ).
- Settings C7: `asr_vad_pad_s` default 0.3 + env — đúng bảng design.

## Findings

### [HIGH → ĐÃ SỬA TRONG UNIT] Double-decode speech của chunk kề

- Vị trí: `asr_paraformer_worker.py` `padded_range` (bản đầu) + vòng decode 1-pass.
- Bằng chứng: bản đầu chỉ clamp trái theo `prev_end` (biên GỐC chunk trước), trong khi bản decode CỦA CHUNK TRƯỚC được mở rộng `+pad` không giới hạn. Tại force-split 20s (gap = 0, xảy ra đúng các câu dài), decode của chunk trước tràn vào 0.3s speech đầu của chunk sau → cùng一段 audio bị decode 2 lần → chữ đầu câu lặp. Với gap < pad (khi user nâng pad > 0.5s) lỗi tương tự.
- Ảnh hưởng: duplicate text — vi phạm chính ràng buộc "không duplicate" của spec (và comment cũ của hàm chỉ đúng một nửa).
- Đề xuất (đã áp dụng): (1) `padded_range` nhận thêm `next_start`, clamp phải `e ≤ next_start`; (2) worker tách 2-pass — pass 1 thu thập toàn bộ biên VAD chunk, pass 2 decode với biên 2 chunk kề. Bất biến mới: speech mỗi chunk nằm trọn trong decode range của chính nó và không chunk kề nào chạm vào — chứng minh bằng `test_no_chunk_speech_decoded_twice`.
- Cân nhắc phụ của cách sửa: decode bắt đầu sau khi VAD quét xong file (trước đó decode chen trong lúc quét) — log tiến trình từng câu vẫn stream; VAD nhanh nên chấp nhận.

## Test Review

- Test thật: fake Popen feed JSON-lines giả — bao protocol mới/cũ, meta=None, cmd chứa `--vad-pad`, 3 nhánh raise. Pure-function test bao biên file/Chunk kề/pad 0/chunk 1-sample + bấtynchronized bất biến double-decode. Không test "cho có".
- Gap chấp nhận: không test worker end-to-end với sherpa thật (cần .venv-asr + model — ngoài phạm vi unit test, thuộc TASK-7 integration).

## Regression Review

- Pad = 0 → decode range = đúng chunk gốc = hành vi cũ (test `test_zero_pad_returns_exact_range`).
- Driver không truyền `meta` → hành vi y hệt trước (kwarg optional).
- Protocol cũ (worker chưa cập nhật trong resume) parse bình thường.
- Full suite 649 passed, không fail.

## Security Review

- JSON protocol nội bộ, không input từ user vào shell (argv là path nội bộ); không secret. OK.

## Performance Review

- 2-pass VAD: thêm 1 list các tuple int (nhỏ); decode tổng lượng audio tăng ≤ pad×2×số chunk (0.6s mỗi chunk với default) — là chủ đích của feature. Không I/O thừa.

## Scope Review

- Deviation duy nhất: `config.py` thêm `asr_vad_pad_s` (4 dòng) — TASK-1 bắt buộc đọc setting này nhưng breakdown ghi nhầm sang TASK-6; đúng bảng settings C7 của design đã duyệt. Đã ghi rõ trong progress.md. Ngoài ra đúng scope.

## Kết luận

**PASS** — finding HIGH duy nhất đã được phát hiện và sửa ngay trong unit (kèm test bất biến), tất cả AC đạt, không regression, scope đúng (1 deviation được ghi nhận hợp lệ).
