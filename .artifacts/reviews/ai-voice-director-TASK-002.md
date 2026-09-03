# Code Review — TASK-002 (Acoustic Profiler & F0 Benchmark)

## Phạm vi review
- **Production file:** [`autodub/speech/speaker_profiler.py`](file:///d:/Project/lphvsub-main/autodub/speech/speaker_profiler.py)
- **Test files:** [`tests/test_speaker_profiler.py`](file:///d:/Project/lphvsub-main/tests/test_speaker_profiler.py), [`tests/benchmark_speaker_profiler.py`](file:///d:/Project/lphvsub-main/tests/benchmark_speaker_profiler.py)

## Requirement & Design Compliance
- [x] Tính toán $F_0$ tự tương quan (Autocorrelation qua FFT) trên CPU thuần túy với các thống kê: `pitch_median`, `pitch_p10`, `pitch_p90`, `pitch_std`, `voiced_ratio`, `confidence`.
- [x] Các ngưỡng Hz cấu hình được (`DEFAULT_DEEP_MALE_MAX_HZ = 135.0`, `DEFAULT_YOUNG_MALE_MAX_HZ = 175.0`, `DEFAULT_FEMALE_MAX_HZ = 255.0`).
- [x] Phân loại giới tính xác suất (không kết luận tuyệt đối, xuất kèm `gender_confidence`).
- [x] Phát hiện vai trò Dẫn chuyện (`narrator`) dựa trên độ dài, độ bao phủ timeline và phân vị, tách rời hoàn toàn khỏi giới tính.
- [x] Benchmark hiệu năng: Đo bằng `time.perf_counter()` qua 10 vòng lặp trên audio 5 phút (300s).

## Findings & Real Numbers
- **CRITICAL:** 0
- **HIGH:** 0
- **MEDIUM:** 0
- **LOW:** 0
- **INFO (Real Benchmark Measurements):**
  - **Median Time:** `327.1 ms` (< 500ms ngưỡng yêu cầu).
  - **P95 Time:** `329.3 ms` (< 750ms ngưỡng yêu cầu).
  - **GPU Utilization:** 0% (chạy thuần CPU bằng NumPy FFT decimation).

## Test Review
- 7/7 tests passed trong 5.73s (bao gồm 10 vòng benchmark).

## Kết luận
`PASS`
