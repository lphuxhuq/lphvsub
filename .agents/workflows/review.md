---
description: Review một unit hoặc feature hiện tại mà không tự ý sửa ngoài phạm vi.
---

# /review

1. Xác định task/feature cần review.
2. Đọc requirement đã duyệt.
3. Đọc design đã duyệt.
4. Kiểm tra diff thực tế.
5. Kiểm tra code liên quan.
6. Chạy `code-review`.
7. Ghi kết quả vào `.artifacts/reviews/`.
8. Nếu FAIL → không được sang unit khác.
9. Nếu PASS → không tự động code unit tiếp theo.

Nếu review phát hiện lỗi, phân loại severity rõ ràng.
