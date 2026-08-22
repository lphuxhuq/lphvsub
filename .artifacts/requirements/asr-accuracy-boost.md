# Phân tích yêu cầu — ASR Accuracy Boost (Paraformer + Selective OCR Fusion)

> Nguồn: task spec user + RE report + root-cause analysis Phase 1-2. Feature name: `asr-accuracy-boost`.

## 1. Mục tiêu

Tăng độ đầy đủ và chính xác của transcript tiếng Trung trước khi dịch Vietsub, xử lý 3 triệu chứng: (a) Paraformer nhận thiếu từ/cụm từ, (b) câu mất đầu/cuối, (c) đoạn có tiếng nói nhưng transcript rỗng. Khi video có hard-sub, OCR được dùng chọn lọc (selective) để phục hồi/so khớp — không phụ thuộc tuyệt đối vào một engine. Không được phá timestamp và pipeline SRT hiện tại.

## 2. User Story

- Là người làm Vietsub video Douyin, tôi muốn transcript gốc đầy đủ từng câu để bản dịch không thiếu ý.
- Tôi muốn các câu bị nghi ngờ sai được phát hiện tự động và chỉ những vùng đó mới tốn thêm thời gian OCR.
- Khi Paraformer và OCR chênh nhau, hệ thống phải quyết định có lý do (scoring) chứ không đè một bên.

## 3. Functional Requirements

### Nhóm A — Sửa nguồn mất text của Paraformer (không cần OCR)

- **FR-A1**: Khi `bg_mode=demucs` và tách vocals thành công, bước ASR nhận đầu vào là `vocals.wav` (đã resample 16kHz mono) thay vì audio gốc; fallback về audio gốc khi separation fail hoặc chạy chế độ `duck/none`.
- **FR-A2**: Worker Paraformer thêm speech padding quanh mỗi VAD chunk (mặc định 0.3s mỗi bên, configurable), clamp để không chồng chunk kề, timestamp **vẫn lấy biên VAD gốc** (không cộng padding vào start/end).
- **FR-A3**: Chunk có speech nhưng decode text rỗng phải được emit ra ngoài (`{"empty": true, start, end}`) kèm đếm tổng và log cảnh báo — không được nuốt im lặng.
- **FR-A4**: Giữ nguyên fallback Whisper khi Paraformer lỗi (hành vi hiện tại transcriber.py:183-184).

### Nhóm B — Suspect segment detection

- **FR-B1**: Hàm `detect_suspect_segments(asr_segments, audio_metadata, ocr_segments=None) -> {normal, suspect}` tách module riêng; mỗi suspect mang `reason` cụ thể (ví dụ: `empty_speech_chunk`, `text_too_short_for_duration`, `gap_anomaly`, `ocr_no_asr_match`).
- **FR-B2**: heuristic: (1) chunk rỗng từ FR-A3; (2) độ dài text (ký tự) bất thường so với duration — char rate ngoài dải adaptive (định nghĩa ở design, không hard-code một ngưỡng cứng duy nhất); (3) gap timestamp bất thường giữa hai câu kề; (4) có OCR text nhưng không có ASR text trong cùng window.

### Nhóm C — Selective OCR fallback

- **FR-C1**: OCR chỉ kích hoạt khi (tất cả phải đúng): video có hard-sub (user bật `enable_ocr` HOẶC auto-detect đơn giản ở design), VÀ tồn tại ít nhất 1 suspect segment. Không bao giờ OCR toàn bộ video khi không cần.
- **FR-C2**: OCR chạy trên frame trong window [suspect.start − margin, suspect.end + margin] tại FPS sampling thấp (ví dụ 2-5 fps, chốt ở design), trích region phụ đề dưới cùng theo tỷ lệ khung.
- **FR-C3**: Kết quả OCR: `{text, start_time, end_time, confidence}` sau khi normalize (strip, full-width → half-width, lọc ký tự không phải CJK/punct) và merge các frame liên tiếp trùng text.
- **FR-C4**: Xử lý: duplicate frame text, multi-line subtitle (ghép dòng), subtitle xuất hiện/mất giữa chừng, OCR confidence thấp → đánh dấu không dùng.

### Nhóm D — ASR + OCR Fusion

