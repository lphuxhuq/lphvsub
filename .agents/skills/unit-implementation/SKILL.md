---
name: unit-implementation
description: Code đúng một unit đã được duyệt, chạy test, không mở rộng phạm vi và chuẩn bị cho code review.
---

# SKILL: IMPLEMENT MỘT UNIT

## Điều kiện

TASK phải:

- tồn tại trong Task Breakdown
- đã được duyệt
- dependency đã hoàn thành
- có scope rõ ràng

## Quy tắc số 1

**MỖI LẦN CHỈ ĐƯỢC CODE MỘT TASK-XXX.**

Không được tự động code task tiếp theo.

## Trước khi code

1. Đọc lại task.
2. Đọc requirement liên quan.
3. Đọc design liên quan.
4. Đọc code thực tế.
5. Xác định chính xác vị trí cần sửa.
6. Kiểm tra convention hiện tại.

## Khi code

- chỉ sửa file được phép
- giữ behavior cũ
- dùng pattern hiện tại
- thay đổi tối thiểu
- viết test cần thiết
- không refactor ngoài phạm vi

## Nếu phát hiện cần sửa file ngoài phạm vi

DỪNG.

Báo:

`YÊU CẦU MỞ RỘNG PHẠM VI`

Gồm:

- file cần sửa
- lý do
- ảnh hưởng
- phương án

Chờ người dùng duyệt.

## Sau khi code

Chạy những kiểm tra phù hợp:

- formatter
- linter
- type check
- build
- unit test
- integration test

Không được nói "đã pass" nếu chưa thực sự chạy.

## Progress

Cập nhật:

`.artifacts/progress.md`

Ghi:

- task hoàn thành
- file thay đổi
- test đã chạy
- kết quả
- warning
- deviation
- phần còn lại

Sau đó chạy code review.

## Nếu có lỗi

Không che giấu.

Nếu lỗi không giải thích được hoặc ảnh hưởng kiến trúc → DỪNG.
