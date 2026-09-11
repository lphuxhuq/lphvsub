"""Tests cho Parallel Chunked Export (xuất video song song theo chunk)."""
import os
import subprocess
import threading
from unittest import mock

import pytest

from autodub.media.parallel_export import (
    ParallelExportError,
    _default_worker_count,
    _write_concat_list,
    parallel_chunked_export,
    plan_chunk_boundaries,
    probe_fps,
    probe_keyframes,
)


# ---------------------------------------------------------------- keyframes --

class TestPlanChunkBoundaries:
    def test_single_chunk_when_target_one(self):
        bounds = plan_chunk_boundaries([5.0, 10.0], 20.0, target_chunks=1)
        assert bounds == [0.0, 20.0]

    def test_too_short_video_returns_single_chunk(self):
        bounds = plan_chunk_boundaries([1.0, 2.0], 20.0, target_chunks=4)
        assert bounds == [0.0, 20.0]

    def test_bounds_are_monotonic_and_end_at_duration(self):
        kfs = [i * 5.0 for i in range(1, 40)]  # 5..195
        bounds = plan_chunk_boundaries(kfs, 200.0, target_chunks=4)
        assert bounds[0] == 0.0
        assert bounds[-1] == 200.0
        for a, b in zip(bounds, bounds[1:]):
            assert b > a
            # mọi biên (trừ 0 và dur) phải là keyframe
        for b in bounds[1:-1]:
            assert b in kfs

    def test_min_gap_respected(self):
        # keyframe dày đặc nhưng min_chunk_s chặn biên quá sát
        kfs = [i * 1.0 for i in range(1, 200)]
        bounds = plan_chunk_boundaries(kfs, 200.0, target_chunks=8,
                                       min_chunk_s=12.0)
        for a, b in zip(bounds, bounds[1:]):
            assert b - a >= 12.0

    def test_no_keyframes(self):
        bounds = plan_chunk_boundaries([], 200.0, target_chunks=4)
        assert bounds == [0.0, 200.0]

    def test_keyframes_outside_range_ignored(self):
        kfs = [-5.0, 0.0, 300.0]
        bounds = plan_chunk_boundaries(kfs, 100.0, target_chunks=2,
                                       min_chunk_s=10.0)
        assert bounds == [0.0, 100.0]


class TestDefaultWorkerCount:
    def test_nvenc_capped(self):
        n = _default_worker_count("NVIDIA NVENC")
        assert 2 <= n <= 5

    def test_cpu_scaled(self):
        n = _default_worker_count("CPU (libx264)")
        assert 2 <= n <= 6

    def test_qsv_capped_at_3(self):
        n = _default_worker_count("Intel QuickSync")
        assert 2 <= n <= 3


class TestWriteConcatList:
    def test_writes_file_uris(self, tmp_path):
        c1 = tmp_path / "chunk_0000.mp4"
        c2 = tmp_path / "chunk_0001.mp4"
        c1.write_bytes(b"x")
        c2.write_bytes(b"x")
        list_file = str(tmp_path / "concat.txt")
        _write_concat_list([str(c1), str(c2)], list_file)
        content = open(list_file, encoding="utf-8").read()
        assert "file 'file:" in content
        assert str(c1.resolve()) in content.replace("\\", "/") or \
            os.path.abspath(str(c1)).replace("\\", "/") in content

    def test_escapes_single_quotes(self, tmp_path):
        d = tmp_path / "it's dir"
        d.mkdir()
        c = d / "c.mp4"
        c.write_bytes(b"x")
        list_file = str(tmp_path / "l.txt")
        _write_concat_list([str(c)], list_file)
        content = open(list_file, encoding="utf-8").read()
        assert "'\\''" in content


