# ROOT CAUSE ANALYSIS — Paraformer thiếu text (Phase 2)

> Đối chiếu 13 giả thuyết của task spec với code thực tế. Kết luận nào cũng có file:line. Không sửa code ở phase này.

## A. Nguyên nhân xác nhận từ code (xếp theo tác động)

### RC-1 — ASR chạy trên audio GỐC trộn nhạc nền (CAO)
- `pipeline.py:424` gọi `transcribe(audio_path, ...)` với `audio_path` = bản 16kHz mono **chưa tách nhạc**.
- Demucs (`_resolve_background`, pipeline.py:1438) **đã sản xuất sẵn `vocals.wav`** trong `data/` (vocal_separator.py:177-190) và pipeline chờ Demucs xong trước ASR ở chế độ tuần tự (pipeline.py:411-414) — file vocals **tồn tại ngay tại thời điểm ASR nhưng bị bỏ qua** (chỉ `no_vocals.wav` được dùng làm nền).
- Hệ quả: VAD threshold 0.35 trên nhạc + tiếng → speech bị chặn cả cụm → mất câu; hoặc decode ra text rỗng (RC-3).
- Ghi chú: khi chạy song song (overlap_ok, pipeline.py:405-409) vocals.wav có thể chưa xong — cần chờ future trước khi dùng.

### RC-2 — VAD không có speech padding (CAO — triệu chứng "mất đầu/cuối câu")
- Nhánh Whisper có `speech_pad_ms=500` (transcriber.py:414). Worker Paraformer KHÔNG pad: biên segment = đúng biên VAD (asr_paraformer_worker.py:141-142).
- Silero threshold 0.35 thường cắt vào vài trăm ms sau khi speech bắt đầu → mất chữ đầu câu; min_silence 0.5s kết thúc sớm → mất chữ cuối.

### RC-3 — Chunk có speech nhưng decode rỗng → drop im lặng (CAO — triệu chứng "có tiếng mà không có text")
- `asr_paraformer_worker.py:133-134`: `if not text: return` — không log, không đếm, không emit. Không có cách nào phát hiện từ output.

### RC-4 — max_speech_duration = 20s chặt câu dài không merge (TRUNG BÌNH)
- `asr_paraformer_worker.py:120`. Silero force-split tại 20s; hai nửa được decode riêng — không mất hẳn nhưng có thể mất ngữ cảnh/chữ ở biên split.

### RC-5 — min_speech_duration = 0.1s bỏ utterance ngắn (THẤP)
- `asr_paraformer_worker.py:119`. Chữ cảm thán < 100ms biến mất hoàn toàn.

## B. Giả thuyết bị LOẠI (không tồn tại trong code)

| Giả thuyết spec | Lý do loại |
|---|---|
| Chunk boundary làm mất từ / speech overlap giữa chunk | VAD tuần tự không overlap (worker:148-160) |
| Sampling rate sai | Worker ép 16kHz + check (worker:109-110); extract ffmpeg `-ar 16000` |
| Post-processing cắt text | `split_long_segments` chỉ tách tại dấu câu, không xoá text (transcriber.py:476) |
| Timestamp merge mất segment | Không tồn tại bước merge timestamp nào |
| SRT formatter mất nội dung | `generate_srt` giữ nguyên text, chỉ tách cue (srt.py:142) |
| Audio volume thấp | SUY LUẬN gián tiếp qua RC-1 (loudnorm chỉ áp cho TTS output, không áp cho đầu vào ASR) |

## C. Hệ quả thiết kế (input cho Phase 3)

1. **Nguồn cải thiện rẻ nhất, trước OCR**: cho ASR ăn `vocals.wav` (resample 16k mono bằng ffmpeg khi cần) khi bg_mode=demucs. Không cần model mới, tận dụng file có sẵn.
2. **Sửa worker đáng giá**: thêm speech padding quanh VAD chunk (~0.3-0.5s mỗi bên, clamp để không chồng chunk kề), log + đếm chunk decode rỗng (phát hiện RC-3 thay vì nuốt), phát tín hiệu `{"empty": true, start, end}` để Phase detect-suspect dùng.
3. **Detect suspect segments** cần tín hiệu: chunk rỗng (RC-3), gap thời lượng bất thường giữa các segment, text quá ngắn so với duration. Đây là input chọn vùng OCR.
4. **OCR không tồn tại** — build mới hoàn toàn (xem RE report); chỉ chạy selective trên suspect window + region phụ đề để giữ performance.
5. Ràng buộc bất biến: output transcript `start/end/text` (resume cache pipeline.py:383-390), timeline là single source of truth cho SRT/TTS/timing.

## D. Cần thí nghiệm trên video mẫu để chốt độ ưu tiên (CHƯA XÁC ĐỊNH)

- So sánh số câu ASR trên original vs vocals.wav với cùng video Douyin.
- Đo số chunk decode rỗng thực tế (sau khi thêm đếm).
Chỉ ảnh hưởng **thứ tự** ưu tiên, không ảnh hưởng hướng thiết kế.

TRẠNG THÁI: HOÀN THÀNH (Phase 2)
