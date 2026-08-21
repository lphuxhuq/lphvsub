---
description: Điều phối toàn bộ vòng đời feature theo approval gate, từng unit một.
---

# /full-cycle

## State Machine

`HIỂU PROJECT`
↓
`PHÂN TÍCH`
↓
`DUYỆT`
↓
`THIẾT KẾ`
↓
`DUYỆT`
↓
`CHIA TASK`
↓
`DUYỆT`
↓
`IMPLEMENT UNIT`
↓
`TEST`
↓
`REVIEW`
↓
`DUYỆT`
↓
`UNIT TIẾP THEO`
↓
...
↓
`FINAL AUDIT`

## Giai đoạn 1 — Hiểu

Chạy `/reverse-engineer` nếu cần.

## Giai đoạn 2 — Phân tích

Chạy requirement-analysis.

DỪNG chờ:

`DUYỆT PHÂN TÍCH`

## Giai đoạn 3 — Thiết kế

Chạy architecture-design.

DỪNG chờ:

`DUYỆT THIẾT KẾ`

## Giai đoạn 4 — Chia task

Chạy task-breakdown.

DỪNG chờ:

`DUYỆT TASK`

## Giai đoạn 5 — Vòng lặp implementation

Mỗi vòng:

1. Chọn một TASK.
2. Hiển thị scope.
3. Code đúng TASK đó.
4. Test.
5. Review.
6. Nếu FAIL → sửa → test → review lại.
7. Nếu PASS → DỪNG.
8. Chờ:

`IMPLEMENT UNIT TIẾP`

Không được tự chạy unit tiếp theo.

## Giai đoạn 6 — Final Audit

Khi tất cả unit PASS:

1. Chạy integration test.
2. Chạy `final-audit`.
3. Tạo `.artifacts/reviews/final-audit.md`.
4. Báo PASS/FAIL.

## QUY TẮC TUYỆT ĐỐI

Không biến workflow này thành autonomous coding liên tục.

Người dùng kiểm soát việc chuyển sang giai đoạn tiếp theo.
