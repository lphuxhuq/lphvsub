# Phân tích yêu cầu — AI Multi-Speaker Smart Voice Director

## 1. Mục tiêu
Tự động nhận diện giới tính/độ tuổi/vai trò của từng người nói (Speaker) trong video dựa trên cao độ âm thanh (F0/Pitch) và ngữ cảnh thoại, tự động phân vai và ghép bộ giọng VieNeu hoặc CapCut tương ứng cho từng nhân vật (Auto Voice Casting), hỗ trợ cả hai hệ thống TTS (VieNeu & CapCut), đồng thời cung cấp tuỳ chọn Bật/Tắt và bảng điều khiển trực quan 1-Click trên GUI để người dùng dễ dàng quản lý giọng của từng nhân vật.

---

## 2. User Story
- **Là một người làm video drama/phim ngắn/talkshow**, tôi muốn khi đưa video có 2-4 nhân vật nam và nữ vào hệ thống, AI sẽ tự động phân tích và gán giọng Nam cho nhân vật nam, giọng Nữ cho nhân vật nữ, giọng Dẫn chuyện cho người thuyết minh (hỗ trợ cả bộ giọng VieNeu offline và CapCut online) mà tôi không cần phải chỉnh tay từng câu.
- **Là một biên tập viên video**, tôi muốn có nút gạt Bật/Tắt tính năng tự động phân vai (để có thể chọn dùng 1 giọng truyền thống hoặc đa giọng tự động) và một bảng "Quản lý nhân vật & Phân vai" trên giao diện để có thể đổi giọng cho toàn bộ các câu của một nhân vật chỉ bằng 1 thao tác và nghe thử nhanh.

---

## 3. Functional Requirements

### FR-01: Bộ phân tích đặc trưng người nói (Speaker Acoustic & Pitch Profiler)
- Trích xuất cao độ âm thanh cơ bản ($F_0$) và phân bố tần số giọng nói trên các segment của từng `speaker_id`.
- Phân loại đặc tính âm học:
  - `deep_male` ($F_0 < 135\text{ Hz}$)
  - `young_male` ($135\text{ Hz} \le F_0 < 175\text{ Hz}$)
  - `female` ($175\text{ Hz} \le F_0 < 255\text{ Hz}$)
  - `child_or_high` ($F_0 \ge 255\text{ Hz}$)
- Nhận diện vai trò dẫn chuyện (`narrator`): Người nói chiếm tỷ lượng thời lượng lớn nhất (>35%) hoặc phân bố đều xuyên suốt video.

### FR-02: Bộ đạo diễn ghép giọng thông minh (Smart Voice Auto-Casting Engine)
- Dựa trên profile của từng `speaker_id` và kho giọng của engine đang dùng (VieNeu hoặc CapCut):
  - Tự động gán các giọng khác nhau (distinct voices) cho các `speaker_id` khác nhau để tránh trùng lặp.
  - Khớp giới tính và sắc thái (Nam $\rightarrow$ giọng Nam, Nữ $\rightarrow$ giọng Nữ, Dẫn chuyện $\rightarrow$ giọng truyền cảm/tin tức).
  - Hỗ trợ kho giọng **VieNeu** (offline) và kho giọng **CapCut** (online TTS).
  - Ghi nhận `speaker_voices` vào `render_opts.json` và cấu hình dự án.

### FR-03: Tuỳ chọn Bật/Tắt linh hoạt (On/Off Toggle)
- Thêm setting `auto_voice_director_enabled` (mặc định: `True` hoặc cấu hình qua GUI/env).
- Khi Tắt (`auto_voice_director_enabled = False`): Toàn bộ video sử dụng 1 giọng đọc mặc định của dự án như truyền thống.
- Khi Bật: Tự động chạy profiler và gán giọng đa nhân vật.

