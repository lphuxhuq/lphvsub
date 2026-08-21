---
name: project-reverse-engineering
description: Phân tích ngược project hiện tại để AI hiểu cấu trúc, kiến trúc, dependency, data flow, coding convention, rủi ro và các điểm quan trọng trước khi code.
---

# SKILL: PHÂN TÍCH NGƯỢC PROJECT

## Mục tiêu

AI phải hiểu project thực tế trước khi được phép thay đổi code.

Đây là bước điều tra. **Không được sửa code production.**

## Bước 1 — Kiểm kê project

Kiểm tra có chọn lọc:

- cấu trúc repository
- README và tài liệu
- package/build files
- configuration
- entry point
- source code
- test
- database/schema/migration
- API
- frontend
- script
- CI/CD

Không đọc mọi file một cách mù quáng. Tập trung vào file liên quan.

## Bước 2 — Xác định kiến trúc

Phải xác định:

- kiến trúc đang sử dụng
- module
- dependency direction
- entry point
- service
- repository/data layer
- API
- external service
- authentication/authorization
- configuration

## Bước 3 — Reverse engineer flow

Với chức năng quan trọng, trace flow thực tế:

`User → UI → Controller/Handler → Service → Repository/API → Database`

và chiều ngược lại.

Phải ghi nhận:

- ai gọi ai
- input
- output
- side effect
- exception
- database access
- external API

Không được kết luận nếu chưa có bằng chứng từ code.

## Bước 4 — Coding convention

Xác định convention hiện tại:

- naming
- folder
- class/function
- DTO/model
- dependency injection
- validation
- error handling
- logging
- test
- database
- API response

## Bước 5 — Tìm rủi ro

Tìm:

- code trùng
- coupling cao
- dead code
- thiếu test
- security risk
- performance risk
- technical debt
- behavior chưa được document

**Không sửa những vấn đề này trong bước reverse engineering.**

## File bắt buộc

Tạo:

`.artifacts/project-map.md`

Nội dung:

# Project Map

## 1. Tổng quan

## 2. Technology Stack

## 3. Cấu trúc Project

## 4. Kiến trúc

## 5. Entry Points

## 6. Module quan trọng

## 7. Call Flow

## 8. Database/Data Model

## 9. API/External Services

## 10. Authentication/Security

## 11. Testing

## 12. Coding Convention

## 13. Rủi ro

## 14. Những điều chưa xác định

## 15. File đã kiểm tra

## 16. Mức độ tin cậy

Mỗi kết luận quan trọng phải đánh dấu:

- `ĐÃ XÁC MINH`
- `SUY LUẬN`
- `CHƯA XÁC ĐỊNH`

## Kết thúc

Nếu hiểu project đủ tốt:

`TRẠNG THÁI: HOÀN THÀNH`

Nếu chưa đủ:

`TRẠNG THÁI: BỊ CHẶN`

Không được code.
