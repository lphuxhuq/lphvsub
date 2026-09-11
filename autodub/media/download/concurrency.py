"""Adaptive Concurrency Controller using AIMD (Additive Increase / Multiplicative Decrease)."""

from __future__ import annotations

import logging
import threading
import time

from autodub.media.download.contract import BandwidthMode, ErrorType

logger = logging.getLogger(__name__)


class AdaptiveConcurrencyController:
    """Dynamically adjusts download worker concurrency based on real-time throughput and network errors."""

    def __init__(
        self,
        bandwidth_mode: BandwidthMode = BandwidthMode.AUTO,
        initial_concurrency: int | None = None,
        min_concurrency: int = 1,
        max_concurrency: int = 8,
        cooldown_seconds: float = 3.0,
        success_streak_threshold: int = 3,
    ):
        self.bandwidth_mode = bandwidth_mode
        self.min_concurrency = max(1, min_concurrency)

        # Apply mode defaults
        if bandwidth_mode == BandwidthMode.LOW:
            self.max_concurrency = min(2, max_concurrency)
            default_init = 1
        elif bandwidth_mode == BandwidthMode.STABLE:
            self.max_concurrency = min(4, max_concurrency)
            default_init = 2
        elif bandwidth_mode == BandwidthMode.FAST:
            self.max_concurrency = max(4, max_concurrency)
            default_init = 6
        else:  # AUTO
            self.max_concurrency = max_concurrency
            default_init = 4

        self.current_concurrency = initial_concurrency or default_init
        self.current_concurrency = min(
            self.max_concurrency, max(self.min_concurrency, self.current_concurrency)
        )

        self.cooldown_seconds = cooldown_seconds
        self.success_streak_threshold = success_streak_threshold

        self._lock = threading.Lock()
        self._last_decrease_time = 0.0
        self._success_streak = 0
        self._last_throughput = 0.0

    def get_concurrency(self) -> int:
        with self._lock:
            return self.current_concurrency

    def record_success(self, bytes_transferred: int, duration_seconds: float) -> int:
        """Records a successful transfer and opportunistically scales concurrency up."""
        if duration_seconds <= 0:
            return self.get_concurrency()

        throughput = bytes_transferred / duration_seconds

        with self._lock:
            now = time.time()
            # If in cooldown after an error, do not increase
            if now - self._last_decrease_time < self.cooldown_seconds:
                return self.current_concurrency

            self._success_streak += 1

            # When streak reached and not at max concurrency
            if self._success_streak >= self.success_streak_threshold:
                if self.current_concurrency < self.max_concurrency:
                    # Only scale up if throughput didn't severely degrade
                    if self._last_throughput == 0.0 or throughput >= (self._last_throughput * 0.75):
                        old_val = self.current_concurrency
                        self.current_concurrency = min(
                            self.max_concurrency, self.current_concurrency + 1
                        )
                        logger.debug(
                            f"AdaptiveConcurrency scaled UP: {old_val} -> {self.current_concurrency} "
                            f"(throughput: {throughput / (1024 * 1024):.2f} MB/s)"
                        )
                self._success_streak = 0

            self._last_throughput = throughput
            return self.current_concurrency

    def record_error(self, error_type: ErrorType, status_code: int | None = None) -> int:
        """Records a network or rate-limiting error and scales concurrency down (multiplicative decrease)."""
        severe_errors = {
            ErrorType.RATE_LIMITED,
            ErrorType.TIMEOUT,
            ErrorType.CONNECTION_RESET,
        }

        should_decrease = error_type in severe_errors or status_code == 429

        with self._lock:
            self._success_streak = 0
            if should_decrease:
                old_val = self.current_concurrency
                new_val = max(self.min_concurrency, self.current_concurrency // 2)
                self.current_concurrency = new_val
                self._last_decrease_time = time.time()
                logger.info(
                    f"AdaptiveConcurrency scaled DOWN: {old_val} -> {self.current_concurrency} "
                    f"due to {error_type.value} (status: {status_code})"
                )
            return self.current_concurrency

    def reset(self, initial: int | None = None) -> None:
        with self._lock:
            if initial is not None:
                self.current_concurrency = min(
                    self.max_concurrency, max(self.min_concurrency, initial)
                )
            self._success_streak = 0
            self._last_decrease_time = 0.0
            self._last_throughput = 0.0
