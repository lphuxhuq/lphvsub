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
    """Tạo tiêu đề, mô tả, hashtag trực tiếp bằng Gemini API (không qua server)."""
    api_keys = getattr(settings, "gemini_api_key", "").strip()
    if not api_keys:
        return {}

    from autodub.text.translate_direct import GeminiDirectClient, _slice_to_payload, _strip_fences_and_citations

    model = getattr(settings, "gemini_model", "gemini-2.5-flash")
    client = GeminiDirectClient(api_keys, model=model)
    prompt = f"""Dựa vào nội dung video và bản dịch tiếng Việt dưới đây:
Tiêu đề gốc: {video_title}
Lời thoại video tiếng Việt: {script_translated[:4000]}

Hãy tạo nội dung đăng bài chuyên nghiệp, thu hút người xem cho YouTube, TikTok, Facebook dưới định dạng JSON:
{{
  "title": "Tiêu đề video tiếng Việt hấp dẫn (dưới 70 ký tự)",
  "description": "Mô tả ngắn gọn thu hút người xem (tóm tắt nội dung chính và bài học/điểm nhấn)",
  "hashtags": ["#shorts", "#phimhay", "#review", "#trending", "#viral"],
  "tiktok": {{
    "title": "Caption ngắn gọn, giật gân, cuốn hút cho TikTok",
    "hashtags": ["#fyp", "#viral", "#xuhuong"]
  }},
  "facebook": {{
    "title": "Caption tương tác, khơi gợi bình luận cho Facebook Reels/Video",
    "hashtags": ["#reels", "#trending"]
  }}
}}
Chỉ trả về JSON thuần túy."""

    try:
        raw = client.call_ai("", prompt)
        clean = _strip_fences_and_citations(raw)
        data = json.loads(_slice_to_payload(clean))
        if isinstance(data, dict) and "title" in data:
            logger.info(f"Đã tạo nội dung đăng bài trực tiếp: «{data.get('title', '')[:50]}»")
            return data
    except Exception as e:
        logger.warning(f"Tạo nội dung đăng bài trực tiếp lỗi ({e}) — bỏ qua")
    return {}


def generate_social_metadata(script_original: str, script_translated: str,
                             video_title: str = "", job_id: str = "",
                             settings=None) -> dict:
    """Nhờ máy chủ hoặc gọi trực tiếp Gemini viết tiêu đề, mô tả và hashtag."""
    if settings and getattr(settings, "gemini_api_key", "").strip():
        return generate_social_metadata_direct(
            script_original, script_translated, settings, video_title=video_title
        )

    from autodub.saas_client import (
        InsufficientCreditError, SaasError, get_client, is_configured,
        new_job_id)
    from autodub.text.translate_common import HOLD

    if not is_configured():
        # Chạy thuần trên máy — không có máy chủ để nhờ viết. Video vẫn xong.
        logger.info("Chưa cấu hình máy chủ — bỏ qua phần nội dung đăng bài")
        return {}

    try:
        metadata = get_client().generate_post(
            script_original, script_translated,
            job_id=job_id or new_job_id(), video_title=video_title,
            hold_id=HOLD.hold_id)
    except InsufficientCreditError:
        raise
    except SaasError as e:
        logger.error(f"Viết nội dung đăng bài lỗi ({str(e)[:120]}) — bỏ qua "
                     "phần đăng bài (không ảnh hưởng video)")
        return {}
    if metadata:
        logger.info("Đã viết xong nội dung đăng bài: "
                    f"«{str(metadata.get('title', ''))[:50]}»")
    return metadata or {}


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
    """Sinh phần nội dung đăng bài của một dự án."""
    del video_path

    result: dict = {"metadata": {}, "metadata_file": None}

    script_original = extract_script_text(
        segments, "text", os.path.join(output_dir, "script_original.txt"))
    script_translated = extract_script_text(
        segments, "text_vi", os.path.join(output_dir, "script_vi.txt"))

    if source_url:
        fetch_original_thumbnail(source_url, output_dir)

    result["metadata"] = generate_social_metadata(
        script_original, script_translated, video_title=video_title,
        job_id=job_id, settings=settings)

    metadata_path = os.path.join(output_dir, "youtube_metadata.json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(result["metadata"], f, ensure_ascii=False, indent=2)
    result["metadata_file"] = metadata_path

    post_path = os.path.join(output_dir, "youtube_post.txt")
    _write_post_file(post_path, result["metadata"])
    result["post_file"] = post_path
    return result