- **FR-D1**: Fusion theo từng segment (không phải toàn cục "OCR > ASR"): quyết định bằng FINAL_SCORE tổng hợp từ ASR_SCORE, OCR_SCORE, ALIGNMENT_SCORE, TEMPORAL_SCORE, TEXT_COMPLETENESS_SCORE (trọng số chốt ở design, có rationale).
- **FR-D2**: Text alignment ASR↔OCR mức ký tự (edit distance / substring) phát hiện OCR bổ sung đầu/cuối câu; kết quả merge **không tạo text trùng lặp**.
- **FR-D3**: Quy tắc timestamp: OCR chỉ bổ sung text → giữ timestamp ASR. ASR rỗng hoàn toàn nhưng OCR có text → dùng timestamp OCR. Merge duration theo temporal overlap. Bất biến: start < end, không duration = 0, không tạo overlap vô lý với câu kề.
- **FR-D4**: Khi ASR và OCR khác nhau đáng kể mà scoring không phân thắng (dưới ngưỡng chốt ở design) → **giữ ASR, đánh dấu suspect trong report**, không tự overwrite (Case 6 của spec).
- **FR-D5**: Fusion không đổi `id`, không đổi số segment khi không có gì bổ sung (Case 1: output == input).

### Nhóm E — Báo cáo & debug

- **FR-E1**: File `asr_fusion_report.json` trong `data/`: số suspect, lý do từng câu, quyết định fusion, score từng thành phần — để audit sau.

## 4. Non-functional Requirements

- **NFR-1**: Pipeline không OCR chạy chậm thêm ≤ 5% (chỉ thêm heuristic in-memory).
- **NFR-2**: Khi OCR bật, thời gian tăng chỉ tuyến tính theo tổng时长 suspect window, không OCR toàn video.
- **NFR-3**: Backward compatibility: format `transcript_original.json` giữ nguyên tối thiểu `start/end/text` (resume cache pipeline.py:383-390 không gãy); SRT/timing/TTS không đổi hành vi khi không có OCR/fusion đổi gì.
- **NFR-4**: OCR dependency cài trong env phù hợp (không phá `.venv-asr` hiện có của worker ASR), CPU chạy được.
- **NFR-5**: Test coverage: heuristic + fusion + alignment đạt unit test đầy đủ (Case 1-8 của spec); ASR worker test được qua mock protocol.
- **NFR-6**: Cache/resume: kết quả OCR cache theo (video, frame range, region) để chạy lại không OCR lại.

## 5. Hành vi hiện tại (tóm tắt từ Phase 1-2)

ASR ăn audio gốc trộn nhạc; VAD không pad; chunk rỗng bị nuốt; không OCR; transcript cache theo 3 field; SRT từ start/end trực tiếp.

## 6. Module bị ảnh hưởng

| Module | Thay đổi |
|---|---|
| `autodub/pipeline.py` (Step 2.5/3) | Chọn nguồn audio ASR; gọi suspect-detect + OCR + fusion sau ASR |
| `autodub/speech/asr_paraformer_worker.py` | Padding, empty-chunk signaling (FR-A2, A3) |
| `autodub/speech/paraformer_transcriber.py` | Parse message `empty` mới |
| `autodub/media/` (module mới `ocr.py` hoặc `autodub/media/ocr/`) | Frame extraction + OCR engine + normalize/merge |
| `autodub/text/` (module mới `fusion.py`) | detect_suspect_segments, alignment, scoring, fusion |
| `autodub/config.py` | Settings mới (enable_ocr, padding, fps, region, trọng số — chốt ở design) |

## 7. Dependency

- Engine OCR mới (PaddleOCR hoặc RapidOCR — quyết định ở design theo ràng buộc CPU/venv).
- ffmpeg frame sampling (đã có sẵn ffmpeg).
- Không đổi dependency của `.venv-asr` (worker chỉ đổi logic nội bộ, không thêm package).

## 8. Constraint

- Timeline `start/end` là single source of truth — không được phá SRT/TTS/timing hiện hành.
- Worker ASR standalone, giao thức JSON-lines — mọi thay đổi phải tương thích protocol cũ (thêm key mới OK, đổi key cũ KHÔNG).
- Không rewrite pipeline — chỉ chèn bước mới sau Step 3.
- Windows + Git Bash môi trường chạy.

