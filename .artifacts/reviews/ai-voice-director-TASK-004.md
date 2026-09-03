# Code Review — TASK-004 (Voice Director Scoring Engine)

## Phạm vi review
- **Production file:** [`autodub/speech/voice_director.py`](file:///d:/Project/lphvsub-main/autodub/speech/voice_director.py)
- **Test file:** [`tests/test_voice_director.py`](file:///d:/Project/lphvsub-main/tests/test_voice_director.py)

## Requirement & Design Compliance
- [x] Động cơ chấm điểm Compatibility Scoring đa tiêu chí: `W_GENDER=0.40`, `W_PITCH=0.20`, `W_NARRATOR=0.25`, `W_PROVIDER=0.15`.
- [x] Cơ chế **Uniqueness Penalty** (`UNIQUENESS_PENALTY=0.80`): Đảm bảo các speaker khác nhau nhận các giọng khác nhau, tránh trùng lặp.
- [x] Tôn trọng **Manual Overrides**: Không ghi đè các speaker đã được người dùng chỉ định thủ công.
- [x] Xử lý **Toggle On/Off**: Khi tắt, toàn bộ speaker dùng chung 1 giọng mặc định của dự án (`source="fallback"`).

## Findings
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO:** Sắp xếp phân vai theo thứ tự thời lượng nói giảm dần để nhân vật chính/dẫn chuyện luôn được chọn giọng tối ưu nhất trước.

## Test Review
- 3/3 tests passed trong 0.07s. Kiểm tra đầy đủ phân vai đa giọng, manual override và toggle off.

## Kết luận
`PASS`
