---
name: architecture-design
description: Thiết kế solution dựa trên yêu cầu đã duyệt và kiến trúc project hiện tại, trước khi chia task hoặc code.
---

# SKILL: THIẾT KẾ KIẾN TRÚC

## Điều kiện bắt buộc

Phải có:

- Requirement Analysis
- người dùng đã duyệt Analysis

Nếu chưa có → DỪNG.

## Mục tiêu

Tạo thiết kế nhỏ nhất có thể đáp ứng yêu cầu nhưng vẫn phù hợp với project hiện tại.

## Phải phân tích

- component cần thêm/sửa
- database
- API
- frontend
- service
- dependency
- validation
- error handling
- security
- performance
- testing
- migration/rollback nếu cần

## Nguyên tắc

- Ưu tiên reuse.
- Không refactor không liên quan.
- Không tạo abstraction cho nhu cầu chưa tồn tại.
- Không thay đổi public contract ngoài yêu cầu đã duyệt.
- Giữ thay đổi nhỏ và dễ review.

## File bắt buộc

`.artifacts/designs/<feature>.md`

Mẫu:

# Thiết kế

## 1. Requirement đã duyệt

## 2. Kiến trúc hiện tại liên quan

## 3. Kiến trúc đề xuất

## 4. Component thay đổi

## 5. Data Flow

## 6. Control Flow

## 7. Database

## 8. API Contract

## 9. UI Contract

## 10. Validation

## 11. Error Handling

## 12. Security

## 13. Performance

## 14. Testing

## 15. Migration/Rollback

## 16. File dự kiến thay đổi

## 17. File không được tự ý thay đổi

## 18. Rủi ro

## 19. Phương án đã cân nhắc

## 20. Quyết định thiết kế

## Approval Gate

Kết thúc:

`TRẠNG THÁI: CHỜ DUYỆT THIẾT KẾ`

Chỉ tiếp tục khi người dùng nói:

`DUYỆT THIẾT KẾ`
