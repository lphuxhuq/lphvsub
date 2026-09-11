"""Error classification and smart retry policy with exponential backoff and jitter."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from autodub.media.download.contract import ErrorType

logger = logging.getLogger(__name__)


class ErrorClassifier:
    """Classifies exceptions, status codes, and error messages into semantic ErrorType."""

    @staticmethod
    def classify(error: Any, status_code: int | None = None) -> ErrorType:
        if status_code is not None:
            if status_code == 403:
                return ErrorType.AUTH_ERROR
            elif status_code == 416:
                return ErrorType.RANGE_NOT_SATISFIABLE
            elif status_code == 429:
                return ErrorType.RATE_LIMITED
            elif status_code == 404:
                return ErrorType.NOT_FOUND
            elif 500 <= status_code < 600:
                return ErrorType.NETWORK_ERROR

        if error is None:
            return ErrorType.UNKNOWN

        # Check by exception type
        err_type_name = type(error).__name__
        err_str = str(error).lower()

        if "cancel" in err_str:
            return ErrorType.CANCELLED

        if (
            "403" in err_str
            or "forbidden" in err_str
            or "cookie" in err_str
            or "unauthorized" in err_str
        ):
            return ErrorType.AUTH_ERROR

        if "416" in err_str or "range not satisfiable" in err_str:
            return ErrorType.RANGE_NOT_SATISFIABLE

        if "429" in err_str or "too many requests" in err_str or "rate limit" in err_str:
            return ErrorType.RATE_LIMITED

        if "404" in err_str or "not found" in err_str:
            return ErrorType.NOT_FOUND

        if any(w in err_type_name.lower() or w in err_str for w in ("timeout", "timed out")):
            return ErrorType.TIMEOUT

        if any(
            w in err_str
            for w in ("connection reset", "connection_reset", "remotedisconnected", "broken pipe")
        ):
            return ErrorType.CONNECTION_RESET

        if "missing audio" in err_str or "audio stream required" in err_str:
            return ErrorType.MISSING_AUDIO

        if any(w in err_str for w in ("corrupt", "invalid media", "truncated", "moov atom")):
            return ErrorType.INVALID_MEDIA

        if any(
            w in err_str
            for w in ("connectionerror", "failed to establish", "network is unreachable")
        ):
            return ErrorType.NETWORK_ERROR

        return ErrorType.UNKNOWN


@dataclass
class RetryDecision:
    """Decision made by SmartRetryPolicy after an error."""

    should_retry: bool
    delay_seconds: float
    error_type: ErrorType
    reset_range: bool = False
    decrease_concurrency: bool = False
    switch_candidate: bool = False
    refresh_session: bool = False
    reason: str = ""


class SmartRetryPolicy:
    """Calculates exponential backoff with jitter and actionable recovery decisions."""

    def __init__(
        self,
        max_retries: int = 4,
        base_delay: float = 0.5,
        max_delay: float = 10.0,
        jitter: float = 0.25,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def evaluate(
        self,
        attempt: int,
        error: Any,
        status_code: int | None = None,
    ) -> RetryDecision:
        """Evaluates whether to retry and what corrective actions to apply.

        Args:
            attempt: Current attempt number (0-indexed, so 0 is first failure).
            error: Exception or failure cause.
            status_code: Optional HTTP status code.

        Returns:
            RetryDecision.
        """
        error_type = ErrorClassifier.classify(error, status_code=status_code)

        if error_type == ErrorType.CANCELLED:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                error_type=error_type,
                reason="Download was cancelled by caller",
            )

        if error_type == ErrorType.NOT_FOUND:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                error_type=error_type,
                switch_candidate=True,
                reason="Resource not found (404), candidate cannot be retried directly",
            )

        if attempt >= self.max_retries:
            return RetryDecision(
                should_retry=False,
                delay_seconds=0.0,
                error_type=error_type,
                reason=f"Exceeded max retries ({self.max_retries})",
            )

        # Calculate exponential backoff: base * 2^attempt
        raw_delay = min(self.max_delay, self.base_delay * (2**attempt))
        delay = raw_delay + random.uniform(0, self.jitter)

        if error_type == ErrorType.AUTH_ERROR:
            # 403 or auth error: retry with session refresh or candidate switch
            return RetryDecision(
                should_retry=attempt < 2,  # limit auth retries
                delay_seconds=delay,
                error_type=error_type,
                refresh_session=True,
                switch_candidate=True,
                reason="Authentication / 403 error, requesting session refresh & candidate switch",
            )

        if error_type == ErrorType.RANGE_NOT_SATISFIABLE:
            # 416: invalid range offset, must reset range to 0 or re-probe
            return RetryDecision(
                should_retry=True,
                delay_seconds=0.2,
                error_type=error_type,
                reset_range=True,
                reason="HTTP 416 Range Not Satisfiable, invalidating range offset",
            )

        if error_type == ErrorType.RATE_LIMITED:
            # 429: longer backoff and decrease concurrency
            rate_limit_delay = max(delay, 2.0 * (attempt + 1))
            return RetryDecision(
                should_retry=True,
                delay_seconds=rate_limit_delay,
                error_type=error_type,
                decrease_concurrency=True,
                switch_candidate=True,
                reason="HTTP 429 Rate limited, backing off and reducing concurrency",
            )

        if error_type in (ErrorType.TIMEOUT, ErrorType.CONNECTION_RESET, ErrorType.NETWORK_ERROR):
            return RetryDecision(
                should_retry=True,
                delay_seconds=delay,
                error_type=error_type,
                switch_candidate=(attempt >= 1),
                decrease_concurrency=(error_type == ErrorType.TIMEOUT and attempt >= 2),
                reason=f"Network error ({error_type.value}), retrying with backoff",
            )

        if error_type == ErrorType.INVALID_MEDIA:
            return RetryDecision(
                should_retry=attempt < 2,
                delay_seconds=delay,
                error_type=error_type,
                reset_range=True,
                switch_candidate=True,
                reason="Media container invalid, requesting clean re-download from alternate candidate",
            )

        # Default fallback retry
        return RetryDecision(
            should_retry=True,
            delay_seconds=delay,
            error_type=error_type,
            reason="Generic failure, retrying",
        )

    def execute_with_retry(
        self,
        func: Callable[[], Any],
        on_retry: Callable[[int, RetryDecision], None] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Any:
        """Executes a callable with smart retry policy."""
        attempt = 0
        while True:
            if is_cancelled and is_cancelled():
                raise RuntimeError("Operation cancelled before execution")

            try:
                return func()
            except Exception as e:
                decision = self.evaluate(attempt, e)
                if not decision.should_retry:
                    raise e

                if on_retry:
                    on_retry(attempt, decision)

                if decision.delay_seconds > 0:
                    # Sleep in small increments to respond quickly to cancellation
                    slept = 0.0
                    step = 0.1
                    while slept < decision.delay_seconds:
                        if is_cancelled and is_cancelled():
                            raise RuntimeError("Operation cancelled during retry wait") from None
                        time.sleep(min(step, decision.delay_seconds - slept))
                        slept += step

                attempt += 1
