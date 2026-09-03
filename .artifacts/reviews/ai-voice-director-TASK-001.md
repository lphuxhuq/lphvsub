# Code Review — TASK-001 (Data Models)

## Phạm vi review
- **Production file:** [`autodub/speech/voice_models.py`](file:///d:/Project/lphvsub-main/autodub/speech/voice_models.py)
- **Test file:** [`tests/test_voice_models.py`](file:///d:/Project/lphvsub-main/tests/test_voice_models.py)

## Requirement & Design Compliance
- [x] Định nghĩa đầy đủ các trường thống kê F0 trong `PitchStats` (`pitch_median`, `pitch_p10`, `pitch_p90`, `pitch_std`, `voiced_ratio`, `confidence`).
- [x] `PitchStats` và `VoiceProfile` là bất biến (`frozen=True`).
- [x] `SpeakerProfile` chứa đầy đủ thông tin âm học, giới tính xác suất (`gender_confidence`), vai trò (`role_confidence`), thời lượng và độ bao phủ timeline.
- [x] `VoiceAssignment` hỗ trợ phân biệt nguồn gán (`auto`, `manual_override`, `fallback`).
- [x] `CastingResult` đóng gói toàn bộ kết quả phân vai kèm trạng thái toggle `director_enabled`.

## Findings
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO:** Tất cả dataclass đều tương thích hoàn toàn với `dataclasses.asdict()` để tiện lưu vào `render_opts.json`.

## Test Review
- 4/4 tests passed trong 0.08s. Kiểm tra đầy đủ tính bất biến, serialization, assignment và casting result.

## Kết luận
`PASS`
