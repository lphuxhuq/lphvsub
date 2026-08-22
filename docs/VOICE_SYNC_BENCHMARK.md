# VOICE SYNC — BENCHMARK (fixtures tổng hợp)

> Sinh tự động từ `tests/test_voice_sync_benchmark.py`. Drift trần = 0.15s; tempo trần = 1.15; KHÔNG retime video.

| Fixture | Segments | Avg drift | Max drift | Avg end err | Max end err | Overlap | Forced tempo | Video speed |
|---|---|---|---|---|---|---|---|---|
| A — nói chậm (slot 3.0s, TTS≈0.8×) | 40 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 | 1.0 |
| B — nói nhanh (slot 1.2s, TTS≈1.18×) | 60 | 0.002 | 0.025 | 0.172 | 0.205 | 0 | 31 | 1.0 |
| C — VI dài (slot 2.0s, TTS≈1.4×) | 50 | 0.147 | 0.150 | 0.564 | 1.150 | 49 | 49 | 1.0 |

## So sánh với scheduler cũ (shift→compress→overlap)

- Scheduler cũ cho phép drift tới **1.5s/câu** (trần `timing_max_drift_s`) — dub có thể trễ gần 2 giây so với môi.
- Scheduler mới: max drift đo được ≤ **0.15s** ở mọi fixture; phần TTS thừa được xử lý bằng silence → per-segment tempo (trần 1.15) → overlap nhỏ được báo cáo, thay vì dồn trễ.

## CHƯA XÁC ĐỊNH

Đo trên video Douyin thật (có môi) cần chạy thủ công — benchmark này dùng fixtures tổng hợp để CI lặp lại được.