### FR-04: Tích hợp vào Pipeline (Step 3.6 Diarization $\rightarrow$ Step 5 TTS)
- Khi `diarization_enabled=True` và `auto_voice_director_enabled=True`:
  - Sau khi cụm người nói xong, pipeline tự động chạy `profile_speakers()` và `auto_cast_voices()`.
  - Bước sinh TTS (Step 5) tự động sử dụng giọng tương ứng theo từng `speaker_id` của từng câu thoại (hỗ trợ cả VieNeu synth và CapCut synth).

### FR-05: Bảng điều khiển Nhân vật trên GUI (Character & Voice Director Panel)
- Hiển thị danh sách các nhân vật được phát hiện trong video:
  - Checkbox / Toggle bật tắt tính năng Auto Voice Director ngay trên giao diện.
  - Tên nhân vật (VD: *Người nói 1 (Nam trầm)*, *Người nói 2 (Nữ)*).
  - Số lượng câu thoại & tổng thời lượng nói.
  - Dropdown chọn giọng (VieNeu / CapCut) kèm nút Nghe thử (Preview).
  - Đổi giọng trên dropdown sẽ tự động cập nhật cho tất cả các câu thuộc `speaker_id` đó.

---

## 4. Non-functional Requirements
- **NFR-01 (Hiệu năng):** Quá trình phân tích F0/Pitch chạy trên CPU cực nhanh ($< 1.0\text{s}$ cho video 5 phút).
- **NFR-02 (Độc lập & An toàn):** Không cài thêm thư viện nặng; sử dụng `scipy.signal` / `numpy` (đã có sẵn trong môi trường).
- **NFR-03 (Fallback an toàn):** Nếu video chỉ có 1 người nói hoặc phân tích âm học không đủ dữ liệu, tự động fallback về giọng mặc định của dự án mà không gây lỗi.
- **NFR-04 (Tương thích ngược):** Dự án cũ không có diarization hoặc chỉ dùng 1 giọng vẫn hoạt động bình thường 100%.

---

## 5. Module bị ảnh hưởng
1. `autodub/speech/speaker_profiler.py` [NEW]: Module phân tích cao độ F0, giới tính và vai trò nhân vật.
2. `autodub/speech/voice_director.py` [NEW]: Module thuật toán Auto Voice Casting ghép giọng VieNeu & CapCut.
3. `autodub/pipeline.py` [MODIFY]: Nối luồng Auto Voice Director giữa Step 3.6 và Step 5.
4. `autodub/config.py` [MODIFY]: Cấu hình `auto_voice_director_enabled: bool = True`.
5. `autodub_gui/pages/editor_panels.py` / `autodub_gui/pages/editor_page.py` [MODIFY]: Bổ sung giao diện Quản lý nhân vật & Phân vai.

---

## 6. Acceptance Criteria

| ID | Tiêu chí nghiệm thu | Phương pháp kiểm thử |
|---|---|---|
| **AC-01** | Đo F0 phân loại chính xác mẫu âm thanh Nam ($<160\text{Hz}$) và Nữ ($>180\text{Hz}$) | Unit test với synthetic tone & voice samples |
| **AC-02** | Auto-Casting gán đúng giọng Nam cho speaker Nam, giọng Nữ cho speaker Nữ cho cả VieNeu và CapCut | Unit test ma trận ghép giọng đa nhân vật |
| **AC-03** | Các nhân vật cùng giới tính được ưu tiên gán các voice ID khác nhau | Unit test phân bổ giọng không trùng lặp |
| **AC-04** | Khi `auto_voice_director_enabled=False`, toàn bộ video dùng 1 giọng mặc định | Unit test kiểm tra toggle bật/tắt |
| **AC-05** | Pipeline tự động tổng hợp TTS đa giọng khi video có nhiều speaker | Integration test pipeline TTS multi-speaker |
| **AC-06** | Fallback về 1 giọng gốc khi audio đơn âm hoặc tắt tính năng | Unit test fallback |

---

## 7. Ngoài phạm vi (Out of scope)
- Voice Cloning trực tiếp từ giọng gốc diễn viên nước ngoài.

---

`TRẠNG THÁI: CHỜ DUYỆT PHÂN TÍCH`
