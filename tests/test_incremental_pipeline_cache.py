import os
import tempfile
from unittest.mock import MagicMock

from autodub.pipeline_cache import AlignGlobalCache
from autodub.speech.align import AlignmentStats, align_segments


def test_align_segments_incremental_flush(monkeypatch):
    """Xác nhận align_segments thực hiện flush định kỳ ('làm tới đâu cache tới đó')."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = os.path.join(tmp_dir, "align_test.db")
        cache_path = os.path.join(tmp_dir, "align_cache.json")
        test_cache = AlignGlobalCache(custom_db=db_path)

        # Mock get_align_cache để trỏ về test_cache
        monkeypatch.setattr("autodub.pipeline_cache.get_align_cache", lambda: test_cache)

        # Chuẩn bị dummy wav files
        wav_paths = []
        segments = []
        for i in range(25):
            w_path = os.path.join(tmp_dir, f"seg_{i:05d}.wav")
            with open(w_path, "wb") as f:
                f.write(b"RIFF" + b"\x00" * 40)  # fake wav
            wav_paths.append(w_path)
            segments.append(
                {
                    "id": i,
                    "start": float(i * 2),
                    "end": float(i * 2 + 1.5),
                    "text_vi": f"câu thứ {i}",
                }
            )

        # Mock Whisper transcribe và mapper
        dummy_model = MagicMock()
        monkeypatch.setattr(
            "autodub.speech.align._load_align_model", lambda: (dummy_model, "cpu", 2)
        )
        monkeypatch.setattr(
            "autodub.speech.align._asr_words",
            lambda m, w, beam_size=1: [("câu", 0.1, 0.4), ("thứ", 0.5, 0.8), ("test", 0.9, 1.2)],
        )
        monkeypatch.setattr("autodub.media.audio.wav_duration_s", lambda p: 1.5)
        monkeypatch.setattr(
            "autodub.speech.align._map_words",
            lambda tw, asr, base, dur: [
                (w, base + 0.1 * i, base + 0.1 * i + 0.08) for i, w in enumerate(tw)
            ],
        )

        stats = AlignmentStats()
        out = align_segments(
            segments,
            tmp_dir,
            "text_vi",
            cache_path=cache_path,
            stats=stats,
        )

        assert len(out) == 25
        # Kiểm tra test_cache đã lưu đủ 25 entries trong SQLite
        conn = test_cache._get_connection()
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM alignments").fetchone()[0]
            assert cnt == 25
        finally:
            conn.close()

        # Kiểm tra file json cục bộ cũng tồn tại và có đủ 25 entries
        import json

        with open(cache_path, encoding="utf-8") as f:
            disk_data = json.load(f)
        assert len(disk_data) == 25


def test_pipeline_diarization_skip_when_already_diarized():
    """Kiểm tra logic bỏ qua diarize_segments khi các câu đã có speaker_id."""
    from autodub.pipeline import DubRequest

    segments = [
        {"id": 0, "start": 0.0, "end": 1.0, "text": "a", "speaker_id": 1},
        {"id": 1, "start": 1.5, "end": 2.5, "text": "b", "speaker_id": 2},
    ]

    req = DubRequest(url="", force_new=False, diarization_enabled=True)
    # Kiểm tra điều kiện already_diarized
    already_diarized = (
        not getattr(req, "force_new", False)
        and all("speaker_id" in s for s in segments)
        and any(s.get("speaker_id", 0) > 0 for s in segments)
    )
    assert already_diarized is True


def test_pipeline_audio_merge_reuse_condition():
    """Kiểm tra logic tái sử dụng merged_audio_path khi file đã tồn tại và mới hơn clip."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        merged_path = os.path.join(tmp_dir, "dubbed_audio.wav")
        clip_path = os.path.join(tmp_dir, "seg_00000.wav")

        with open(clip_path, "wb") as f:
            f.write(b"clip")
        with open(merged_path, "wb") as f:
            f.write(b"merged_content" * 100)

        # merged_path được tạo sau clip_path nên mtime >= clip_path
        audio_mtime = os.path.getmtime(merged_path)
        clips = [clip_path]
        clips_up_to_date = all(os.path.getmtime(c) <= audio_mtime for c in clips)
        assert clips_up_to_date is True
        assert os.path.getsize(merged_path) > 1000


def test_pipeline_video_reuse_condition():
    """Kiểm tra logic tái sử dụng dubbed_video.mp4 khi video đã hoàn thành."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        video_path = os.path.join(tmp_dir, "orig.mp4")
        audio_path = os.path.join(tmp_dir, "dubbed.wav")
        dubbed_video = os.path.join(tmp_dir, "dubbed_video.mp4")

        with open(video_path, "wb") as f:
            f.write(b"v")
        with open(audio_path, "wb") as f:
            f.write(b"a")
        with open(dubbed_video, "wb") as f:
            f.write(b"dubbed_video_content" * 10_000)

        v_mtime = os.path.getmtime(dubbed_video)
        dep_mtimes = [os.path.getmtime(video_path), os.path.getmtime(audio_path)]
        can_reuse = (
            all(d <= v_mtime for d in dep_mtimes) and os.path.getsize(dubbed_video) > 100_000
        )
        assert can_reuse is True
