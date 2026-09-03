"""Kiểm thử tính năng trích xuất và trả về social_metadata trong Gemini SRT UI."""
import json
import os
import pytest
from autodub.tools.gemini_srt_ui.app import app, jobs, batch_queues, get_social_metadata_safe, OUTPUT_FOLDER


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_get_social_metadata_safe_with_saved_file(tmp_path):
    job_id = "test-job-meta-123"
    jobs.pop(job_id, None)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    meta_path = os.path.join(OUTPUT_FOLDER, f"meta_{job_id}.json")
    if os.path.exists(meta_path):
        os.remove(meta_path)
    
    data = {
        "title": "Tóm Tắt Phim Cực Cuốn 2026",
        "description": "Nội dung phim kịch tính hồi hộp...",
        "hashtags": ["#reviewphim", "#shorts", "trending"]
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    try:
        job = {
            "status": "done",
            "original_name": "tap_1_review.mp4",
            "output_file": "tap_1_review_vi.srt",
        }
        res = get_social_metadata_safe(job_id, job)
        assert res is not None
        assert res["filename"] == "tap_1_review.mp4"
        assert res["title"] == "Tóm Tắt Phim Cực Cuốn 2026"
        assert "#reviewphim" in res["hashtags"]
        assert "#trending" in res["hashtags"]  # tự thêm # nếu thiếu
        assert res["hashtags_str"] == "#reviewphim #shorts #trending"
        assert "Tiêu đề: Tóm Tắt Phim Cực Cuốn 2026" in res["full_text"]
    finally:
        jobs.pop(job_id, None)
        if os.path.exists(meta_path):
            os.remove(meta_path)


def test_api_status_includes_social_metadata(client):
    job_id = "test-api-status-job"
    jobs[job_id] = {
        "status": "done",
        "progress": 100,
        "current_lines": 50,
        "total_lines": 50,
        "speed_lps": 5.0,
        "eta_sec": 0,
        "elapsed_sec": 10,
        "prompt_tokens": 100,
        "output_tokens": 100,
        "log": ["Hoàn thành dịch."],
        "output_file": "video_sub_vi.srt",
        "original_name": "video_sub.mp4",
        "input_file_path": None,
        "out_file_path": None,
        "error": None,
        "start_time": 0,
    }

    res = client.get(f"/api/status/{job_id}?include_subtitles=0")
    assert res.status_code == 200
    json_data = res.get_json()
    assert "social_metadata" in json_data
    meta = json_data["social_metadata"]
    assert meta is not None
    assert meta["filename"] == "video_sub.mp4"
    assert len(meta["hashtags"]) > 0


def test_api_batch_status_includes_social_metadata(client):
    batch_id = "test-batch-meta-789"
    jid = "job-batch-1"
    jobs[jid] = {
        "status": "done",
        "progress": 100,
        "current_lines": 20,
        "total_lines": 20,
        "output_file": "file1_vi.srt",
        "original_name": "file1.mp4",
        "error": None,
    }
    batch_queues[batch_id] = {
        "batch_id": batch_id,
        "jobs": [{"job_id": jid, "name": "file1.mp4"}],
        "status": "done",
        "total_files": 1,
        "failed_files": [],
    }

    res = client.get(f"/api/batch_status/{batch_id}")
    assert res.status_code == 200
    json_data = res.get_json()
    assert "jobs" in json_data
    assert len(json_data["jobs"]) == 1
    assert "social_metadata" in json_data["jobs"][0]
    assert json_data["jobs"][0]["social_metadata"]["filename"] == "file1.mp4"
