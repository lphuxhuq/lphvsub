import json
import os
import pytest
from autodub.config import Settings
from autodub.content.generator import (
    generate_social_metadata,
    generate_social_metadata_direct,
    generate_content,
)
from autodub.languages import get_target
from autodub.pipeline import DubPipeline
from autodub.text.translate_direct import GeminiDirectClient


def test_generate_social_metadata_direct_with_api_key(monkeypatch):
    settings = Settings(
        gemini_api_key="AIzaSyTestApiKey123",
        gemini_model="gemini-2.5-flash",
    )

    fake_output = {
        "title": "Bí Quyết Nấu Phở Bò Gia Truyền",
        "description": "Hướng dẫn chi tiết cách nấu phở bò đậm đà chuẩn vị.",
        "hashtags": ["#phobo", "#monngon", "#shorts"],
        "tiktok": {
            "title": "Nấu phở bò chuẩn vị tại nhà cực dễ!",
            "hashtags": ["#fyp", "#xuhuong", "#food"]
        },
        "facebook": {
            "title": "Ai mê phở bò thì vào xem ngay nhé!",
            "hashtags": ["#reels", "#trending"]
        }
    }

    calls = []

    def _mock_call_ai(self, system_instruction, user_prompt, **kwargs):
        calls.append((system_instruction, user_prompt))
        return "```json\n" + json.dumps(fake_output, ensure_ascii=False) + "\n```"

    monkeypatch.setattr(GeminiDirectClient, "call_ai", _mock_call_ai)

    meta = generate_social_metadata(
        script_original="牛肉面制作教程",
        script_translated="Hôm nay tôi sẽ hướng dẫn các bạn nấu phở bò thơm ngon.",
        video_title="Cách nấu phở bò",
        settings=settings,
    )

    assert len(calls) == 1
    assert meta["title"] == "Bí Quyết Nấu Phở Bò Gia Truyền"
    assert len(meta["hashtags"]) == 3
    assert meta["tiktok"]["title"] == "Nấu phở bò chuẩn vị tại nhà cực dễ!"
    assert meta["facebook"]["title"] == "Ai mê phở bò thì vào xem ngay nhé!"


