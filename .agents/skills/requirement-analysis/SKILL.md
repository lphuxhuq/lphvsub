---
name: requirement-analysis
description: Phân tích yêu cầu thành specification rõ ràng, có acceptance criteria, edge case, dependency và phạm vi trước khi thiết kế.
---

# SKILL: PHÂN TÍCH YÊU CẦU

## Mục tiêu

Biến yêu cầu của người dùng thành yêu cầu kỹ thuật rõ ràng và có thể kiểm thử.

**Không được code.**

## Quy trình

1. Xác định mục tiêu.
2. Phân tách functional requirement.
3. Phân tách non-functional requirement.
4. Đối chiếu project hiện tại.
5. Xác định module bị ảnh hưởng.
6. Xác định dependency.
7. Xác định constraint.
8. Xác định edge case.
9. Xác định backward compatibility.
10. Viết acceptance criteria.
11. Tìm điểm mơ hồ.

## File bắt buộc

`.artifacts/requirements/<feature>.md`

Mẫu:

# Phân tích yêu cầu

## 1. Mục tiêu

## 2. User Story

## 3. Functional Requirements

- FR-01

## 4. Non-functional Requirements

- NFR-01

## 5. Hành vi hiện tại

## 6. Module bị ảnh hưởng

## 7. Dependency

## 8. Constraint

## 9. Edge Cases

## 10. Security

## 11. Performance

## 12. Acceptance Criteria

Mỗi criterion phải có cách kiểm tra.

## 13. Điểm chưa rõ

Mỗi điểm gồm:

- Câu hỏi
- Vì sao quan trọng
- Giả định an toàn hiện tại nếu có

## 14. Ngoài phạm vi

Liệt kê rõ những thứ KHÔNG làm.

## Approval Gate

Kết thúc:

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`

AI phải dừng.

Chỉ tiếp tục khi người dùng nói rõ:

`DUYỆT PHÂN TÍCH`
