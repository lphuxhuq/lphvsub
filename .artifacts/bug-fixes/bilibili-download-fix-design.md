# Fix Design: Sửa lỗi không tải được video Bilibili

> Mã lỗi: `BUG-BILIBILI-DOWNLOAD` · Ngày: 2026-08-21  
> Trạng thái: **CHỜ DUYỆT CÁCH SỬA**

---

## 1. Mục tiêu và Phạm vi sửa đổi

- **Mục tiêu**: Đảm bảo ứng dụng tải thành công 100% các định dạng video Bilibili (link trực tiếp, link rút gọn `b23.tv`, văn bản sao chép kèm chữ từ mobile app, video nhiều tập `_p1`, video chất lượng cao).
- **Phạm vi file thay đổi**:
  1. `autodub/media/downloader.py` (Lõi xử lý tải & chuẩn hóa URL)
  2. `autodub_gui/pages/batch_page.py` (Cho phép nhận link có kèm văn bản chia sẻ khi thêm hàng loạt)
  3. `tests/test_bilibili_downloader.py` (Bộ unit test kiểm thử toàn diện)

---

## 2. Thiết kế logic chi tiết

### 2.1 Chuẩn hóa URL (`autodub/media/downloader.py`)

Cải tiến hàm `normalize_url(url: str) -> str` và bổ sung xử lý riêng cho Bilibili:

1. **Làm sạch chuỗi đầu vào**:
   - Sử dụng `extract_clean_url(url)` trước tiên để tách URL hợp lệ ra khỏi văn bản chia sẻ chứa tiêu đề tiếng Trung.
2. **Phân giải link rút gọn `b23.tv`**:
   - Nếu domain là `b23.tv`, thực hiện follow 302 redirect bằng `requests.head` / `requests.get` với `User-Agent` và `Referer: https://www.bilibili.com/` để lấy URL đích `https://www.bilibili.com/video/BV...`.
3. **Lọc sạch tham số rác (Tracking query params)**:
   - Xóa bỏ các query params tracking của Bilibili: `spm_id_from`, `vd_source`, `share_source`, `from_spmid`, `buvid`, `mid`, `bvid` trùng lặp.
   - **Giữ lại** tham số phân tập quan trọng như `?p=...` nếu có.
4. **Giữ nguyên tính tương thích**:
   - Duy trì logic chuẩn hóa Douyin (`modal_id` $\rightarrow$ `/video/<id>`) và các domain khác.

### 2.2 Tối ưu cấu hình yt-dlp (`_get_optimized_opts`)

1. **Thêm HTTP Headers bắt buộc cho Bilibili CDN**:
   - Thêm `http_headers`:
     ```python
     "http_headers": {
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
         "Referer": "https://www.bilibili.com/",
     }
     ```
   - Giúp CDN không ngắt kết nối giữa chừng, không bị 403 Forbidden và giữ tốc độ tải tối đa.
2. **Loại bỏ `extractor_args` không hợp lệ**:
   - Bỏ `"extractor_args": {"bilibili": {"playback": "dash"}}` (không có trong yt-dlp schema).
3. **Duy trì định dạng**:
   - `bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best[ext=mp4]/best` kết hợp `merge_output_format: mp4`.

### 2.3 Sửa luồng tải & giải quyết tên file (`download_video` & `download_one`)

1. **Sửa biến gọi `normalize_url`**:
   ```python
   clean_url = extract_clean_url(url)
   if is_douyin_url(clean_url):
       ...
   canonical = normalize_url(clean_url)  # Đã sửa: truyền clean_url thay vì url gốc
   ```
2. **Xử lý an toàn `entries` generator**:
   - Trích xuất thông tin video từ `info["entries"]` nếu có, đảm bảo lấy đúng `id`, `title`, `uploader` của tập được tải (`_p1`).
3. **Tìm file thông minh (`_resolve_filepath` & `download_video`)**:
   - Tìm file theo `video_id`. Nếu không thấy, tìm file có tiền tố `video_id` (ví dụ `BVxxxx_p1.mp4`) hoặc `f"{extractor}_{video_id}"`.

### 2.4 Cải thiện nhập liệu tại GUI (`autodub_gui/pages/batch_page.py`)

- Trong `_add_link` và `_import_list`: áp dụng `extract_clean_url(line)` để khi người dùng dán cả đoạn văn bản chia sẻ từ app Bilibili/Douyin, hệ thống tự động bóc tách link sạch mà không báo lỗi `Liên kết phải bắt đầu bằng http://...`.

---

## 3. Kế hoạch kiểm thử (Test Plan)

Tạo file test mới `tests/test_bilibili_downloader.py` bao gồm:
1. `test_extract_clean_url_bilibili`: Kiểm tra bóc tách URL Bilibili từ chuỗi văn bản chia sẻ có tiếng Trung.
2. `test_normalize_url_bilibili_params`: Kiểm tra lọc bỏ tracking params (`spm_id_from`, `vd_source`) nhưng giữ lại `p=2`.
3. `test_normalize_url_douyin_preserved`: Đảm bảo chức năng Douyin modal ID không bị ảnh hưởng.
4. `test_bilibili_opts_headers`: Kiểm tra `_get_optimized_opts` có đầy đủ `http_headers` chuẩn.
5. `test_resolve_filepath_multipart`: Kiểm tra tìm kiếm file khi có hậu tố `_p1` hoặc tiền tố extractor.
6. Chạy lại toàn bộ bộ test hiện tại (`pytest tests/`) để kiểm tra hồi quy.

---

## 4. Đánh giá rủi ro hồi quy (Regression Risks)

| Rủi ro | Mức độ | Biện pháp ngăn ngừa |
|--------|--------|---------------------|
| Ảnh hưởng tới tải YouTube/Douyin | Rất thấp | `extract_clean_url` và `normalize_url` giữ nguyên các quy tắc cho YouTube/Douyin. `http_headers` áp dụng an toàn cho mọi extractor. |
| Xung đột query params khi tải playlist YouTube | Không có | Chỉ lọc query params trên domain `bilibili.com` / `b23.tv`. |
| Chậm do resolve redirect `b23.tv` | Không đáng kể | Chỉ gọi `requests.head(..., timeout=5)` khi domain đúng là `b23.tv`. |

---

`TRẠNG THÁI: CHỜ DUYỆT CÁCH SỬA`
