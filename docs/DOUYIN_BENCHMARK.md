# Douyin Video Extraction & Download Subsystem Benchmark Report

> Tài liệu tổng hợp kết quả đo đạc thực tế, phân tích cơ chế anti-bot và thông số kỹ thuật media khi trích xuất video từ nền tảng Douyin 2026.

---

## 1. Thông Tin Mẫu Thực Nghiệm

- **URL mục tiêu**: `https://www.douyin.com/jingxuan?modal_id=7681436015344853669`
- **Video ID**: `7681436015344853669`
- **Tác giả / Kênh**: `@游苏（射手教学）`
- **Tiêu đề gốc**: `2277分守约教学！枪枪爆头 好运连连！我是狙击手游苏！@游苏`
- **Thời điểm đo kiểm**: 2026-09-06 18:48:26 (UTC+7)
- **Tệp kết quả xác thực**: `.artifacts/benchmarks/douyin_7681436015344853669.mp4`

---

## 2. Kết Quả Đo Đạc Hiệu Năng (Measured Performance Metrics)

Tất cả các số liệu dưới đây được đo lường trực tiếp thông qua luồng streaming thật từ CDN Douyin:

| Tiêu chí | Giá trị thực tế | Đơn vị | Ghi chú |
| :--- | :--- | :--- | :--- |
| **Kích thước tệp (File Size)** | **379,885,828** | Bytes | **362.29 MB** |
| **Thời lượng phát (Duration)** | **663.60** | Giây | **11.06 phút** (~11:04) |
| **Thời gian tải xuống (Wall Time)** | **29.61** | Giây | Single connection streaming chunk 256KB |
| **Tốc độ tải trung bình (Throughput)** | **12.23** | MB/s | **97.87 Mbps** |
| **Cụm CDN phục vụ** | `v5-dy-ov-experiment.zjcdn.com` | Host | Cụm máy chủ CDN chính thức của ByteDance |
| **Mã trạng thái phản hồi** | `HTTP 200 OK` | Code | Progressive MP4 Stream |

---

## 3. Thông Số Kỹ Thuật Media (FFprobe Analysis)

Kiểm tra toàn vẹn container và codec bằng `ffprobe` và `MediaValidator`:

```json
{
  "format": {
    "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
    "duration": "663.600000",
    "size": "379885828",
    "bit_rate": "4579700"
  },
  "video_stream": {
    "codec_name": "h264",
    "profile": "High",
    "width": 1920,
    "height": 1080,
    "r_frame_rate": "30/1",
    "pix_fmt": "yuv420p"
  },
  "audio_stream": {
    "codec_name": "aac",
    "channels": 2,
    "sample_rate": "44100",
    "duration": "663.600000"
  }
}
```

- **Video Stream**: Chuẩn nén H.264 / AVC High Profile, độ phân giải **1920x1080** (Full HD), 30 fps, không watermark.
- **Audio Stream**: Chuẩn nén AAC stereo 44.1 kHz, đồng bộ hoàn hảo với video stream.
- **MediaValidator Status**: `PASS` (Không có hiện tượng lệch audio/video, không lỗi container).

---

## 4. Phân Tích Kỹ Thuật & Giải Pháp Tích Hợp Vào Engine

### 4.1. Thay đổi cấu trúc từ phía Douyin (2026)
1. **Endpoint `iteminfo` cũ**: `https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?item_ids={id}` đã bị vô hiệu hoá hoàn toàn (trả về 200 OK với content rỗng).
2. **Mobile Share Page**: `_ROUTER_DATA` trên trang `share/video/{id}` không còn kết xuất dữ liệu tĩnh `videoInfoRes` nếu thiếu token và client hydration.
3. **Anti-bot Desktop URL**: Đường dẫn desktop `/video/{id}` trực tiếp kích hoạt dialog đăng nhập cưỡng bức và báo lỗi kết nối máy chủ.
4. **Modal URL Preservation**: Đường dẫn `/jingxuan?modal_id={id}` cho phép giao diện nền nạp video vào DOM ngay cả khi dialog đăng nhập xuất hiện.

### 4.2. Cải tiến đã tích hợp vào Codebase
1. **Regex Host CDN mở rộng (`_CDN_HOST_RE`)**:
   - Bổ sung `zjcdn.com`, `douyincdn.com`, `bytecdntp.com`.
   - Ngăn chặn triệt để tình trạng bỏ sót các luồng Full HD từ cụm CDN `*.zjcdn.com`.
2. **Cơ chế BrowserPool Fallback thông minh**:
   - Khi gặp URL Douyin, engine thử tuần tự các định dạng route: Original URL -> Canonical URL -> `/jingxuan?modal_id={id}` -> `/discover?modal_id={id}`.
   - Tự động đóng modal đăng nhập và kích hoạt phát video.
   - Thăm dò trực tiếp thuộc tính `currentSrc` của thẻ `<video>` trong DOM để bắt URL stream ngay lập tức.
3. **Đồng bộ Singleton BrowserPool**:
   - Tránh việc gọi `sync_playwright()` trực tiếp trên thread đang có asyncio loop, ngăn chặn lỗi runtime `Playwright Sync API inside the asyncio loop`.
