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

def _has_cjk(text: str) -> bool:
    """Kiểm tra chuỗi có chứa ký tự tiếng Trung/Nhật/Hàn hay không."""
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _clean_social_metadata(meta: dict, script_translated: str) -> dict:
    """Chuẩn hóa và lọc sạch 100% tiếng Trung trong metadata."""
    if not isinstance(meta, dict):
        meta = {}

    title = str(meta.get("title") or "").strip()
    if not title or _has_cjk(title):
        # Tự sinh tiêu đề tiếng Việt từ kịch bản dịch
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", script_translated) if s.strip()]
        first_line = sentences[0] if sentences else "Siêu Phẩm Video Lồng Tiếng Mới Nhất"
        title = first_line[:65]
        meta["title"] = title

    desc = str(meta.get("description") or "").strip()
    if not desc or _has_cjk(desc):
        desc = (
            f"{title}\n\n"
            f"Chào mừng bạn đến với video mới nhất! Hãy xem trọn vẹn video để không bỏ lỡ "
            f"những tình tiết gay cấn và hấp dẫn nhất nhé.\n\n"
            f"+ Đừng quên bấm LIKE, CHIA SẺ và ĐĂNG KÝ KÊNH để ủng hộ mình và đón xem "
            f"những tập tiếp theo sớm nhất!"
        )
        meta["description"] = desc

    # Xử lý alternative titles
    alt_titles = meta.get("alternative_titles")
    if not isinstance(alt_titles, list) or not alt_titles or any(_has_cjk(x) for x in alt_titles):
        meta["alternative_titles"] = [
            f"Bí Mật Đằng Sau: {title[:45]}",
            f"Sự Thật Bất Ngờ Trong {title[:45]}",
            f"Cái Kết Bất Ngờ Của {title[:45]}",
        ]

    # Xử lý tags
    tags = meta.get("tags")
    if not isinstance(tags, list) or not tags or any(_has_cjk(x) for x in tags):
        meta["tags"] = [
            "review phim", "lồng tiếng", "tóm tắt phim", "phim hay",
            "phim mới", "shorts", "xem phim", "viral video", "thịnh hành"
        ]

    # Xử lý hashtags
    hashtags = meta.get("hashtags")
    if not isinstance(hashtags, list) or not hashtags or any(_has_cjk(x) for x in hashtags):
        meta["hashtags"] = ["#shorts", "#reviewphim", "#phimhay", "#tomtatphim", "#trending", "#viral", "#xuhuong"]

    # Xử lý TikTok
    tiktok = meta.get("tiktok")
    if not isinstance(tiktok, dict):
        tiktok = {}
    tk_title = str(tiktok.get("title") or "").strip()
    if not tk_title or _has_cjk(tk_title):
        tiktok["title"] = f"{title[:60]} | Xem ngay để biết cái kết!"
    tk_tags = tiktok.get("hashtags")
    if not isinstance(tk_tags, list) or not tk_tags or any(_has_cjk(x) for x in tk_tags):
        tiktok["hashtags"] = ["#fyp", "#xuhuong", "#viral", "#shorts", "#phimhay", "#review"]
    meta["tiktok"] = tiktok

    # Xử lý Facebook
    facebook = meta.get("facebook")
    if not isinstance(facebook, dict):
        facebook = {}
    fb_title = str(facebook.get("title") or "").strip()
    if not fb_title or _has_cjk(fb_title):
        facebook["title"] = f"Mọi người đánh giá thế nào về diễn biến này? Để lại bình luận nhé!\n{title}"
    if not facebook.get("description") or _has_cjk(facebook.get("description", "")):
        facebook["description"] = "Cùng theo dõi và thảo luận những tình tiết gay cấn nhất trong video dưới đây."
    fb_tags = facebook.get("hashtags")
    if not isinstance(fb_tags, list) or not fb_tags or any(_has_cjk(x) for x in fb_tags):
        facebook["hashtags"] = ["#reels", "#trending", "#viral", "#phimhay", "#xuhuong"]
    meta["facebook"] = facebook

    return meta


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
        "tiêu đề, mô tả, hashtag và danh sách thẻ từ khóa (tags) hấp dẫn, kích thích lượt xem (High CTR) "
        "nhưng không giật tít lừa đảo.\n"
        "YÊU CẦU BẮT BUỘC:\n"
        "1. Toàn bộ nội dung trả về BẮT BUỘC 100% bằng TIẾNG VIỆT HOÀN TOÀN.\n"
        "2. TUYỆT ĐỐI KHÔNG để lại bất kỳ chữ Hán/tiếng Trung (CJK) nào trong tiêu đề, mô tả, thẻ tags hay hashtag."
    )

    domain = getattr(settings, "translate_domain", "").strip()
    topic_context = f"\nChủ đề/Thể loại: {domain}" if domain else ""
    clean_vtitle = re.sub(r"[\u4e00-\u9fff]+", "", video_title).strip()
    orig_title_context = f"\nTiêu đề tham khảo: {clean_vtitle}" if clean_vtitle else ""

    user_prompt = f"""Dựa vào nội dung kịch bản video tiếng Việt dưới đây:{orig_title_context}{topic_context}
Lời thoại video:
\"\"\"
{script_translated[:6000]}
\"\"\"

Hãy tạo gói nội dung đăng bài chuyên nghiệp, chuẩn SEO và tối ưu tương tác cho cả 3 nền tảng:
1. YouTube (Video / Shorts):
   - title: Tiêu đề tiếng Việt chính cực kỳ hấp dẫn, kích thích tò mò (khoảng 45-70 ký tự).
   - alternative_titles: 3 tiêu đề gợi ý khác nhau mang phong cách giật gân, tò mò, khám phá để A/B test.
   - description: Mô tả chi tiết 3 phần: (1) Đoạn mở đầu hook 2 câu tóm tắt gay cấn; (2) Tóm tắt cốt truyện/điểm nổi bật chính; (3) Lời kêu gọi hành động (Đăng ký kênh, để lại bình luận).
   - tags: 12-18 từ khóa SEO dạng mảng chuỗi (không có dấu #) để dán vào ô Tags của YouTube Studio (ví dụ: ["review phim", "tóm tắt phim", "phim hay"]).
   - hashtags: 10-15 hashtag chất lượng cao (viết liền có dấu #).
2. TikTok:
   - title: Caption ngắn gọn (1-2 câu), giật gân, khơi gợi tranh luận hoặc tò mò ngay giây đầu.
   - hashtags: 5-8 hashtag thịnh hành (#fyp, #xuhuong, #viral + các hashtag chủ đề video).
3. Facebook (Reels / Video Post):
   - title: Caption tự nhiên, mang tính kết nối cộng đồng, đặt câu hỏi để người xem comment.
   - description: Đoạn chia sẻ ngắn gọn về tình tiết video.
   - hashtags: 3-5 hashtag cô đọng (#reels, #trending + hashtag chủ đề).

Bắt buộc trả về đúng DUY NHẤT định dạng JSON thuần túy sau (100% TIẾNG VIỆT, KHÔNG CHỨA CHỮ HÁN):
{{
  "title": "Tiêu đề YouTube chính...",
  "alternative_titles": [
    "Tiêu đề gợi ý 1...",
    "Tiêu đề gợi ý 2...",
    "Tiêu đề gợi ý 3..."
  ],
  "description": "Nội dung mô tả YouTube đầy đủ...",
  "tags": ["từ khóa 1", "từ khóa 2", "từ khóa 3"],
  "hashtags": ["#tag1", "#tag2"],
  "tiktok": {{
    "title": "Caption TikTok...",
    "hashtags": ["#fyp", "#xuhuong"]
  }},
  "facebook": {{
    "title": "Caption Facebook...",
    "description": "Mô tả Facebook...",
    "hashtags": ["#reels", "#trending"]
  }}
}}
Chỉ trả về JSON thuần túy, không có lời dẫn hay giải thích thêm."""

    try:
        raw = client.call_ai(system_instruction, user_prompt)
        clean = _strip_fences_and_citations(raw)
        data = json.loads(_slice_to_payload(clean))
        if isinstance(data, dict) and "title" in data:
            data = _clean_social_metadata(data, script_translated)
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
        clean_vtitle = re.sub(r"[\u4e00-\u9fff]+", "", video_title).strip()
        orig_title_context = f"\nTiêu đề tham khảo: {clean_vtitle}" if clean_vtitle else ""

        user_prompt = f"""Dựa vào nội dung kịch bản video tiếng Việt dưới đây:{orig_title_context}{topic_context}
Lời thoại video:
\"\"\"
{script_translated[:6000]}
\"\"\"

Hãy tạo gói nội dung đăng bài chuyên nghiệp, chuẩn SEO và tối ưu tương tác cho cả 3 nền tảng:
1. YouTube (Video / Shorts):
   - title: Tiêu đề tiếng Việt chính cực kỳ hấp dẫn, kích thích tò mò (khoảng 45-70 ký tự).
   - alternative_titles: 3 tiêu đề gợi ý khác nhau mang phong cách giật gân, tò mò để A/B test.
   - description: Mô tả chi tiết 3 phần (hook 2 câu mở đầu, điểm nổi bật chính, kêu gọi Like/Đăng ký kênh).
   - tags: 12-18 từ khóa SEO dạng mảng chuỗi (không có dấu #) để dán vào ô Tags của YouTube Studio.
   - hashtags: 10-15 hashtag chất lượng cao (#shorts, #phimhay, #review...).
2. TikTok:
   - title: Caption ngắn gọn (1-2 câu), giật gân, cuốn hút.
   - hashtags: 5-8 hashtag thịnh hành (#fyp, #xuhuong, #viral...).
3. Facebook (Reels / Post):
   - title: Caption tự nhiên, tăng tương tác và bình luận.
   - description: Mô tả ngắn gọn thu hút.
   - hashtags: 3-5 hashtag cô đọng (#reels, #trending...).

Bắt buộc trả về đúng DUY NHẤT định dạng JSON sau (100% TIẾNG VIỆT, KHÔNG CHỨA CHỮ HÁN):
{{
  "title": "Tiêu đề YouTube...",
  "alternative_titles": ["Tiêu đề gợi ý 1...", "Tiêu đề gợi ý 2...", "Tiêu đề gợi ý 3..."],
  "description": "Nội dung mô tả YouTube...",
  "tags": ["từ khóa 1", "từ khóa 2", "từ khóa 3"],
  "hashtags": ["#tag1", "#tag2", ...],
  "tiktok": {{
    "title": "Caption TikTok...",
    "hashtags": ["#fyp", "#xuhuong", ...]
  }},
  "facebook": {{
    "title": "Caption Facebook...",
    "description": "Mô tả Facebook...",
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
                data = _clean_social_metadata(data, script_translated)
                logger.info(f"Đã tạo nội dung đăng bài qua Google AI Studio: «{data.get('title', '')[:50]}»")
                return data
        finally:
            client.close()
    except Exception as e:
        logger.warning(f"Tạo nội dung đăng bài qua Google AI Studio lỗi ({e}) — bỏ qua")
    return {}


def _generate_fallback_metadata(script_translated: str, video_title: str = "") -> dict:
    """Tạo metadata dự phòng tự nhiên 100% tiếng Việt dựa trên kịch bản khi không có AI."""
    clean_vtitle = re.sub(r"[\u4e00-\u9fff]+", "", str(video_title or "")).strip()
    title = clean_vtitle if len(clean_vtitle) >= 6 else ""
    if not title:
        sentences = [s.strip() for s in re.split(r"[.!?\n]+", script_translated) if s.strip()]
        first_line = sentences[0] if sentences else "Siêu Phẩm Video Lồng Tiếng Mới Nhất"
        title = first_line[:65]

    desc = (
        f"{title}\n\n"
        f"Chào mừng các bạn đã đến với kênh! Hãy thưởng thức trọn vẹn video để cảm nhận những "
        f"khoảnh khắc kịch tính và ý nghĩa nhất.\n\n"
        f"+ Nhấn LIKE và ĐĂNG KÝ KÊNH để không bỏ lỡ những siêu phẩm video hấp dẫn tiếp theo nhé!"
    )
    tags = [
        "review phim", "lồng tiếng", "tóm tắt phim", "phim hay", "phim mới",
        "shorts", "xem phim", "viral video", "thịnh hành", "video hot"
    ]
    hashtags = ["#shorts", "#reviewphim", "#phimhay", "#tomtatphim", "#trending", "#viral", "#xuhuong"]

    return {
        "title": title,
        "alternative_titles": [
            f"Bí Mật Đằng Sau: {title[:45]}",
            f"Sự Thật Bất Ngờ Trong {title[:45]}",
            f"Cái Kết Bất Ngờ Của {title[:45]}",
        ],
        "description": desc,
        "tags": tags,
        "hashtags": hashtags,
        "tiktok": {
            "title": f"{title[:60]} | Xem ngay để biết cái kết!",
            "hashtags": ["#fyp", "#xuhuong", "#viral", "#shorts", "#phimhay"]
        },
        "facebook": {
            "title": f"Mọi người thấy diễn biến này thế nào? Bình luận bên dưới nhé!\n{title}",
            "description": "Cùng theo dõi và chia sẻ cảm nghĩ của bạn về video này nhé!",
            "hashtags": ["#reels", "#trending", "#viral", "#phimhay"]
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
            return _clean_social_metadata(res, script_translated)

        if getattr(settings, "ai_studio_enabled", False):
            res_browser = generate_social_metadata_browser(
                script_original, script_translated, settings, video_title=video_title
            )
            if res_browser:
                return _clean_social_metadata(res_browser, script_translated)

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
                return _clean_social_metadata(metadata, script_translated)
        except InsufficientCreditError:
            raise
        except SaasError as e:
            logger.error(f"Viết nội dung đăng bài lỗi ({str(e)[:120]})")

    # Dự phòng thông minh: luôn tạo metadata để youtube_post.txt không bao giờ bị rỗng
    return _generate_fallback_metadata(script_translated, video_title=video_title)


# ------------------------------------------------------------- ghi ra tệp -- #

def _write_post_file(path: str, meta: dict) -> None:
    """``youtube_post.txt`` — nội dung đăng bài chuyên nghiệp, đầy đủ cho cả 3 nền tảng."""
    tiktok = meta.get("tiktok") or {}
    facebook = meta.get("facebook") or {}
    alt_titles = meta.get("alternative_titles") or []
    tags = meta.get("tags") or []
    if not tags:
        tags = [h.lstrip("#") for h in (meta.get("hashtags") or [])]

    bar_double = "=" * 70

    lines = [
        bar_double,
        "             GÓI NỘI DUNG ĐĂNG BÀI ĐA NỀN TẢNG (CHUẨN SEO / HIGH CTR)",
        bar_double,
        "",
        "============================== 1. YOUTUBE ==============================",
        f"► TIÊU ĐỀ CHÍNH (TITLE):\n{meta.get('title', '')}",
        "",
    ]

    if alt_titles:
        lines.append("► GỢI Ý TIÊU ĐỀ THAY THẾ (DÙNG CHO A/B TESTING):")
        for idx, at in enumerate(alt_titles, 1):
            lines.append(f"  {idx}. {at}")
        lines.append("")

    lines.extend([
        f"► MÔ TẢ VIDEO (DESCRIPTION):\n{meta.get('description', '')}",
        "",
        f"► DANH SÁCH THẺ TỪ KHÓA (TAGS / KEYWORDS - Copy dán thẳng vào YouTube Studio):\n{', '.join(tags)}",
        "",
        f"► HASHTAGS:\n{' '.join(meta.get('hashtags') or [])}",
        "",
        "=============================== 2. TIKTOK ===============================",
        f"► CAPTION / TIÊU ĐỀ TIKTOK:\n{tiktok.get('title', meta.get('title', ''))}",
        "",
        f"► HASHTAGS TIKTOK:\n{' '.join(tiktok.get('hashtags') or meta.get('hashtags') or [])}",
        "",
        "============================== 3. FACEBOOK ==============================",
        f"► BÀI ĐĂNG FACEBOOK / REELS:\n{facebook.get('title', meta.get('title', ''))}",
        "",
    ])

    fb_desc = facebook.get("description", "")
    if fb_desc:
        lines.extend([f"► MÔ TẢ CHI TIẾT:\n{fb_desc}", ""])

    lines.extend([
        f"► HASHTAGS FACEBOOK:\n{' '.join(facebook.get('hashtags') or meta.get('hashtags') or [])}",
        "",
        bar_double,
    ])

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
            if isinstance(saved_meta, dict) and saved_meta.get("title") and not _has_cjk(saved_meta.get("title", "")):
                meta = saved_meta
                logger.info(f"Dùng lại tiêu đề, mô tả đã có: «{str(saved_meta.get('title'))[:50]}»")
        except Exception:
            pass

    if not meta or not meta.get("title") or _has_cjk(meta.get("title", "")):
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
        thumb_title = meta.get("title") or "VIDEO MỚI NHẤT"
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