class TestParallelChunkedExport:
    def _fake_ffmpeg_env(self, tmp_path, monkeypatch, fail_labels=None):
        """Giả lập ffmpeg: chunk → copy 1 byte; concat → gộp bytes."""
        fail_labels = fail_labels or set()
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            argv = cmd if isinstance(cmd, list) else cmd
            if argv[0] == "ffmpeg" and "concat" in argv:
                # lệnh concat: đọc list, gộp các chunk
                li = argv.index("-i")
                list_path = argv[li + 1]
                out_path = argv[-1]
                data = b""
                for line in open(list_path, encoding="utf-8"):
                    line = line.strip()
                    if line.startswith("file '"):
                        p = line[6:-1]
                        p = p.replace("'\\''", "'")
                        if p.startswith("file:"):
                            p = p[5:]
                        data += open(p, "rb").read()
                with open(out_path, "wb") as f:
                    f.write(data)
                return mock.MagicMock(returncode=0, stderr="")
            if argv[0] == "ffmpeg":
                # chunk render: tìm -y và output
                out_path = argv[argv.index("-y") + 1]
                with open(out_path, "wb") as f:
                    f.write(b"CHUNKDATA")
                return mock.MagicMock(returncode=0, stderr="")
            if argv[0] == "ffprobe":
                return mock.MagicMock(returncode=0,
                                      stdout='{"streams": [{"r_frame_rate": "30/1"}]}',
                                      stderr="")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

    def test_video_too_short_raises(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        with pytest.raises(ParallelExportError):
            parallel_chunked_export(
                lambda s, a, b, o: ["ffmpeg"],
                str(src), str(audio), str(tmp_path / "out.mp4"),
                duration_s=30.0, max_workers=4)

    def test_invalid_duration_raises(self, tmp_path):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        with pytest.raises(ParallelExportError):
            parallel_chunked_export(
                lambda s, a, b, o: ["ffmpeg"],
                str(src), str(audio), str(tmp_path / "o.mp4"), duration_s=0)

    def test_missing_input_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parallel_chunked_export(
                lambda s, a, b, o: ["ffmpeg"],
                str(tmp_path / "nope.mp4"), str(tmp_path / "nope.wav"),
                str(tmp_path / "o.mp4"), duration_s=600)

    def test_success_flow_produces_output(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        out = tmp_path / "out.mp4"
        self._fake_ffmpeg_env(tmp_path, monkeypatch)

        # Giả lập keyframes dày đều — monkeypatch probe_keyframes cho nhanh
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_keyframes",
            lambda p, timeout=300: [i * 10.0 for i in range(1, 100)])
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_fps", lambda p: 30.0)

        progress_events = []

        def cb(pct, msg):
            progress_events.append(pct)

        result = parallel_chunked_export(
            lambda s, a, b, o: ["ffmpeg", "-y", o],
            str(src), str(audio), str(out),
            duration_s=400.0, progress_cb=cb, max_workers=4,
            fps=30.0)

        assert result == str(out)
        assert out.read_bytes() == b"CHUNKDATA" * 4
        assert progress_events, "progress callback phải được gọi"

    def test_chunk_failure_raises(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        out = tmp_path / "out.mp4"
        self._fake_ffmpeg_env(tmp_path, monkeypatch)
        # Chunk 0000/0001 fail
        real_run = subprocess.run

        def failing_run(cmd, **kwargs):
            argv = cmd
            if argv[0] == "ffmpeg" and "-ss" in argv:
                out_arg = argv[argv.index("-y") + 1]
                if out_arg.replace("\\", "/").endswith(("chunk_0000.mp4", "chunk_0001.mp4")):
                    return mock.MagicMock(returncode=1, stderr="boom")
                with open(out_arg, "wb") as f:
                    f.write(b"CHUNKDATA")
                return mock.MagicMock(returncode=0, stderr="")
            if argv[0] == "ffprobe":
                return mock.MagicMock(
                    returncode=0,
                    stdout='{"streams": [{"r_frame_rate": "30/1"}]}',
                    stderr="")
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", failing_run)
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_keyframes",
            lambda p, timeout=300: [i * 10.0 for i in range(1, 100)])
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_fps", lambda p: 30.0)

        with pytest.raises(ParallelExportError):
            parallel_chunked_export(
                lambda s, a, b, o: ["ffmpeg", "-ss", f"{a:.3f}", "-y", o],
                str(src), str(audio), str(out),
                duration_s=400.0, max_workers=4, fps=30.0)

    def test_cancel_event_raises(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        out = tmp_path / "out.mp4"
        self._fake_ffmpeg_env(tmp_path, monkeypatch)
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_keyframes",
            lambda p, timeout=300: [i * 10.0 for i in range(1, 100)])
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_fps", lambda p: 30.0)

        cancel = threading.Event()
        cancel.set()
        with pytest.raises(ParallelExportError):
            parallel_chunked_export(
                lambda s, a, b, o: ["ffmpeg", "-y", o],
                str(src), str(audio), str(out),
                duration_s=400.0, max_workers=2, fps=30.0,
                cancel_event=cancel)

    def test_metadata_fn_called_on_output(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        out = tmp_path / "out.mp4"
        self._fake_ffmpeg_env(tmp_path, monkeypatch)
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_keyframes",
            lambda p, timeout=300: [i * 10.0 for i in range(1, 100)])
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_fps", lambda p: 30.0)

        called = []
        parallel_chunked_export(
            lambda s, a, b, o: ["ffmpeg", "-y", o],
            str(src), str(audio), str(out),
            duration_s=400.0, max_workers=4, fps=30.0,
            randomize_metadata_fn=lambda: called.append(out.read_bytes()))

        assert len(called) == 1
        assert called[0] == b"CHUNKDATA" * 4

    def test_tmp_dir_cleaned(self, tmp_path, monkeypatch):
        src = tmp_path / "src.mp4"
        audio = tmp_path / "a.wav"
        src.write_bytes(b"v")
        audio.write_bytes(b"a")
        out = tmp_path / "out.mp4"
        self._fake_ffmpeg_env(tmp_path, monkeypatch)
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_keyframes",
            lambda p, timeout=300: [i * 10.0 for i in range(1, 100)])
        monkeypatch.setattr(
            "autodub.media.parallel_export.probe_fps", lambda p: 30.0)

        leftovers_before = set(os.listdir(tmp_path))
        parallel_chunked_export(
            lambda s, a, b, o: ["ffmpeg", "-y", o],
            str(src), str(audio), str(out),
            duration_s=400.0, max_workers=4, fps=30.0)
        leftovers_after = set(os.listdir(tmp_path))
        # Không để lại thư mục autodub_pexport_* nào
        assert not [d for d in leftovers_after - leftovers_before
                    if d.startswith("autodub_pexport_")]