## 9. Edge Cases

- Video không có hard-sub (Case 7): OCR off, pipeline y như cũ.
- ASR rỗng toàn bộ (đã có RuntimeError pipeline.py:428-433) — fusion không che mất lỗi này một cách im lặng khi OCR cũng rỗng.
- OCR lỗi ký tự thường xuyên (Case 5): scoring phải nghiêng giữ ASR.
- Subtitle 2 dòng, dòng dài wrap.
- Suspect window nằm sát cuối video (clamp biên).
- Video quay dọc (Douyin 9:16) — region phụ đề theo tỷ lệ vẫn đúng.
- Hard-sub di động / phụ đề kiểu karaoke đổi liên tục → merge frame phải có ngưỡng ổn định.

## 10. Security

Không có surface mới: OCR local, không network. Chỉ ghi file trong work dir. Frame tạm cần dọn hoặc cache có kiểm soát (disk usage).

## 11. Performance

- Ưu tiên thứ tự: Paraformer → suspect detect (in-memory) → OCR chỉ trên suspect.
- Frame sampling FPS thấp + region crop trước khi OCR.
- Cache OCR + frame (NFR-6).

## 12. Acceptance Criteria

| # | Criterion | Cách kiểm tra |
|---|---|---|
| AC-1 | Case 1: ASR đủ → output fusion == input (không thêm module nào chạy OCR) | Unit test: fusion passthrough |
| AC-2 | Case 2/3: thiếu đầu/cuối → OCR bổ sung đúng vị trí, không duplicate | Unit test alignment merge |
| AC-3 | Case 4: ASR empty + OCR có text → dùng OCR text + timestamp OCR | Unit test |
| AC-4 | Case 5: OCR sai vài ký tự → ASR được giữ | Unit test scoring |
| AC-5 | Case 6: khác hoàn toàn → giữ ASR + suspect flag | Unit test |
| AC-6 | Case 7: không hard-sub → không gọi OCR API/frame extraction nào | Test với mock counter |
| AC-7 | Case 8: nhiều speaker → không crash, không mất segment (số segment không giảm sau bất kỳ bước nào) | Unit test invariant |
| AC-8 | Worker emit `empty` chunk + padding hoạt động, timestamp không trượt do padding | Unit test worker logic (mock recognizer) |
| AC-9 | ASR trên vocals khi có, fallback đúng khi không có | Unit test lựa chọn nguồn + integration pipeline |
| AC-10 | Bất biến timestamp: mọi segment start<end, duration>0, không overlap kề mới | Property test trên fusion output |
| AC-11 | `transcript_original.json` vẫn đọc được bởi resume logic cũ | Regression test |
| AC-12 | Full suite cũ 630 test PASS | CI |

## 13. Điểm chưa rõ

1. **Chọn engine OCR (PaddleOCR vs RapidOCR)?** — Quan trọng vì quyết định venv/latency/độ chính xác zh. Giả định an toàn: RapidOCR (onnxruntime, nhẹ, không pull Paddle đầy đủ) — quyết định cuối ở design.
2. **Auto-detect hard-sub có cần không, hay user bật tay?** — Giả định an toàn: setting thủ công `enable_ocr` + auto-detect rẻ (OCR thử 3-5 frame, có text CJK ở region dưới → coi như có hard-sub) ở design.
3. **Ngưỡng "khác nhau đáng kể" và trọng số scoring?** — Chốt ở design kèm rationale + hằng số có tên.
4. **Padding 0.3s có đủ?** — Thí nghiệm Phase 2 chưa có video mẫu; chọn default 0.3s + configurable.

## 14. Ngoài phạm vi

- Không sửa translation/TTS/timing/merge.
- Không thay Paraformer bằng engine ASR khác, không thêm LM decoding.
- Không OCR để *dịch* hard-sub tiếng Trung phức tạp (styled, nghệ thuật).
- Không làm UI mới cho OCR (chỉ config; GUI wiring tối thiểu nếu cần).
- Không handle video không phải 16kHz (đã ép ở extract).

TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH
