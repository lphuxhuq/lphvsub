# Social Automation Design Spec

> **Feature Group 4:** Tự động hóa & Phân phối Đa nền tảng (Auto High-CTR Thumbnail, Batch Queue Manager, Social Publishing Package)
> **Author:** Antigravity AI
> **Date:** 2026-08-29
> **Status:** Draft -> Approved for Implementation Plan

---

## 1. Mục tiêu (Goals)

Cung cấp trọn bộ công cụ tự động hóa từ khâu sản xuất hàng loạt đến khâu xuất bản nội dung lên các nền tảng mạng xã hội (YouTube, TikTok, Facebook):

1. **Auto High-CTR Thumbnail Generator (`autodub/media/thumbnail.py`)**:
   - Tự động quét chọn khung hình đẹp/ấn tượng nhất trong video.
   - Thiết kế và render đồ họa ảnh bìa (Thumbnail) chất lượng cao với tiêu đề giật tít tiếng Việt, viền tương phản (Stroke + Shadow + Banner) chuẩn phong cách thu hút lượt click ($16:9$ và $9:16$).
2. **Gói Xuất bản Đa nền tảng (Social Publishing Package & 1-Click Copy)**:
   - Đóng gói chuẩn thư mục `publish/` gồm video xuất hoàn thiện, thumbnail $16:9$, thumbnail $9:16$, và các tệp văn bản đăng bài tối ưu riêng cho từng nền tảng (YouTube, TikTok, Facebook).
   - Nút sao chép 1-chạm (1-Click Copy) tiêu đề, mô tả, hashtag trực tiếp trên giao diện Editor.
3. **Quản lý hàng đợi hàng loạt (Batch Queue Enhancements)**:
   - Hỗ trợ xếp hàng 10-50 video/liên kết, tự động chạy liên tục qua đêm, cơ chế thử lại khi mất mạng và báo cáo tổng kết chi tiết.

---

## 2. Thiết kế Kỹ thuật (Technical Design)

### 2.1. Bộ tạo Thumbnail Tự Động (`autodub/media/thumbnail.py`)
- **Thuật toán chọn Frame**:
  - Trích xuất frame tại các mốc thời gian $15\%$, $30\%$, $50\%$ của video qua FFmpeg.
  - Phân tích và chọn frame có độ rõ nét / màu sắc tốt nhất.
- **Vẽ Typography & Bố cục Thumbnail**:
  - Sử dụng Pillow (`PIL.Image`, `PIL.ImageDraw`, `PIL.ImageFont`) với font chữ Việt hóa từ `fonts/`.
  - Tự động bẻ dòng chữ ngắn gọn ($3-7$ chữ mỗi dòng, tối đa 2 dòng lớn).
  - Áp dụng dải màu gradient banner phía dưới chữ + viền chữ dày (Stroke width 4-8px) + bóng đổ (Drop shadow) để chữ luôn nổi bật trên bất kỳ nền video nào.
  - Lưu ảnh `thumbnail_landscape.jpg` ($1280\times 720$) và `thumbnail_portrait.jpg` ($720\times 1280$).

### 2.2. Gói Xuất bản Đa nền tảng (`autodub/content/generator.py`)
- Khi kết thúc pipeline, sinh thư mục `publish/` chứa:
  - `publish/video.mp4` (symbolic link hoặc copy)
  - `publish/thumbnail.jpg`
  - `publish/youtube_metadata.json`
  - `publish/youtube_post.txt`
  - `publish/tiktok_post.txt`
  - `publish/facebook_post.txt`

### 2.3. Tích hợp Giao diện Người dùng (GUI)
- **Editor Export / Result Tab**: Thêm widget xem trước Thumbnail + các nút sao chép nhanh:
  - `📋 Copy Tiêu đề YouTube`
  - `📋 Copy Mô tả & Tag`
  - `📋 Copy Caption TikTok`
  - `🖼️ Mở thư mục Thumbnail`
- **Batch Page**: Nâng cấp thanh tiến trình tổng thể và danh sách hàng đợi mượt mà.
