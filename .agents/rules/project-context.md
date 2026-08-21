# Quy tắc hiểu và làm việc với Project

Các quy tắc này áp dụng cho mọi nhiệm vụ lập trình trong repository.

## 1. Hiểu project trước khi sửa

Trước khi sửa code phải xác định:

- cấu trúc thư mục
- entry point
- module chính
- cấu hình
- database/data layer
- API
- UI
- test
- CI/CD
- tài liệu
- dependency

Nếu chưa có hoặc project-map đã lỗi thời thì phải chạy `/reverse-engineer`.

## 2. Tôn trọng kiến trúc hiện tại

Ưu tiên cách project đang sử dụng cho:

- đặt tên
- tổ chức thư mục
- dependency injection
- xử lý lỗi
- logging
- validation
- testing
- database
- API

Không tự ý đưa framework/pattern mới vào chỉ vì AI thích cách đó hơn.

## 3. Kiểm soát phạm vi

Chỉ sửa những file cần thiết cho task đã duyệt.

Không được tự ý:

- refactor code không liên quan
- đổi tên class/function không liên quan
- format toàn bộ project
- nâng version dependency không cần thiết
- rewrite module đang chạy tốt
- thay đổi kiến trúc ngoài thiết kế đã duyệt

## 4. Không được đoán

Nếu chưa xác định được từ source code, test, tài liệu hoặc configuration thì đánh dấu `CHƯA XÁC ĐỊNH`.

Không tự bịa:

- API
- database column
- business rule
- dependency
- hành vi hệ thống

## 5. Bảo mật

Không để lộ hoặc commit:

- API key
- password
- token
- private key
- secret
- thông tin nhạy cảm

## 6. Nguyên tắc dừng

Phải DỪNG nếu:

- yêu cầu chưa rõ
- kiến trúc chưa rõ
- dependency thiếu
- cần sửa ngoài phạm vi
- test không chạy được
- phát hiện lỗi nghiêm trọng
- thiết kế đã duyệt không còn phù hợp

Khi dừng phải giải thích nguyên nhân và chờ người dùng quyết định.
