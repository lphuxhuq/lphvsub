---
description: Thực hiện đúng một unit, test, review và dừng.
---

# /implement-next

## Kiểm tra trước khi chạy

Phải có:

- Analysis đã duyệt
- Design đã duyệt
- Task Breakdown đã duyệt
- task hiện tại đã được cho phép
- dependency đã hoàn thành
- unit trước đó nếu có phải PASS

Nếu thiếu → DỪNG.

## Thực hiện

1. Xác định TASK-XXX tiếp theo.
2. Hiển thị:
   - mục tiêu
   - dependency
   - file được sửa
   - file không được sửa
   - acceptance criteria
3. Chạy `unit-implementation`.
4. Code đúng một unit.
5. Chạy test.
6. Chạy `code-review`.
7. Nếu FAIL:
   - sửa CHỈ unit hiện tại
   - test lại
   - review lại
8. Nếu PASS:
   - cập nhật progress
   - DỪNG
   - chờ người dùng cho phép unit tiếp theo.

TUYỆT ĐỐI không tự động chạy unit kế tiếp.
