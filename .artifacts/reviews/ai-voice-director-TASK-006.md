# Code Review — TASK-006 (GUI Character Director Panel)

## Phạm vi review
- **Production files:**
  - [`autodub_gui/pages/editor_panels.py`](file:///d:/Project/lphvsub-main/autodub_gui/pages/editor_panels.py) (Tích hợp Speaker Director Section vào `VoicePanel`)
  - [`autodub_gui/pages/editor_page.py`](file:///d:/Project/lphvsub-main/autodub_gui/pages/editor_page.py) (Nạp danh sách nhân vật và `speaker_voices` vào `VoicePanel`)
- **Test file:** [`tests/test_editor_voice_panel.py`](file:///d:/Project/lphvsub-main/tests/test_editor_voice_panel.py)

## Requirement & Design Compliance
- [x] Checkbox `cb_auto_director` ("Tự động phân vai AI (Đa nhân vật)") cho phép bật/tắt trực quan.
- [x] Khi video có $\ge 2$ speaker, hiển thị thẻ nhân vật: tên người nói, vai trò (Dẫn chuyện / Nhân vật), giới tính (Nam / Nữ), số câu thoại.
- [x] Mỗi nhân vật có một `VoicePicker` riêng, cho phép chọn giọng (VieNeu hoặc CapCut) và nghe thử.
- [x] Thay đổi giọng trên picker tự động ghi nhận vào `speaker_voices` và cập nhật `render_opts.json`.

## Findings
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO:** Khi video chỉ có 1 người nói, phần đa nhân vật tự động ẩn đi để giao diện gọn gàng.

## Test Review
- 1/1 test passed trong 0.28s với `pytest-qt`.

## Kết luận
`PASS`
