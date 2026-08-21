---
name: code-review
description: Review implementation một cách độc lập và nghiêm khắc, đối chiếu requirement, design, code, test, security, performance và scope.
---

# SKILL: CODE REVIEW

## Mục tiêu

Tìm lỗi trước khi cho phép AI chuyển sang unit tiếp theo.

Review phải mang tính phản biện, không mặc định code đúng.

## 1. Review Requirement

Đối chiếu code với Acceptance Criteria.

## 2. Review Design

Đối chiếu implementation với Design đã duyệt.

## 3. Correctness

Kiểm tra:

- happy path
- edge case
- null/empty
- invalid input
- state transition
- concurrency nếu có
- error path

## 4. Regression

Kiểm tra behavior cũ bị ảnh hưởng không.

## 5. Security

Kiểm tra:

- authentication
- authorization
- validation
- injection
- secret
- sensitive data
- unsafe deserialization
- insecure default

## 6. Performance

Kiểm tra:

- I/O thừa
- N+1 query
- tính toán lặp
- thao tác không giới hạn
- memory
- blocking

## 7. Maintainability

Kiểm tra:

- duplicate
- complexity
- naming
- coupling
- cohesion
- testability
- convention

## 8. Test

Kiểm tra test có thật sự chứng minh acceptance criteria hay chỉ test cho có.

## 9. Scope

Kiểm tra có sửa ngoài task không.

## Severity

`CRITICAL` — lỗi nghiêm trọng, security, mất dữ liệu

`HIGH` — lỗi chức năng lớn hoặc regression

`MEDIUM` — lỗi đáng kể

`LOW` — lỗi nhỏ

`INFO` — đề xuất

## Quyết định

PASS chỉ khi:

- không có CRITICAL
- không có HIGH
- acceptance criteria đạt
- test cần thiết pass
- scope đúng

Nếu không:

`FAIL`

## File bắt buộc

`.artifacts/reviews/TASK-XXX.md`

Mẫu:

# Code Review — TASK-XXX

## Phạm vi review

## Requirement Compliance

## Design Compliance

## Findings

### [SEVERITY] Tên lỗi

- Vị trí:
- Bằng chứng:
- Ảnh hưởng:
- Đề xuất:

## Test Review

## Regression Review

## Security Review

## Scope Review

## Kết luận

`PASS` hoặc `FAIL`

Nếu FAIL → chỉ được sửa unit hiện tại và review lại.

Nếu PASS → DỪNG và chờ người dùng cho phép unit tiếp theo.
