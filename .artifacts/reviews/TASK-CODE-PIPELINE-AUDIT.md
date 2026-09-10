# Code Review — TASK-CODE-PIPELINE-AUDIT

## Phạm vi review

Audit các thay đổi pipeline/cache hiện tại liên quan:

- `BUG-URL-RESTART`: tự động tiếp tục dự án cũ khi nhập lại URL.
- `PERF-PIPELINE-SPEED`: tối ưu render video, hậu kỳ audio.
- `Universal Pipeline Cache`: cache liên dự án cho Demucs, ASR, dịch, TTS, align.

Các file trọng tâm đã đọc:

- `autodub/pipeline.py`
- `autodub/pipeline_cache.py`
- `autodub/media/vocal_separator.py`
- `autodub/media/audio.py`
- `autodub/media/video.py`
- `autodub/media/subtitle.py`
- `autodub_gui/pages/new_project_page.py`
- `tests/test_url_resume.py`
- `tests/test_pipeline_cache.py`
- `tests/test_pipeline_cache_orchestrator.py`
- `tests/test_incremental_pipeline_cache.py`
- `tests/test_perf_optimizations.py`

## Requirement Compliance

FAIL.

URL auto-resume cơ bản có helper và GUI/pipeline wiring, nhưng test chưa chứng minh pipeline không chạy lại ASR/Dịch/TTS khi auto-resume. UPC có cache subsystem và unit tests, nhưng invalidation chưa đủ an toàn cho các cấu hình ảnh hưởng trực tiếp đến output.

## Design Compliance

FAIL.

Thiết kế yêu cầu cache deterministic, thread-safe, có invalidation khi file nguồn/cấu hình thay đổi. Implementation hiện tại cache ASR, dịch, TTS và output audio/video theo key quá hẹp hoặc mtime, dẫn đến reuse artifact sai khi cấu hình thay đổi.

## Findings

### [HIGH] ASR cache bỏ qua cấu hình OCR/fusion và có thể tái sử dụng transcript sai

- Vị trí: `autodub/pipeline.py:698`, `autodub/pipeline.py:706`, `autodub/pipeline.py:718`, `autodub/pipeline.py:737`; `autodub/pipeline_cache.py:151`
- Bằng chứng: Pipeline lookup ASR cache bằng `asr_audio + model_name + lang_code + engine`; nếu hit thì gán `segments = cached_asr` và bỏ qua toàn bộ OCR/hardsub fusion. Khi miss, OCR fusion được chạy rồi kết quả sau fusion lại được store vào cùng key ASR thuần.
- Ảnh hưởng: Một run có `ocr_enabled=True` có thể ghi transcript đã fusion vào cache ASR chung. Run sau với `ocr_enabled=False`, hoặc video/config OCR khác nhưng cùng audio ASR, vẫn nhận transcript đã fusion. Ngược lại, nếu cache có transcript ASR thuần, run sau bật OCR sẽ hit cache và không chạy OCR fusion. Đây là lỗi correctness ở Step 3, đặc biệt với hardsub fallback.
- Đề xuất: Cache raw ASR riêng trước OCR, sau đó luôn chạy OCR/fusion theo setting hiện tại; hoặc đưa OCR/hardsub/fusion config và video fingerprint vào key riêng cho transcript sau fusion.

### [HIGH] Translation cache key thiếu source/config context nên có thể trả bản dịch sai ngữ cảnh

- Vị trí: `autodub/pipeline.py:902`, `autodub/pipeline.py:907`, `autodub/pipeline.py:912`, `autodub/pipeline_cache.py:253`, `autodub/pipeline_cache.py:334`
- Bằng chứng: Cache dịch keyed theo `source_text + target_lang + provider`. Pipeline không đưa `source_lang`, glossary, translation domain/style, CPS budget, review/style settings, prompt version hoặc model/provider config cụ thể vào key.
- Ảnh hưởng: Hai dự án có cùng câu nguồn nhưng khác ngôn ngữ nguồn, glossary, phong cách dịch hoặc constraint độ dài sẽ dùng chung bản dịch. Điều này có thể silently sai nội dung hoặc sai phong cách, và cache 100% hit sẽ bỏ qua `_auto_translate` hoàn toàn.
- Đề xuất: Mở rộng key bằng translation context có version: `source_lang`, `target_lang`, provider/model, glossary hash, style/domain, prompt version, CPS/slot policy. Chỉ partial-hit vào checkpoint khi context khớp đầy đủ.

### [HIGH] Reuse final audio/video chỉ dựa vào mtime nên bỏ qua thay đổi render/mix settings

