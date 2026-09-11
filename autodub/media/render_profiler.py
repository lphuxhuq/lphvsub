"""Render profiler để đo kiểm và chẩn đoán hiệu năng xuất video."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger("autodub.render_profiler")


@dataclass
class RenderMetrics:
    total_time_s: float = 0.0
    video_duration_s: float = 0.0
    fps: float = 0.0
    speed: float = 0.0
    encoder: str = ""
    resolution: str = ""
    details: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"[PERF] Resolution: {self.resolution}",
            f"[PERF] Encoder   : {self.encoder}",
            f"[PERF] Duration  : {self.video_duration_s:.1f}s | Export Time: {self.total_time_s:.2f}s",
            f"[PERF] Speed     : {self.speed:.2f}x (FPS: {self.fps:.1f})",
        ]
        for k, v in self.details.items():
            lines.append(f"[PERF] - {k:<12}: {v:.2f}s")
        return "\n".join(lines)


class RenderProfiler:
    """Profiler nhẹ để thu thập số liệu render video (Zero overhead khi disabled)."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._start_time: float = 0.0
        self._checkpoints: dict[str, float] = {}

    def start(self) -> None:
        if not self.enabled:
            return
        self._start_time = time.perf_counter()

    def mark(self, name: str) -> None:
        if not self.enabled:
            return
        self._checkpoints[name] = time.perf_counter()

    def finish(
        self, video_duration_s: float, encoder: str = "", resolution: str = ""
    ) -> RenderMetrics:
        if not self.enabled:
            return RenderMetrics()
        now = time.perf_counter()
        total = max(0.001, now - (self._start_time or now))
        dur = max(0.001, video_duration_s)
        spd = dur / total
        fps = (dur * 30.0) / total  # Ước lượng trên 30fps

        metrics = RenderMetrics(
            total_time_s=total,
            video_duration_s=dur,
            fps=fps,
            speed=spd,
            encoder=encoder,
            resolution=resolution,
            details={},
        )
        last = self._start_time
        for k, ts in self._checkpoints.items():
            metrics.details[k] = ts - last
            last = ts
        return metrics