def test_pipeline_load_translation_extracts_ai_studio_metadata(tmp_path):
    """Bản dịch từ Google AI Studio chứa cả metadata đăng bài lẫn segments."""
    work_dir = str(tmp_path / "proj")
    data_dir = os.path.join(work_dir, "data")
    os.makedirs(data_dir, exist_ok=True)

    ai_studio_json = {
        "title": "Top 5 Mẹo Vặt Cuộc Sống Siêu Hữu Ích",
        "description": "Xem ngay 5 mẹo vặt giúp cuộc sống của bạn dễ dàng hơn.",
        "hashtags": ["#meovat", "#lifehacks", "#shorts"],
        "tiktok": {
            "title": "5 mẹo vặt này bạn nhất định phải biết!",
            "hashtags": ["#fyp", "#meovat", "#trending"]
        },
        "facebook": {
            "title": "Mẹo hay cuộc sống cực đơn giản!",
            "hashtags": ["#reels", "#meohay"]
        },
        "segments": [
            {"id": 1, "text": "第一个技巧", "text_vi": "Mẹo đầu tiên.", "start": 0.0, "end": 2.5, "duration": 2.5},
            {"id": 2, "text": "第二个技巧", "text_vi": "Mẹo thứ hai.", "start": 2.5, "end": 5.0, "duration": 2.5}
        ]
    }

    transcript_path = os.path.join(data_dir, "transcript_vi.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(ai_studio_json, f, ensure_ascii=False)

    pipeline = DubPipeline(Settings())
    target = get_target("vi")
    orig_segs = [
        {"id": 1, "text": "第一个技巧", "start": 0.0, "end": 2.5, "duration": 2.5},
        {"id": 2, "text": "第二个技巧", "start": 2.5, "end": 5.0, "duration": 2.5}
    ]

    segs = pipeline._load_translation(transcript_path, orig_segs, target)
    assert len(segs) == 2
    assert segs[0]["text_vi"] == "Mẹo đầu tiên."
    assert segs[1]["text_vi"] == "Mẹo thứ hai."

    # Kiểm tra file metadata và post file đã được tự động tạo trong youtube/
    yt_meta_path = os.path.join(work_dir, "youtube", "youtube_metadata.json")
    yt_post_path = os.path.join(work_dir, "youtube", "youtube_post.txt")
    assert os.path.exists(yt_meta_path)
    assert os.path.exists(yt_post_path)

    with open(yt_meta_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["title"] == "Top 5 Mẹo Vặt Cuộc Sống Siêu Hữu Ích"

    with open(yt_post_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "Top 5 Mẹo Vặt Cuộc Sống Siêu Hữu Ích" in content
    assert "#meovat" in content


def test_generate_content_reuses_existing_metadata(tmp_path):
    """Khi metadata đã có sẵn từ AI Studio, generate_content tái sử dụng ngay không cần gọi lại API."""
    out_dir = str(tmp_path / "youtube")
    os.makedirs(out_dir, exist_ok=True)

    meta_file = os.path.join(out_dir, "youtube_metadata.json")
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump({"title": "Tiêu đề có sẵn từ trước", "hashtags": ["#tag1"]}, f, ensure_ascii=False)

    segs = [{"id": 1, "text": "hi", "text_vi": "chào"}]
    res = generate_content(segs, source_url=None, output_dir=out_dir)

    assert res["metadata"]["title"] == "Tiêu đề có sẵn từ trước"


def test_generate_social_metadata_browser(monkeypatch):
    """Kiểm tra tạo metadata qua Google AI Studio Browser Client."""
    settings = Settings(ai_studio_enabled=True)

    from autodub.text.translate_browser import AiStudioBrowserClient

    fake_meta = {
        "title": "Review Phim Hấp Dẫn Nhất Tuần",
        "description": "Tóm tắt bộ phim cực hay.",
        "hashtags": ["#reviewphim", "#shorts"],
        "tiktok": {"title": "Phim hay đỉnh chóp!", "hashtags": ["#fyp"]},
        "facebook": {"title": "Xem ngay thôi!", "hashtags": ["#reels"]}
    }

    def _mock_translate_batch(self, sys_prompt, user_prompt, **kwargs):
        return json.dumps(fake_meta, ensure_ascii=False)

    monkeypatch.setattr(AiStudioBrowserClient, "translate_batch", _mock_translate_batch)
    monkeypatch.setattr(AiStudioBrowserClient, "close", lambda self: None)

    meta = generate_social_metadata(
        script_original="电影解说",
        script_translated="Hôm nay chúng ta sẽ cùng xem một bộ phim hành động gay cấn.",
        video_title="Review Phim",
        settings=settings,
    )

    assert meta["title"] == "Review Phim Hấp Dẫn Nhất Tuần"
    assert "#reviewphim" in meta["hashtags"]


def test_generate_social_metadata_fallback_never_empty():
    """Khi không có API Key và không có máy chủ, luôn sinh fallback metadata chuẩn thay vì bỏ trống."""
    meta = generate_social_metadata(
        script_original="电影解说",
        script_translated="Hôm nay chúng ta sẽ cùng thưởng thức một bộ phim tuyệt đỉnh.",
        video_title="Phim Hành Động 2026",
        settings=None,
    )

    assert meta["title"] == "Phim Hành Động 2026"
    assert len(meta["hashtags"]) >= 3
    assert "tiktok" in meta
    assert "facebook" in meta


def test_pipeline_generate_content_with_video_path(tmp_path):
    """Kiểm tra pipeline._generate_content nhận video_path an toàn không bị UnboundLocalError."""
    settings = Settings(generate_metadata=True)
    pipeline = DubPipeline(settings)
    target = get_target("vi")
    work_dir = str(tmp_path / "proj")
    os.makedirs(work_dir, exist_ok=True)
    video_file = str(tmp_path / "sample.mp4")
    with open(video_file, "wb") as f:
        f.write(b"mock video data")

    segments = [{"id": 1, "text": "你好", "text_vi": "Xin chào"}]
    res = pipeline._generate_content(target, segments, "https://example.com", work_dir, video_path=video_file)
    assert isinstance(res, dict)