- Vị trí: `autodub/pipeline.py:1163`, `autodub/pipeline.py:1175`, `autodub/pipeline.py:1525`, `autodub/pipeline.py:1538`
- Bằng chứng: `can_reuse_merged_audio` chỉ kiểm tra `audio_vi_full.wav` mới hơn các clip wav/background. `can_reuse_video` chỉ kiểm tra `dubbed_video_path` mới hơn source video, merged audio và burn subtitle.
- Ảnh hưởng: Resume cùng project rồi đổi `background_gain_db`, ducking, SFX preset/volume, speech intervals, subtitle mode/style, blur regions, logo/watermark, reframe/aspect, mask/inpaint, color filter, metadata randomization, speed/fps... vẫn có thể skip Step 6/7 và trả output cũ. Đây là regression lớn vì UI cho phép chỉnh các tùy chọn trước export.
- Đề xuất: Ghi manifest/hash cho từng artifact gồm dependency paths, mtimes/fingerprints và toàn bộ settings ảnh hưởng output. Chỉ reuse khi manifest hiện tại trùng manifest đã render.

### [MEDIUM] TTS cache có fallback cross-engine không an toàn

- Vị trí: `autodub/pipeline.py:2392`, `autodub/pipeline.py:2399`, `autodub/pipeline_cache.py:388`
- Bằng chứng: Với voice resolved là CapCut, nếu không có hit theo `engine=capcut`, code thử restore cùng text/voice với `engine=vieneu`.
- Ảnh hưởng: Nếu voice id trùng hoặc từng được store sai engine, pipeline có thể dùng clip từ engine khác với giọng/timbre khác nhưng vẫn gắn `rate_applied="cached"`. Người dùng nghe thấy giọng không nhất quán giữa các câu.
- Đề xuất: Không fallback sang engine khác trừ khi có alias mapping có kiểm soát và test chứng minh hai engine tạo cùng voice identity. Key cũng nên bao gồm các tham số engine ảnh hưởng âm sắc.

### [MEDIUM] URL auto-resume test chưa chứng minh pipeline behavior end-to-end

- Vị trí: `tests/test_url_resume.py:112`
- Bằng chứng: Test `test_auto_resume_existing_project` chỉ gọi `find_existing_project_by_url` và kiểm tra default `force_new`; nó không gọi `DubPipeline.run`, không mock các stage, không assert `last_work_dir`, không assert không tạo thư mục timestamp mới, không assert ASR/Dịch/TTS không bị gọi.
- Ảnh hưởng: Requirement chính của `BUG-URL-RESTART` có thể regress mà test vẫn pass.
- Đề xuất: Thêm test pipeline-level với project giả có source metadata + cached stage outputs, mock các stage đắt tiền, gọi `DubPipeline.run(DubRequest(url=..., output_dir=...))`, assert `last_work_dir == existing_proj` và các expensive mocks không gọi.

### [LOW] Fingerprint comment overstated về collision/tamper detection

- Vị trí: `autodub/pipeline_cache.py:37`
- Bằng chứng: Large-file fingerprint hash size + five sampled 64KB chunks, không hash toàn bộ file.
- Ảnh hưởng: Đây là trade-off hợp lý cho performance, nhưng comment nói “reliable tamper detection and collision resistance” quá mạnh. File khác cùng size và cùng sample windows vẫn collision theo implementation.
- Đề xuất: Đổi comment thành “fast probabilistic fingerprint” hoặc thêm mode full-hash cho artifact cần strict correctness.

## Test Review

Đã chạy:

```text
python -m pytest tests/test_url_resume.py tests/test_pipeline_cache.py tests/test_pipeline_cache_orchestrator.py tests/test_incremental_pipeline_cache.py tests/test_perf_optimizations.py -q
29 passed, 1 warning in 2.24s
```

Kết quả pass nhưng coverage chưa bắt các lỗi invalidation ở trên. Thiếu test thay đổi setting rồi resume, test OCR cache hit/miss, test translation context mismatch, test TTS cross-engine mismatch.

## Regression Review

Rủi ro regression cao ở các luồng resume/chỉnh sửa lại project:

- Bật/tắt OCR hoặc thay đổi hardsub config.
- Đổi style/glossary/domain dịch.
- Đổi mix/render settings trước export.
- Đổi engine/voice TTS.

Các nhánh này đều có khả năng trả artifact cũ mà không báo lỗi.

## Security Review

Không thấy lỗi security trực tiếp như injection/secret exposure trong phạm vi cache. Tuy nhiên cache toàn cục lưu transcript/dịch/TTS plaintext dưới `%LOCALAPPDATA%`; nếu dữ liệu người dùng nhạy cảm, cần quyết định sản phẩm rõ ràng về privacy, cleanup và opt-out.

## Scope Review

Phạm vi diff khá rộng so với hai bug/perf mục tiêu. Ngoài pipeline/cache còn có thay đổi ASR alignment/model preloader/subtitle/render GUI. Cần chia review theo task nếu muốn PASS từng unit.

## Kết luận

`FAIL`

Không có CRITICAL, nhưng có nhiều HIGH correctness regressions do cache/output invalidation chưa đủ chặt. Chỉ nên sửa trong phạm vi pipeline cache/reuse hiện tại, sau đó review lại với test chứng minh các setting mismatch không bị reuse sai.
