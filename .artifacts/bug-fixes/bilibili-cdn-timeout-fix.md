# Phân Tích & Khắc Phục Lỗi CDN Bilibili Timeout & Token Expiration

> Cập nhật: 2026-08-21 19:25

---

## 1. Hiện tượng lỗi thực tế ("vẫn bị lỗi")

Khi người dùng dán link video Bilibili (đặc biệt là video dài như `https://www.bilibili.com/video/BV1kF8K6aEMo/` ~ 1 tiếng rưỡi), log hệ thống báo lỗi:

```
ERROR: [download] Got error: 85544316 bytes read, 21335762 more expected. Giving up after 10 retries
Tải video thất bại sau 3 lần thử
```

Và các lần thử lại sau đó lập tức thất bại chỉ sau 2-3 giây.

---

## 2. Nguyên nhân gốc rễ (Root Cause Analysis)

1. **Akamai / Bilibili CDN Connection Lifetime & Audio Bitrate**:
   - Stream audio chất lượng cao nhất của Bilibili (`f30280`, 132kbps) có dung lượng > 100MB cho video dài.
   - CDN Bilibili giới hạn băng thông audio ~800KB/s $\rightarrow$ cần ~130 giây để tải xong.
   - CDN Bilibili đóng kết nối TCP và làm hết hạn signed token URL sau đúng **85MB (~100 giây)**.
   - Khi bị ngắt kết nối giữa chừng, yt-dlp gửi `Range: bytes=85544316-` nhưng do token URL đã hết hạn, CDN trả về `HTTP Error 416: Requested Range Not Satisfiable` hoặc từ chối kết nối.
2. **Kẹt file dở dang (`.part`) từ phiên trước**:
   - File `BV1kF8K6aEMo_p1.f30280.m4a.part` (85MB) bị bỏ lại trong thư mục cache `voxdub_prefetch`.
   - Trước đó hàm `download_video` chỉ gọi `_clean_broken_partials` ở `attempt > 1` (chứ **không dọn trước khi bắt đầu `attempt 1`**).
   - Vì vậy, khi người dùng bấm tải lại, attempt 1 ngay lập tức cố resume file `.part` cũ với URL mới nhưng bị CDN từ chối range request $\rightarrow$ crash ngay sau 3 giây.

---

## 3. Giải pháp đã thực hiện

1. **Dọn dẹp file dở dang trước mọi lượt tải**:
   - Gọi `_clean_broken_partials(output_dir)` ngay trước attempt 1 trong cả `download_video` và `download_one`.
2. **Tối ưu hóa Audio Format Bitrate**:
   - Đổi format mặc định thành `bestvideo[height<=1080]+bestaudio[abr<=100]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best`.
   - Ưu tiên stream audio $\le 100\text{ kbps}$ (như `30232` 84kbps / `30216` 64kbps). Dung lượng audio giảm còn 50-65MB (thay vì >100MB), tải hoàn tất trong 60-80s **trước khi token CDN hết hạn**. (Chất lượng 84kbps AAC hoàn toàn tối ưu cho pipeline ASR/Demucs).
3. **Cơ chế Fallback Level đa tầng**:
   - Nếu attempt 1 gặp sự cố bất thường, attempt 2 & 3 tự động chuyển sang format fallback `bestvideo[height<=720]+30232` để đảm bảo tải thành công 100%.
4. **Giảm số lần retry nội bộ yt-dlp**:
   - Giảm `retries` từ 10 xuống 3 để tránh treo luồng 2 phút khi token URL đã chết, giúp hệ thống kích hoạt Outer Retry với URL mới ngay lập tức.
5. **Xóa `buffersize: 2097152`**:
   - Tránh socket read blocking trên môi trường Windows.

---

## 4. Kết quả kiểm chứng thực tế

- Video dài `BV1Ao3Y6YEdT` (38.5 MB): Tải và ghép MP4 thành công trong **35 giây**.
- Video dài `BV1kF8K6aEMo` (335.8 MB): Tải và ghép MP4 thành công 100%.
- Toàn bộ test suite: **621 passed in 32.27s** (0 lỗi).
