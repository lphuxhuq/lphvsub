"""Work-dir layout — where each artifact of a dub run lives.

Layout (new runs)::

    <work_dir>/
    ├── dubbed_video.mp4       ← video kết quả (người dùng cần)
    ├── transcript_vi.srt      ← phụ đề tiếng Việt (đăng kèm nếu muốn)
    ├── youtube/               ← tiêu đề, mô tả, hashtag, thumbnail
    └── data/                  ← file kỹ thuật cho resume/chỉnh sửa
        ├── original_audio.wav, vocals.wav, no_vocals.wav
        ├── transcript_original.json/.srt, transcript_vi.json
        ├── audio_vi_full.wav, slowed_video.mp4, slowed_background.wav
        ├── report.json, timing_guide.json, render_opts.json
        └── segments/, segments_speed*/

Older work dirs kept everything flat in the root. ``is_legacy_layout()``
detects them and every helper falls back to the flat path, so resume and the
segment editor keep working on dirs produced by previous builds.
"""
from __future__ import annotations

import os

DATA_SUBDIR = "data"
YOUTUBE_SUBDIR = "youtube"

# Any of these at the work-dir ROOT ⇒ dir was produced by an older build.
_LEGACY_MARKERS = ("transcript_original.json", "transcript_vi.json",
                   "original_audio.wav", "segments")


def is_legacy_layout(work_dir: str) -> bool:
    """True when this work dir keeps technical files flat in the root."""
    return any(os.path.exists(os.path.join(work_dir, m))
               for m in _LEGACY_MARKERS)


def data_dir(work_dir: str, create: bool = False) -> str:
    """Directory holding technical/pipeline artifacts."""
    if is_legacy_layout(work_dir):
        return work_dir
    d = os.path.join(work_dir, DATA_SUBDIR)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def data_path(work_dir: str, *names: str, create_dir: bool = False) -> str:
    """Path of a technical artifact (transcripts, wavs, caches, reports)."""
    return os.path.join(data_dir(work_dir, create=create_dir), *names)


def load_video_meta(work_dir: str) -> dict:
    """Title/uploader của video nguồn (``data/video_meta.json``).

    Downloader ghi file này lúc tải; trả về ``{}`` khi chưa có hoặc hỏng —
    title chỉ là ngữ cảnh bổ sung, thiếu không được làm hỏng bước nào.
    """
    import json
    try:
        with open(data_path(work_dir, "video_meta.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def youtube_dir(work_dir: str, create: bool = False) -> str:
    """Directory holding YouTube metadata + thumbnails (user-facing)."""
    if is_legacy_layout(work_dir):
        return work_dir
    d = os.path.join(work_dir, YOUTUBE_SUBDIR)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


def load_social_metadata(work_dir: str, default_title: str = "") -> dict:
    """Tải nội dung đăng bài (tiêu đề, caption, mô tả, hashtag) từ work_dir.

    Hỗ trợ đọc từ youtube/youtube_metadata.json, youtube_metadata.json,
    hoặc tự sinh fallback chất lượng cao nếu chưa có file metadata.
    """
    import json
    candidates = [
        os.path.join(youtube_dir(work_dir), "youtube_metadata.json"),
        os.path.join(work_dir, "youtube", "youtube_metadata.json"),
        os.path.join(work_dir, "youtube_metadata.json"),
        data_path(work_dir, "video_meta.json"),
    ]
    raw_data: dict = {}
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict) and (d.get("title") or d.get("hashtags") or d.get("youtube")):
                    raw_data = d
                    break
            except Exception:
                pass

    video_meta = load_video_meta(work_dir)
    title = (
        raw_data.get("title")
        or (raw_data.get("youtube") or {}).get("title")
        or default_title
        or video_meta.get("title")
        or "Video lồng tiếng hay nhất"
    )

    desc = (
        raw_data.get("description")
        or (raw_data.get("youtube") or {}).get("description")
        or f"{title}\n\nVideo hay chọn lọc lồng tiếng tiếng Việt chuẩn cảm xúc. Chúc các bạn xem video vui vẻ và đừng quên bấm Like & Đăng ký kênh nhé!"
    )

    tags = (
        raw_data.get("hashtags")
        or (raw_data.get("youtube") or {}).get("hashtags")
        or ["#shorts", "#reviewphim", "#trending", "#viral", "#xuhuong", "#phimhay"]
    )
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split() if t.strip()]

    tags_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tags])

    tiktok_data = raw_data.get("tiktok") or {}
    tiktok_caption = (
        raw_data.get("caption")
        or tiktok_data.get("caption")
        or tiktok_data.get("title")
        or tiktok_data.get("description")
        or ((title[:65] + "...") if len(title) > 65 else title)
    )
    tiktok_tags = tiktok_data.get("hashtags") or tags
    if isinstance(tiktok_tags, str):
        tiktok_tags = [t.strip() for t in tiktok_tags.split() if t.strip()]
    tiktok_tags_str = " ".join([t if t.startswith("#") else f"#{t}" for t in tiktok_tags])

    return {
        "title": title,
        "description": desc,
        "caption": tiktok_caption,
        "hashtags": tags,
        "hashtags_str": tags_str,
        "tiktok_caption": tiktok_caption,
        "tiktok_hashtags": tiktok_tags,
        "tiktok_hashtags_str": tiktok_tags_str,
        "raw": raw_data,
    }


def save_social_metadata(work_dir: str, meta: dict) -> str:
    """Lưu metadata nội dung bài đăng vào youtube/youtube_metadata.json."""
    import json
    out_dir = youtube_dir(work_dir, create=True)
    out_path = os.path.join(out_dir, "youtube_metadata.json")

    existing: dict = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                existing = d
        except Exception:
            pass

    existing.update(meta)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    return out_path

