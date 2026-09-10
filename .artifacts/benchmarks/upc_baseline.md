# UPC Baseline & Instrumentation Report (TASK-000)

**Date**: 2026-09-06
**Environment**: Windows 11 / Python 3.11.0 / NVMe SSD
**Cache Version**: `upc-v1`

## 1. Media Fingerprint Latency (`compute_media_fingerprint`)
| File Size | Cold Run (ms) | Warm Run Avg (ms) | Speedup / Observation |
|---|---|---|---|
| **0.5 MB (Small)** | 20.551 ms | 0.127 ms | Cache / buffer cached in OS |
| **10.0 MB (Medium)** | 9.815 ms | 0.127 ms | Constant time O(1) sampling |
| **100.0 MB (Large)** | 23.364 ms | 0.165 ms | Sub-millisecond warm fingerprinting |

## 2. Demucs Cache Latency (5MB WAV stems)
| Operation | Measured Latency (ms) | Status |
|---|---|---|
| **Miss Lookup** | 17.678 ms | Checked directory & non-existent bucket |
| **Cold Store** | 36.000 ms | Atomic mkdtemp + 2x WAV copy + atomic JSON meta |
| **Warm Hit & Restore** | 22.073 ms | Validated RIFF header + copied 2x stems to target |

## 3. ASR Cache Latency (100 JSON Transcript Segments)
| Operation | Measured Latency (ms) | Status |
|---|---|---|
| **Miss Lookup** | 13.300 ms | Path check returned None |
| **Cold Store** | 2.117 ms | Atomic write JSON |
| **Warm Hit** | 1.560 ms | JSON read & schema validation |
