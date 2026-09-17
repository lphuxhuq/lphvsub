import os
import time

from autodub.media.cache_cleaner import (
    clean_preview_videos,
    clean_temp_prefetch,
    purge_all_caches,
)


def test_clean_preview_videos_age_and_size_caps(tmp_path, monkeypatch):
    preview_dir = tmp_path / "preview_videos"
    preview_dir.mkdir(parents=True)
    monkeypatch.setattr("autodub.media.cache_cleaner.cache_dir", lambda: str(tmp_path))

    # Create 3 files:
    # f_old: 5 days old
    # f_new1: fresh, 100KB
    # f_new2: fresh, 200KB
    f_old = preview_dir / "old_video.mp4"
    f_old.write_bytes(b"x" * 1024)
    old_time = time.time() - (5 * 86400.0)
    os.utime(f_old, (old_time, old_time))

    f_new1 = preview_dir / "new_video1.mp4"
    f_new1.write_bytes(b"y" * 1024)

    f_new2 = preview_dir / "new_video2.mp4"
    f_new2.write_bytes(b"z" * 1024)

    res = clean_preview_videos(max_age_days=3.0, max_size_mb=100.0)
    assert res["removed"] == 1
    assert not f_old.exists()
    assert f_new1.exists()
    assert f_new2.exists()

    # Test size cap: max_size_mb = 0 -> removes remaining files
    res2 = clean_preview_videos(max_age_days=30.0, max_size_mb=0.0)
    assert res2["removed"] == 2
    assert not f_new1.exists()
    assert not f_new2.exists()


def test_clean_temp_prefetch(tmp_path, monkeypatch):
    prefetch_dir = tmp_path / "voxdub_prefetch"
    prefetch_dir.mkdir(parents=True)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    old_f = prefetch_dir / "old.mp4"
    old_f.write_bytes(b"123")
    old_time = time.time() - (24 * 3600.0)
    os.utime(old_f, (old_time, old_time))

    new_f = prefetch_dir / "new.mp4"
    new_f.write_bytes(b"456")

    res = clean_temp_prefetch(max_age_hours=12.0)
    assert res["removed"] == 1
    assert not old_f.exists()
    assert new_f.exists()


def test_purge_all_caches_runs_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr("autodub.media.cache_cleaner.cache_dir", lambda: str(tmp_path))
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    res = purge_all_caches(output_dir=str(tmp_path / "output"))
    assert "removed" in res
    assert "reclaimed_bytes" in res
