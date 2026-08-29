"""Sinh nội dung đăng bài: tiêu đề, mô tả, hashtag cho từng nền tảng.

Mỗi dự án nhận hai nhóm tệp, mỗi tệp một việc:

- ``youtube_post.txt`` — nội dung đăng bài (YouTube, TikTok, Facebook).
- ``script_original.txt`` / ``script_vi.txt`` — lời thoại thuần chữ.

Phần chữ do máy chủ VoxDub viết (app không giữ API Key nào). Ảnh bìa AI đã bỏ
hẳn khỏi sản phẩm — ảnh bìa gốc của video vẫn được tải về làm tham chiếu nếu
người dùng muốn tự thiết kế.
"""
import json
import os
import re

import requests

from autodub.utils import setup_logging

logger = setup_logging("autodub.content_generator")


def _extract_video_id(url: str) -> str | None:
    """Lấy mã video YouTube từ một liên kết."""
    if not url:
        return None
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
        r"(?:shorts/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_original_thumbnail(url: str, output_dir: str) -> str | None:
    """Tải ảnh bìa gốc của video YouTube."""
    video_id = _extract_video_id(url)
    if not video_id:
        return None

    thumb_urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    ]
    for thumb_url in thumb_urls:
        try:
            resp = requests.get(thumb_url, timeout=10)
            if resp.status_code == 200 and len(resp.content) > 1000:
                path = os.path.join(output_dir, "thumbnail_original.jpg")
                with open(path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Đã tải ảnh bìa gốc: {path}")
                return path
        except requests.RequestException:
            continue
    return None


def extract_script_text(segments: list[dict], text_field: str,
                        output_path: str) -> str:
    """Rút lời thoại thuần chữ ra tệp .txt và trả về chính chuỗi đó."""
    lines = []
    for seg in segments:
        text = str(seg.get(text_field) or seg.get("text", "")).strip()
        if text:
            lines.append(text)
    script_text = " ".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(script_text)
    return script_text


# ------------------------------------------------------- nội dung đăng bài -- #

def generate_social_metadata_direct(
    script_original: str,
    script_translated: str,
    settings,
    video_title: str = "",
) -> dict:
    """Tạo tiêu đề, mô tả, hashtag trực tiếp bằng AI API Key (Gemini, DeepSeek, OpenAI, v.v.)."""
    if not settings:
        return {}

    from autodub.text.translate_direct import (
        get_direct_client, _slice_to_payload, _strip_fences_and_citations
    )

    try:
        client, provider_name = get_direct_client(settings)
    except Exception:
        return {}

    system_instruction = (
        "Bạn là chuyên gia sáng tạo nội dung mạng xã hội và tối ưu SEO video hàng đầu "
        "(YouTube, TikTok, Facebook Reels). Nhiệm vụ của bạn là đọc kịch bản video và tạo ra bộ "
        "tiêu đề, mô tả, hashtag hấp dẫn, kích thích lượt xem (CTR cao) nhưng không giật tít lừa đảo."
    )

    domain = getattr(settings, "translate_domain", "").strip()
    topic_context = f"\nChủ đề/Thể loại: {domain}" if domain else ""
    orig_title_context = f"\nTiêu đề gốc: {video_title}" if video_title else ""

    user_prompt = f"""Dựa vào nội dung kịch bản video tiếng Việt dưới đây:{orig_title_context}{topic_context}
Lời thoại video:
\"\"\"
{script_translated[:6000]}
\"\"\"

Hãy tạo gói nội dung đăng bài chuyên nghiệp, chuẩn SEO và tối ưu tương tác cho cả 3 nền tảng:
1. YouTube (Video / Shorts):
   - title: Tiêu đề tiếng Việt hấp dẫn, kích thích tò mò (khoảng 45-70 ký tự, có thể kèm emoji tinh tế hoặc từ khóa hot).
   - description: Mô tả chi tiết 3 phần: (1) Đoạn mở đầu hook 2 câu tóm tắt gay cấn; (2) Điểm nổi bật / bài học chính trong video; (3) Lời kêu gọi hành động (Đăng ký kênh, để lại bình luận).
   - hashtags: 10-15 hashtag chất lượng cao (gồm các từ khóa ngách cụ thể và hashtag thịnh hành, viết liền có dấu #).
2. TikTok:
   - title: Caption ngắn gọn (1-2 câu), giật gân, khơi gợi tranh luận hoặc tò mò ngay giây đầu.
   - hashtags: 5-8 hashtag thịnh hành (#fyp, #xuhuong, #viral + các hashtag chủ đề video).
3. Facebook (Reels / Video Post):
   - title: Caption tự nhiên, mang tính kết nối cộng đồng, đặt câu hỏi để người xem comment.
   - hashtags: 3-5 hashtag cô đọng (#reels, #trending + hashtag chủ đề).

Bắt buộc trả về đúng duy nhất định dạng JSON thuần túy sau:
{{
  "title": "Tiêu đề YouTube...",
  "description": "Nội dung mô tả YouTube...",
  "hashtags": ["#tag1", "#tag2", ...],
  "tiktok": {{
    "title": "Caption TikTok...",
    "hashtags": ["#fyp", "#xuhuong", ...]
  }},
  "facebook": {{
    "title": "Caption Facebook...",
    "hashtags": ["#reels", "#trending", ...]
  }}
}}
Chỉ trả về JSON thuần túy, không có lời dẫn hay giải thích thêm."""

    try:
        raw = client.call_ai(system_instruction, user_prompt)
        clean = _strip_fences_and_citations(raw)
        data = json.loads(_slice_to_payload(clean))
        if isinstance(data, dict) and "title" in data:
            logger.info(f"Đã tạo nội dung đăng bài qua {provider_name}: «{data.get('title', '')[:50]}»")
            return data
    except Exception as e:
        logger.warning(f"Tạo nội dung đăng bài qua {provider_name} lỗi ({e}) — bỏ qua")
    return {}


def generate_social_metadata_browser(
    script_original: str,
    script_translated: str,
    settings,
    video_title: str = "",
) -> dict:
    """Tạo tiêu đề, mô tả, hashtag trực tiếp bằng Google AI Studio (Playwright browser)."""
    if not settings or not getattr(settings, "ai_studio_enabled", False):
        return {}

    try:
        from autodub.text.translate_browser import AiStudioBrowserClient
        from autodub.text.translate_direct import _slice_to_payload, _strip_fences_and_citations

        domain = getattr(settings, "translate_domain", "").strip()
        topic_context = f"\nChủ đề/Thể loại: {domain}" if domain else ""
        orig_title_context = f"\nTiêu đề gốc: {video_title}" if video_title else ""

        user_prompt = f"""Dựa vào nội dung kịch bản video tiếng Việt dưới đây:{orig_title_context}{topic_context}
Lời thoại video:
\"\"\"
{script_translated[:6000]}
\"\"\"

Hãy tạo gói nội dung đăng bài chuyên nghiệp, chuẩn SEO và tối ưu tương tác cho cả 3 nền tảng:
1. YouTube (Video / Shorts):
   - title: Tiêu đề tiếng Việt hấp dẫn, kích thích tò mò (khoảng 45-70 ký tự).
   - description: Mô tả chi tiết 3 phần (hook 2 câu mở đầu, điểm nổi bật chính, kêu gọi Like/Đăng ký kênh).
   - hashtags: 10-15 hashtag chất lượng cao (#shorts, #phimhay, #review, #trending, #viral...).
2. TikTok:
   - title: Caption ngắn gọn (1-2 câu), giật gân, cuốn hút.
   - hashtags: 5-8 hashtag thịnh hành (#fyp, #xuhuong, #viral...).
3. Facebook (Reels / Post):
   - title: Caption tự nhiên, tăng tương tác và bình luận.
   - hashtags: 3-5 hashtag cô đọng (#reels, #trending...).

Bắt buộc trả về đúng DUY NHẤT định dạng JSON sau:
{{
  "title": "Tiêu đề YouTube...",
  "description": "Nội dung mô tả YouTube...",
  "hashtags": ["#tag1", "#tag2", ...],
  "tiktok": {{
    "title": "Caption TikTok...",
    "hashtags": ["#fyp", "#xuhuong", ...]
  }},
  "facebook": {{
    "title": "Caption Facebook...",
    "hashtags": ["#reels", "#trending", ...]
  }}
}}
Chỉ trả về JSON thuần túy, không có lời dẫn hay giải thích thêm."""

        headless = getattr(settings, "ai_studio_headless", False)
        profile_dir = getattr(settings, "ai_studio_chrome_profile", "")
        client = AiStudioBrowserClient(profile_dir=profile_dir, headless=headless)
        try:
            raw = client.translate_batch("", user_prompt, max_wait_secs=90)
            clean = _strip_fences_and_citations(raw)
            data = json.loads(_slice_to_payload(clean))
            if isinstance(data, dict) and "title" in data:
                logger.info(f"Đã tạo nội dung đăng bài qua Google AI Studio: «{data.get('title', '')[:50]}»")
                return data
        finally:
            client.close()
    except Exception as e:
        logger.warning(f"Tạo nội dung đăng bài qua Google AI Studio lỗi ({e}) — bỏ qua")
    return {}


def _generate_fallback_metadata(script_translated: str, video_title: str = "") -> dict:
    """Tạo metadata dự phòng tự nhiên dựa trên tiêu đề gốc và kịch bản khi không có AI."""
    title = video_title.strip() if video_title else ""
    if not title:
        first_line = script_translated.split(".")[0].strip()
        title = first_line[:60] if first_line else "Video Lồng Tiếng Mới Nhất"
    desc = f"{title}\n\nXem video trọn vẹn và đừng quên bấm Like & Đăng ký kênh để theo dõi những video hấp dẫn tiếp theo nhé!"
    tags = ["#shorts", "#review", "#phimhay", "#trending", "#viral", "#xuhuong"]
    return {
        "title": title,
        "description": desc,
        "hashtags": tags,
        "tiktok": {
            "title": f"{title} | Xem ngay!",
            "hashtags": ["#fyp", "#xuhuong", "#viral", "#shorts"]
        },
        "facebook": {
            "title": f"Mọi người thấy video này thế nào? Bình luận bên dưới nhé!\n{title}",
            "hashtags": ["#reels", "#trending", "#viral"]
        }
    }


def generate_social_metadata(script_original: str, script_translated: str,
                             video_title: str = "", job_id: str = "",
                             settings=None) -> dict:
    """Tạo tiêu đề, mô tả và hashtag tự động qua API Key trực tiếp, AI Studio hoặc máy chủ."""
    if settings:
        res = generate_social_metadata_direct(
            script_original, script_translated, settings, video_title=video_title
        )
        if res:
            return res

        if getattr(settings, "ai_studio_enabled", False):
            res_browser = generate_social_metadata_browser(
                script_original, script_translated, settings, video_title=video_title
            )
            if res_browser:
                return res_browser

    from autodub.saas_client import (
        InsufficientCreditError, SaasError, get_client, is_configured,
        new_job_id)
    from autodub.text.translate_common import HOLD

    if is_configured():
        try:
            metadata = get_client().generate_post(
                script_original, script_translated,
                job_id=job_id or new_job_id(), video_title=video_title,
                hold_id=HOLD.hold_id)
            if metadata:
                logger.info("Đã viết xong nội dung đăng bài qua server: "
                            f"«{str(metadata.get('title', ''))[:50]}»")
                return metadata
        except InsufficientCreditError:
            raise
        except SaasError as e:
            logger.error(f"Viết nội dung đăng bài lỗi ({str(e)[:120]})")

    # Dự phòng thông minh: luôn tạo metadata để youtube_post.txt không bao giờ bị rỗng
    return _generate_fallback_metadata(script_translated, video_title=video_title)


# ------------------------------------------------------------- ghi ra tệp -- #

def _write_post_file(path: str, meta: dict) -> None:
    """``youtube_post.txt`` — nội dung đăng bài cho ba nền tảng."""
    tiktok = meta.get("tiktok") or {}
    facebook = meta.get("facebook") or {}
    bar = "=" * 60

    def block(name: str, title: str, description: str,
              hashtags: list) -> list[str]:
        rows = [bar, name, bar, "", f"TIÊU ĐỀ:\n{title}", ""]
        if description:
            rows += [f"MÔ TẢ:\n{description}", ""]
        rows += [f"HASHTAG:\n{' '.join(hashtags or [])}", ""]
        return rows

    lines: list[str] = []
    lines += block("YOUTUBE", meta.get("title", ""),
                   meta.get("description", ""), meta.get("hashtags", []))
    lines += block("TIKTOK", tiktok.get("title", ""), "",
                   tiktok.get("hashtags", []))
    lines += block("FACEBOOK", facebook.get("title", ""), "",
                   facebook.get("hashtags", []))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def generate_content(
    segments: list[dict],
    source_url: str | None,
    output_dir: str,
    settings=None,
    video_path: str | None = None,
    video_title: str = "",
    job_id: str = "",
) -> dict:
    """Sinh phần nội dung đăng bài của một dự án (Metadata, Thumbnail High-CTR, Publishing Package)."""
    result: dict = {"metadata": {}, "metadata_file": None}

    script_original = extract_script_text(
        segments, "text", os.path.join(output_dir, "script_original.txt"))
    script_translated = extract_script_text(
        segments, "text_vi", os.path.join(output_dir, "script_vi.txt"))

    if source_url:
        fetch_original_thumbnail(source_url, output_dir)

    metadata_path = os.path.join(output_dir, "youtube_metadata.json")
    post_path = os.path.join(output_dir, "youtube_post.txt")

    meta: dict = {}
    # Nếu đã có metadata trích xuất từ trước (ví dụ từ bản dịch Google AI Studio):
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                saved_meta = json.load(f)
            if isinstance(saved_meta, dict) and saved_meta.get("title"):
                meta = saved_meta
                logger.info(f"Dùng lại tiêu đề, mô tả đã có: «{str(saved_meta.get('title'))[:50]}»")
        except Exception:
            pass

    if not meta or not meta.get("title"):
        meta = generate_social_metadata(
            script_original, script_translated, video_title=video_title,
            job_id=job_id, settings=settings)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    result["metadata"] = meta
    result["metadata_file"] = metadata_path

    _write_post_file(post_path, meta)
    result["post_file"] = post_path

    # Tự động sinh Thumbnail High-CTR (16:9 và 9:16) nếu có video_path
    if video_path and os.path.exists(video_path):
        from autodub.media.thumbnail import generate_high_ctr_thumbnail
        thumb_title = meta.get("title") or video_title or "VIDEO MỚI NHẤT"
        thumb_landscape = os.path.join(output_dir, "thumbnail_landscape.jpg")
        thumb_portrait = os.path.join(output_dir, "thumbnail_portrait.jpg")
        try:
            generate_high_ctr_thumbnail(video_path, thumb_title, thumb_landscape, aspect="16:9")
            result["thumbnail_landscape"] = thumb_landscape
            generate_high_ctr_thumbnail(video_path, thumb_title, thumb_portrait, aspect="9:16")
            result["thumbnail_portrait"] = thumb_portrait
        except Exception as e:
            logger.warning(f"Lỗi khi tự động tạo thumbnail: {e}")

    return result
