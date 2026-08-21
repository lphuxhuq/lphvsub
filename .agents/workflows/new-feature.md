---
description: Phân tích và thiết kế feature mới theo quy trình có approval gate, chưa code.
---

# /new-feature

## BƯỚC 0 — HIỂU PROJECT

Nếu `.artifacts/project-map.md` chưa có hoặc đã lỗi thời:

→ chạy `/reverse-engineer`

Nếu chưa hiểu đủ → DỪNG.

## BƯỚC 1 — PHÂN TÍCH YÊU CẦU

1. Chạy `requirement-analysis`.
2. Tạo `.artifacts/requirements/<feature>.md`.
3. Hiển thị tóm tắt.
4. DỪNG.

Chờ người dùng:

`DUYỆT PHÂN TÍCH`

Không được tự suy diễn rằng đã được duyệt.

## BƯỚC 2 — THIẾT KẾ

Sau khi được duyệt:

1. Chạy `architecture-design`.
2. Tạo `.artifacts/designs/<feature>.md`.
3. DỪNG.

Chờ:

`DUYỆT THIẾT KẾ`

## BƯỚC 3 — CHIA TASK

Sau khi Design được duyệt:

1. Chạy `task-breakdown`.
2. Tạo `.artifacts/tasks/<feature>.md`.
3. DỪNG.

Chờ:

`DUYỆT TASK`

## BƯỚC 4

Workflow này không tự code.

Sau khi Task được duyệt, người dùng chạy:

`/implement-next`
