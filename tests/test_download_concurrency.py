"""Tests for AdaptiveConcurrencyController."""

import time

from autodub.media.download.concurrency import AdaptiveConcurrencyController
from autodub.media.download.contract import BandwidthMode, ErrorType


def test_concurrency_modes_initialization():
    low = AdaptiveConcurrencyController(bandwidth_mode=BandwidthMode.LOW)
    assert low.get_concurrency() == 1
    assert low.max_concurrency == 2

    stable = AdaptiveConcurrencyController(bandwidth_mode=BandwidthMode.STABLE)
    assert stable.get_concurrency() == 2
    assert stable.max_concurrency == 4

    fast = AdaptiveConcurrencyController(bandwidth_mode=BandwidthMode.FAST)
    assert fast.get_concurrency() == 6
    assert fast.max_concurrency >= 6

    auto = AdaptiveConcurrencyController(bandwidth_mode=BandwidthMode.AUTO)
    assert auto.get_concurrency() == 4
    assert auto.max_concurrency == 8


def test_concurrency_multiplicative_decrease():
    controller = AdaptiveConcurrencyController(
        initial_concurrency=8,
        min_concurrency=1,
        max_concurrency=8,
    )
    assert controller.get_concurrency() == 8

    # 429 error -> cuts in half
    controller.record_error(ErrorType.RATE_LIMITED, status_code=429)
    assert controller.get_concurrency() == 4

    # Timeout error -> cuts in half again
    controller.record_error(ErrorType.TIMEOUT)
    assert controller.get_concurrency() == 2

    # Another error -> down to min (1)
    controller.record_error(ErrorType.CONNECTION_RESET)
    assert controller.get_concurrency() == 1

    # Cannot decrease below min_concurrency
    controller.record_error(ErrorType.TIMEOUT)
    assert controller.get_concurrency() == 1


def test_concurrency_additive_increase():
    controller = AdaptiveConcurrencyController(
        initial_concurrency=2,
        min_concurrency=1,
        max_concurrency=5,
        cooldown_seconds=0.0,
        success_streak_threshold=2,
    )
    assert controller.get_concurrency() == 2

    # 2 successful chunks of 1MB over 0.5s (2MB/s)
    controller.record_success(1024 * 1024, 0.5)
    assert controller.get_concurrency() == 2 # Need 2 successes for streak

    controller.record_success(1024 * 1024, 0.5)
    assert controller.get_concurrency() == 3 # Scaled up to 3!

    # Another streak
    controller.record_success(1024 * 1024, 0.5)
    controller.record_success(1024 * 1024, 0.5)
    assert controller.get_concurrency() == 4

    # Another streak
    controller.record_success(1024 * 1024, 0.5)
    controller.record_success(1024 * 1024, 0.5)
    assert controller.get_concurrency() == 5 # Reached max

    # Stays clamped at max
    controller.record_success(1024 * 1024, 0.5)
    controller.record_success(1024 * 1024, 0.5)
    assert controller.get_concurrency() == 5


def test_concurrency_cooldown_prevents_premature_scale_up():
    controller = AdaptiveConcurrencyController(
        initial_concurrency=4,
        cooldown_seconds=5.0,
        success_streak_threshold=1,
    )
    # Trigger error
    controller.record_error(ErrorType.RATE_LIMITED, status_code=429)
    assert controller.get_concurrency() == 2

    # Immediate success during cooldown should NOT increase concurrency
    controller.record_success(1024 * 1024, 0.1)
    assert controller.get_concurrency() == 2
