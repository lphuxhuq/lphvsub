---
description: Quy trình debug và sửa bug có Root Cause Analysis, approval gate, regression test và code review.
---

# /fix-bug

## BƯỚC 1 — TIẾP NHẬN

Đọc bug report.

Xác định:

- lỗi gì
- expected
- actual
- bước tái hiện
- môi trường
- log/stack trace
- severity

## BƯỚC 2 — REPRODUCE

Cố gắng tái hiện bằng test/runtime/log/source.

Không được sửa code.

## BƯỚC 3 — ROOT CAUSE

Reverse engineer call flow và tìm nguyên nhân gốc.

Tạo:

`.artifacts/bug-fixes/<bug-id>-root-cause.md`

Sau đó:

`TRẠNG THÁI: CHỜ DUYỆT NGUYÊN NHÂN`

DỪNG.

Chờ:

`DUYỆT NGUYÊN NHÂN`

## BƯỚC 4 — FIX DESIGN

Sau khi được duyệt:

- thiết kế cách sửa
- xác định file
- xác định logic
- xác định test
- xác định regression risk

Tạo:

`.artifacts/bug-fixes/<bug-id>-fix-design.md`

Sau đó:

`TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`

DỪNG.

Chờ:

`DUYỆT CÁCH SỬA`

## BƯỚC 5 — IMPLEMENT

Chỉ sửa đúng phạm vi đã duyệt.

## BƯỚC 6 — TEST

Chạy:

- test tái hiện bug
- expected behavior
- edge case
- existing tests
- build/type check/lint nếu có

## BƯỚC 7 — REGRESSION

Kiểm tra behavior liên quan để đảm bảo fix không tạo bug mới.

## BƯỚC 8 — REVIEW

Review:

- root cause
- correctness
- regression
- security
- performance
- maintainability
- scope

Nếu FAIL:

→ sửa
→ test
→ regression test
→ review lại

Nếu PASS:

→ tạo final report
→ DỪNG

## QUY TẮC

Không tự chuyển sang bug khác.

Không tự refactor.

Không tự mở rộng scope.

Không được nói bug đã fix nếu chưa có evidence.
