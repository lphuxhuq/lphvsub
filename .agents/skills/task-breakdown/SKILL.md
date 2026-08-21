---
name: task-breakdown
description: Chia thiết kế đã duyệt thành các unit nhỏ, độc lập, có dependency, acceptance criteria, test và giới hạn file thay đổi.
---

# SKILL: CHIA TASK

## Điều kiện

Phải có:

- Analysis đã duyệt
- Design đã duyệt

Nếu thiếu → DỪNG.

## Mục tiêu

Chia feature thành những unit đủ nhỏ để:

`Hiểu → Code → Test → Review`

một cách độc lập.

## Một unit tốt phải có

- một mục tiêu rõ
- phạm vi nhỏ
- input/output
- acceptance criteria
- test
- dependency
- file được phép sửa
- file được bảo vệ

## Không được tạo task kiểu

`TASK-001: Implement toàn bộ feature`

## File bắt buộc

`.artifacts/tasks/<feature>.md`

Mẫu:

# Task Breakdown

## 1. Dependency Graph

Ví dụ:

TASK-001
↓
TASK-002
↓
TASK-003 ──┐
TASK-004 ──┤
           ↓
        TASK-005

## 2. Danh sách Unit

### TASK-001 — Tên task

**Mục tiêu:**

**Dependency:**

**File được phép sửa:**

**File không được sửa:**

**Thay đổi dự kiến:**

**Acceptance Criteria:**

**Test:**

**Rủi ro:**

**Rollback:**

## 3. Thứ tự thực hiện

## 4. Change Budget

Xác định giới hạn thay đổi.

## Approval Gate

Kết thúc:

`TRẠNG THÁI: CHỜ DUYỆT TASK`

Chỉ tiếp tục khi người dùng nói:

`DUYỆT TASK`
