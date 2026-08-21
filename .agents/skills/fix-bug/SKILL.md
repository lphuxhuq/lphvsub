---
name: fix-bug
description: Quy trình sửa bug có kiểm soát: tái hiện bug, reverse engineering, tìm root cause, thiết kế cách sửa, chờ duyệt, implement, regression test và code review.
---

# SKILL: FIX BUG

## Mục tiêu

Sửa đúng nguyên nhân gốc của bug, không sửa triệu chứng một cách mù quáng.

Quy trình bắt buộc:

REPRODUCE
→ INVESTIGATE
→ ROOT CAUSE ANALYSIS
→ DUYỆT
→ FIX DESIGN
→ DUYỆT
→ IMPLEMENT
→ TEST
→ REGRESSION TEST
→ CODE REVIEW
→ PASS

## QUY TẮC TUYỆT ĐỐI

- Không sửa code ngay khi vừa nhận bug.
- Không đoán nguyên nhân.
- Phải cố gắng tái hiện bug trước.
- Phải tìm Root Cause trước khi đề xuất fix.
- Không được thay đổi code trước khi Root Cause được duyệt.
- Không tự mở rộng phạm vi sửa.
- Không được coi "hết lỗi ở trường hợp này" là đủ; phải kiểm tra regression.
- Nếu không tái hiện được bug, phải báo rõ và tiếp tục điều tra bằng evidence, không tự bịa nguyên nhân.

# PHASE 1 — TIẾP NHẬN BUG

Ghi nhận:

## Bug

## Expected Behavior

## Actual Behavior

## Steps To Reproduce

## Environment

## Error Message / Stack Trace

## Frequency

- ALWAYS
- SOMETIMES
- UNKNOWN

## Severity

- CRITICAL
- HIGH
- MEDIUM
- LOW

Nếu thông tin thiếu nhưng có thể điều tra tiếp thì không hỏi lan man; hãy kiểm tra source code, log, test và configuration trước.

# PHASE 2 — REPRODUCE

Cố gắng tái hiện lỗi bằng:

- test hiện có
- unit test
- integration test
- application runtime
- API request
- UI flow
- database state
- log/stack trace

Ghi:

## Reproduction Result

`REPRODUCED` / `NOT REPRODUCED` / `PARTIALLY REPRODUCED`

## Evidence

Phải ghi bằng chứng cụ thể.

Nếu không tái hiện được:

- ghi những gì đã thử
- ghi những gì đã kiểm tra
- xác định phần còn UNKNOWN

Không được tuyên bố bug đã được tái hiện nếu chưa có evidence.

# PHASE 3 — REVERSE ENGINEERING

Trace flow thực tế:

User/UI
→ Controller/Handler
→ Service
→ Repository/Data Layer
→ Database/External API

Kiểm tra cả chiều ngược lại nếu cần.

Xác định:

- file liên quan
- function/class liên quan
- call chain
- dữ liệu đầu vào
- dữ liệu đầu ra
- state
- exception
- database query
- external API
- validation
- authentication/authorization

Không sửa code ở phase này.

# PHASE 4 — ROOT CAUSE ANALYSIS

Phân biệt:

### Symptom

Điều người dùng nhìn thấy.

### Root Cause

Nguyên nhân thực tế tạo ra symptom.

### Contributing Factors

Các yếu tố làm lỗi xảy ra hoặc khó phát hiện.

Bắt buộc tạo:

`.artifacts/bug-fixes/<bug-id>-root-cause.md`

Mẫu:

# Root Cause Analysis

## Bug

## Reproduction

## Symptom

## Root Cause

## Evidence

## Call Flow

## Affected Files

## Contributing Factors

## Why Existing Tests Did Not Catch It

## Impact

## Regression Risk

## Proposed Fix

## Alternatives Considered

## Scope

## Unknowns

## Approval Gate

Kết thúc:

`TRẠNG THÁI: CHỜ DUYỆT NGUYÊN NHÂN`

DỪNG.

Chỉ tiếp tục khi người dùng nói:

`DUYỆT NGUYÊN NHÂN`

# PHASE 5 — FIX DESIGN

Sau khi Root Cause được duyệt:

Thiết kế cách sửa nhỏ nhất nhưng giải quyết đúng root cause.

Phải xác định:

- file cần sửa
- function/class cần sửa
- logic trước
- logic sau
- validation
- error handling
- backward compatibility
- regression risk
- test cần thêm/sửa
- rollback

Tạo:

`.artifacts/bug-fixes/<bug-id>-fix-design.md`

Mẫu:

# Fix Design

## Root Cause Đã Duyệt

## Cách Sửa

## Files Được Phép Sửa

## Files Không Được Sửa

## Logic Trước

## Logic Sau

## Regression Tests

## Existing Tests

## Risks

## Rollback

## Change Budget

## Approval Gate

Kết thúc:

`TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`

DỪNG.

Chỉ tiếp tục khi người dùng nói:

`DUYỆT CÁCH SỬA`

# PHASE 6 — IMPLEMENT FIX

Chỉ implement đúng fix design đã duyệt.

Không:

- refactor không liên quan
- đổi architecture
- nâng dependency
- sửa bug khác
- format toàn bộ project
- đổi API ngoài phạm vi

Nếu cần sửa thêm file ngoài scope:

`TRẠNG THÁI: YÊU CẦU MỞ RỘNG PHẠM VI`

DỪNG và chờ duyệt.

# PHASE 7 — TEST

Phải kiểm tra ít nhất:

1. Test case tái hiện bug cũ.
2. Test case expected behavior.
3. Edge cases liên quan.
4. Existing tests liên quan.
5. Build/type check/lint tùy project.

Không được chỉ test happy path.

# PHASE 8 — REGRESSION TEST

Kiểm tra:

- behavior cũ
- module liên quan
- API liên quan
- database behavior
- UI flow liên quan
- error handling

Mục tiêu:

`BUG ĐÃ FIX` + `KHÔNG TẠO BUG MỚI`

# PHASE 9 — CODE REVIEW

Review độc lập:

- Root Cause có thực sự được giải quyết không?
- Fix có đúng Design không?
- Có sửa triệu chứng thay vì nguyên nhân không?
- Có regression không?
- Có security issue không?
- Có performance issue không?
- Có test đầy đủ không?
- Có sửa ngoài scope không?

Severity:

- CRITICAL
- HIGH
- MEDIUM
- LOW
- INFO

Nếu còn CRITICAL/HIGH:

`FAIL`

Phải sửa và review lại.

Nếu không còn CRITICAL/HIGH và tất cả acceptance criteria đạt:

`PASS`

# PHASE 10 — KẾT QUẢ

Tạo:

`.artifacts/bug-fixes/<bug-id>-final.md`

Mẫu:

# Bug Fix Final Report

## Bug

## Root Cause

## Fix

## Files Changed

## Tests

## Regression Tests

## Review

## Remaining Risks

## Final Status

`PASS` / `FAIL`

## Quy tắc kết thúc

Sau khi PASS:

- không tự sửa thêm
- không tự xử lý bug khác
- không tự refactor
- báo kết quả cho người dùng
