# Code Review — BUG-BILIBILI-DOWNLOAD

> Nhiệm vụ: Sửa lỗi không tải được video Bilibili  
> Ngày: 2026-08-21 · Trạng thái: **PASS**

---

## 1. Phạm vi review

Các file đã thay đổi trong đợt sửa lỗi này:
1. [`autodub/media/downloader.py`](file:///d:/Project/lphvsub-main/autodub/media/downloader.py):
   - Chuẩn hóa URL, bóc tách link sạch từ văn bản chia sẻ tiếng Trung.
   - Giải mã redirect link rút gọn `b23.tv` $\rightarrow$ `bilibili.com/video/BV...`.
   - Lọc bỏ tham số tracking của Bilibili (`spm_id_from`, `vd_source`...), giữ tham số phân tập `p`.
   - Cấu hình `http_headers` (`User-Agent`, `Referer: https://www.bilibili.com/`) cho yt-dlp để chống CDN bóp tốc độ / ngắt TCP.
   - Sửa lỗi truyền `clean_url` vào `normalize_url` trong `download_video` & `download_one`.
   - Xử lý trường hợp video nhiều phần (`_p1`) và generator `entries` an toàn trong `_resolve_filepath`.
2. [`autodub_gui/pages/batch_page.py`](file:///d:/Project/lphvsub-main/autodub_gui/pages/batch_page.py):
   - Sử dụng `extract_clean_url` khi thêm liên kết đơn và nạp danh sách từ file text.
3. [`tests/test_bilibili_downloader.py`](file:///d:/Project/lphvsub-main/tests/test_bilibili_downloader.py):
   - 7 unit test kiểm thử toàn diện các trường hợp Bilibili và hồi quy.

---

## 2. Requirement Compliance

| Tiêu chí chấp nhận | Hiện trạng | Đánh giá |
|--------------------|------------|----------|
| Tải được link Bilibili tiêu chuẩn (`bilibili.com/video/BV...`) | Đã kiểm chứng tải video thật thành công với định dạng tốt nhất (video + audio ghép MP4) | **ĐẠT** |
| Tải được văn bản chia sẻ từ app Bilibili có chứa tiêu đề chữ Hán | `normalize_url` và `extract_clean_url` tự động bóc tách link sạch | **ĐẠT** |
| Hỗ trợ link rút gọn `b23.tv` | `_resolve_b23_shortlink` tự động follow 302 redirect lấy link video đích | **ĐẠT** |
| Hỗ trợ video nhiều phần (Anthology / 分P) | Nhận diện đúng file `_p1.mp4` và metadata của tập | **ĐẠT** |
| Tải hàng loạt (Batch) nhận diện link Bilibili | `batch_page.py` dùng `extract_clean_url` cho cả nhập tay và file txt | **ĐẠT** |

---

## 3. Design Compliance

- Đúng 100% theo bản thiết kế [`.artifacts/bug-fixes/bilibili-download-fix-design.md`](file:///d:/Project/lphvsub-main/.artifacts/bug-fixes/bilibili-download-fix-design.md) đã được duyệt.
- Không thêm thư viện ngoại lai ngoài `requests` và `yt_dlp` đã có sẵn trong project.

---

## 4. Findings

Không phát hiện lỗi ở các mức `CRITICAL`, `HIGH`, `MEDIUM`.

- **[INFO] Timeout khi resolve `b23.tv`**:
  - Vị trí: `autodub/media/downloader.py:L48`
  - Đã có `timeout=8.0` và khối `try-except` bắt lỗi fallback về URL gốc nếu mất mạng.

---

## 5. Test Review

- File test mới: [`tests/test_bilibili_downloader.py`](file:///d:/Project/lphvsub-main/tests/test_bilibili_downloader.py)
- Kết quả chạy test riêng: `7 passed in 0.40s`
- Kiểm thử các ca biên:
  - Chuỗi text tiếng Trung chứa URL $\rightarrow$ pass.
  - URL Bilibili kèm tracking query parameters $\rightarrow$ pass.
  - Douyin modal URL $\rightarrow$ pass (không ảnh hưởng tính năng cũ).
  - YouTube URL $\rightarrow$ pass.
  - HTTP headers cấu hình $\rightarrow$ pass.
  - Filepath resolution cho video phân tập $\rightarrow$ pass.

---

## 6. Regression Review

- Đã chạy toàn bộ bộ test của dự án: `py -m pytest -q`
- Kết quả: **621 passed in 35.93s** (100% pass, không có bất kỳ test nào bị hỏng).

---

## 7. Security Review

- Không lưu trữ hoặc để lộ secret, API key hay token.
- Không sử dụng `eval` hoặc deserialization không an toàn.
- `urlparse` và `extract_clean_url` kiểm soát chặt chẽ scheme HTTP/HTTPS, ngăn ngừa injection.

---

## 8. Scope Review

- Chỉ sửa đúng 2 file mã nguồn (`downloader.py`, `batch_page.py`) và thêm 1 file test (`test_bilibili_downloader.py`).
- Không sửa lan ra các module không liên quan.

---

## 9. Kết luận

`KẾT LUẬN: PASS`
