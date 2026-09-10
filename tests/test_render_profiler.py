import pytest
import time
from autodub.media.render_profiler import RenderProfiler


def test_render_profiler_enabled():
    profiler = RenderProfiler(enabled=True)
    profiler.start()
    time.sleep(0.01)
    profiler.mark("decode")
    metrics = profiler.finish(video_duration_s=10.0, encoder="NVIDIA NVENC", resolution="1080x1920")
    assert metrics.total_time_s > 0
    assert metrics.speed > 0
    assert metrics.encoder == "NVIDIA NVENC"
    assert "1080x1920" in metrics.summary()


def test_render_profiler_disabled():
    profiler = RenderProfiler(enabled=False)
    profiler.start()
    profiler.mark("decode")
    metrics = profiler.finish(video_duration_s=10.0)
    assert metrics.total_time_s == 0.0
