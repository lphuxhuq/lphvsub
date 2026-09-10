"""Tests for URL-based project auto-resume and deduplication."""
import json
import os
import shutil
import tempfile
import unittest

from autodub.pipeline import (
    DubPipeline,
    DubRequest,
    extract_video_id,
    find_existing_project_by_url,
    normalize_video_url,
)
from autodub.config import Settings


class TestUrlHelpers(unittest.TestCase):
    def test_extract_video_id(self):
        # Bilibili BV
        bili_url = "https://www.bilibili.com/video/BV1X4t865ECX/?spm_id_from=333.1007"
        self.assertEqual(extract_video_id(bili_url), "BV1X4t865ECX")

        # YouTube watch URL
        yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=shared"
        self.assertEqual(extract_video_id(yt_url), "dQw4w9WgXcQ")

        # YouTube short URL
        yt_short = "https://youtu.be/dQw4w9WgXcQ"
        self.assertEqual(extract_video_id(yt_short), "dQw4w9WgXcQ")

        # TikTok / Douyin
        douyin_url = "https://www.douyin.com/video/7123456789012345678"
        self.assertEqual(extract_video_id(douyin_url), "7123456789012345678")

        # Empty / non-matching
        self.assertEqual(extract_video_id(""), "")
        self.assertEqual(extract_video_id("https://example.com/some/random/page"), "")

    def test_normalize_video_url(self):
        # Strips tracking params but keeps v
        url1 = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=xyz123&fbclid=abc"
        norm1 = normalize_video_url(url1)
        self.assertIn("v=dqw4w9wgxcq", norm1)
        self.assertNotIn("fbclid", norm1)
        self.assertNotIn("si=", norm1)

        # Removes trailing slash
        url2 = "https://www.bilibili.com/video/BV1X4t865ECX/"
        norm2 = normalize_video_url(url2)
        self.assertFalse(norm2.endswith("/"))
        self.assertIn("bv1x4t865ecx", norm2)

        # Empty
        self.assertEqual(normalize_video_url(""), "")


class TestFindExistingProjectByUrl(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_find_by_source_info(self):
        proj_dir = os.path.join(self.test_dir, "20260905_proj_vi")
        data_dir = os.path.join(proj_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "source_info.json"), "w", encoding="utf-8") as f:
            json.dump({"url": "https://www.bilibili.com/video/BV1X4t865ECX"}, f)

        found = find_existing_project_by_url(self.test_dir, "https://www.bilibili.com/video/BV1X4t865ECX/?spm_id=123")
        self.assertEqual(found, proj_dir)

    def test_find_by_source_video_json(self):
        proj_dir = os.path.join(self.test_dir, "20260905_proj_vi")
        data_dir = os.path.join(proj_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "source_video.json"), "w", encoding="utf-8") as f:
            json.dump({"file_path": r"C:\tmp\video_BV1X4t865ECX.mp4", "url": "https://www.bilibili.com/video/BV1X4t865ECX"}, f)

        found = find_existing_project_by_url(self.test_dir, "https://www.bilibili.com/video/BV1X4t865ECX")
        self.assertEqual(found, proj_dir)

    def test_find_by_video_file_name(self):
        proj_dir = os.path.join(self.test_dir, "20260905_proj_vi")
        os.makedirs(proj_dir, exist_ok=True)
        # Video file directly in project directory
        open(os.path.join(proj_dir, "raw_BV1X4t865ECX.mp4"), "w").close()

        found = find_existing_project_by_url(self.test_dir, "https://www.bilibili.com/video/BV1X4t865ECX")
        self.assertEqual(found, proj_dir)

    def test_not_found_different_url(self):
        proj_dir = os.path.join(self.test_dir, "20260905_proj_vi")
        data_dir = os.path.join(proj_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "source_info.json"), "w", encoding="utf-8") as f:
            json.dump({"url": "https://www.bilibili.com/video/BV1X4t865ECX"}, f)

        found = find_existing_project_by_url(self.test_dir, "https://www.bilibili.com/video/BV9999999999")
        self.assertIsNone(found)


class TestPipelineUrlResume(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_auto_resume_existing_project(self):
        # Create an existing project with source_info.json and a fake video file
        existing_proj = os.path.join(self.test_dir, "20260905120000_vi")
        data_dir = os.path.join(existing_proj, "data")
        os.makedirs(data_dir, exist_ok=True)

        target_url = "https://www.bilibili.com/video/BV1X4t865ECX"
        with open(os.path.join(data_dir, "source_info.json"), "w", encoding="utf-8") as f:
            json.dump({"url": target_url}, f)

        fake_video = os.path.join(existing_proj, "source.mp4")
        open(fake_video, "w").close()

        settings = Settings.load()
        pipeline = DubPipeline(settings)

        # Mock stages of pipeline or verify folder selection before execution
        found = find_existing_project_by_url(self.test_dir, target_url)
        self.assertEqual(found, existing_proj)

        # Test DubRequest default force_new is False
        req = DubRequest(url=target_url, output_dir=self.test_dir)
        self.assertFalse(req.force_new)

        # Test DubRequest with force_new = True
        req_force = DubRequest(url=target_url, output_dir=self.test_dir, force_new=True)
        self.assertTrue(req_force.force_new)


if __name__ == "__main__":
    unittest.main()