class TestProbeKeyframes:
    def test_raises_when_no_keyframe(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: mock.MagicMock(
            returncode=0, stdout="0.0,__\n0.5,___\n"))
        with pytest.raises(ParallelExportError):
            probe_keyframes("fake.mp4")

    def test_raises_on_ffprobe_failure(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: mock.MagicMock(
            returncode=1, stdout="", stderr="bad file"))
        with pytest.raises(ParallelExportError):
            probe_keyframes("fake.mp4")

    def test_parses_k_flags(self, monkeypatch):
        stdout = (
            "0.000000,K__\n"
            "0.033333,___\n"
            "2.000000,K__\n"
            "2.033333,___\n"
        )
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: mock.MagicMock(
            returncode=0, stdout=stdout, stderr=""))
        frames = probe_keyframes("fake.mp4")
        assert frames == [0.0, 2.0]

    def test_handles_kf_first_flag_variants(self, monkeypatch):
        stdout = "1.0,K_\n2.0,K\n3.0,__K\n"
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: mock.MagicMock(
            returncode=0, stdout=stdout, stderr=""))
        frames = probe_keyframes("fake.mp4")
        assert frames == [1.0, 2.0]


class TestProbeFps:
    def test_parses_r_frame_rate(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: mock.MagicMock(
            returncode=0,
            stdout='{"streams": [{"r_frame_rate": "30000/1001"}]}',
            stderr=""))
        assert abs(probe_fps("fake.mp4") - 29.97) < 0.01

    def test_fallback_on_error(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no ffmpeg")
        monkeypatch.setattr(subprocess, "run", boom)
        assert probe_fps("fake.mp4") == 30.0
