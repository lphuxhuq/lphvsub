# Code Review — TASK-001: OutputProfile & Pixel Budget Engine

## Phạm vi review
- Files: `autodub/media/output_profile.py`, `tests/test_output_profile.py`.

## Requirement Compliance
- Đã chuẩn hóa 9:16 $\rightarrow$ 1080x1920 khi source 16:9.
- Đã chuẩn hóa 16:9 $\rightarrow$ 1920x1080, 1:1 $\rightarrow$ 1080x1080.
- Pixel budget strictly enforced $\le$ max_pixels (mặc định 2,073,600).
- Resolution chẵn (even) tương thích chuẩn mã hóa YUV420p.

## Findings
- Không có lỗi CRITICAL, HIGH hoặc MEDIUM.

## Test Review
- 5/5 unit tests passed.

## Kết luận
`PASS`
