---
name: final-audit
description: Kiểm tra toàn bộ feature sau khi tất cả unit đã hoàn thành và review pass, bao gồm requirement, architecture, integration, regression, security, performance, test và code quality.
---

# SKILL: FINAL AUDIT

## Điều kiện

Tất cả unit phải:

- hoàn thành
- test pass
- code review PASS

## Mục tiêu

Xác định feature có thực sự sẵn sàng hay chưa.

## Kiểm tra

### Requirement

Map từng acceptance criteria với:

- code
- test
- kết quả

### Architecture

Kiểm tra implementation còn đúng design không.

### Integration

Kiểm tra:

- module
- API
- database
- frontend/backend
- external service

### Regression

Chạy test hiện có liên quan.

### Security

Review security lần cuối.

### Performance

Tìm regression rõ ràng.

### Code Quality

Kiểm tra:

- duplicate
- dead code
- debug code
- hack tạm
- TODO mới
- convention

### Database

Nếu có:

- schema
- index
- constraint
- migration
- data integrity
- rollback

### Documentation

Kiểm tra tài liệu/config example cần thiết.

## File bắt buộc

`.artifacts/reviews/final-audit.md`

Mẫu:

# FINAL AUDIT

## Feature

## Requirement Matrix

| Requirement | Implementation | Test | Status |
|---|---|---|---|

## Architecture

## Integration

## Regression

## Security

## Performance

## Code Quality

## Documentation

## Rủi ro còn lại

## Kết luận

`PASS` hoặc `FAIL`

FAIL nghĩa là feature chưa hoàn thành.
