# Hệ thống quy trình lập trình Antigravity — Tiếng Việt

Đây là bộ workflow có kiểm soát cho Antigravity.

## Quy trình bắt buộc

PHÂN TÍCH NGƯỢC PROJECT
→ PHÂN TÍCH YÊU CẦU
→ DUYỆT
→ THIẾT KẾ
→ DUYỆT
→ CHIA TASK
→ DUYỆT
→ CODE MỘT UNIT
→ TEST
→ REVIEW
→ DUYỆT
→ UNIT TIẾP THEO
→ FINAL AUDIT

## Nguyên tắc không được vi phạm

- Không code trước khi hoàn thành phân tích, thiết kế và chia task.
- Không tự động code nhiều unit cùng lúc.
- Không chuyển sang unit tiếp theo nếu unit hiện tại chưa PASS review và chưa được người dùng cho phép.
- Không được đoán khi yêu cầu, kiến trúc, dependency hoặc hành vi hiện tại chưa rõ.
- Không tự ý mở rộng phạm vi.
- Phải ưu tiên thay đổi nhỏ, an toàn và dễ rollback.
- Không che giấu lỗi build, test, warning hoặc review.
