"""Kiểm tra tích hợp tự động nạp file SRT từ dự án sang Web Gemini SRT Translator."""
import os
import tempfile
import pytest
from autodub.tools.gemini_srt_ui.server_manager import get_server_manager
from autodub.tools.gemini_srt_ui.app import create_app


def test_open_project_srt():
    mgr = get_server_manager()
    with tempfile.TemporaryDirectory() as tmpdir:
        srt_file = os.path.join(tmpdir, "transcript_original.srt")
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nXin chao the gioi\n\n2\n00:00:03,500 --> 00:00:05,000\nThu nghiem\n\n")

        url = mgr.open_project_srt(srt_file, work_dir=tmpdir, open_browser=False)
        assert "?preload=" in url
        assert mgr.pending_file is not None
        assert mgr.pending_file["original"] == "transcript_original.srt"
        assert mgr.pending_file["line_count"] == 2
        assert mgr.pending_file["work_dir"] == tmpdir


def test_pending_project_endpoint():
    mgr = get_server_manager()
    with tempfile.TemporaryDirectory() as tmpdir:
        srt_file = os.path.join(tmpdir, "test_sample.srt")
        with open(srt_file, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:02,000\nHello\n\n")

        url = mgr.open_project_srt(srt_file, work_dir=tmpdir, open_browser=False)
        filename = mgr.pending_file["filename"]

        app = create_app()
        client = app.test_client()
        res = client.get(f"/api/voxdub/pending_project?preload={filename}")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["file"]["filename"] == filename
        assert data["file"]["line_count"] == 1
