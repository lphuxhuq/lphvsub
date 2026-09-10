"""Tests for ErrorClassifier and SmartRetryPolicy."""

import pytest

from autodub.media.download.contract import ErrorType
from autodub.media.download.retry import ErrorClassifier, SmartRetryPolicy


def test_error_classifier_status_codes():
    assert ErrorClassifier.classify(None, status_code=403) == ErrorType.AUTH_ERROR
    assert ErrorClassifier.classify(None, status_code=416) == ErrorType.RANGE_NOT_SATISFIABLE
    assert ErrorClassifier.classify(None, status_code=429) == ErrorType.RATE_LIMITED
    assert ErrorClassifier.classify(None, status_code=404) == ErrorType.NOT_FOUND
    assert ErrorClassifier.classify(None, status_code=502) == ErrorType.NETWORK_ERROR


def test_error_classifier_exceptions():
    assert ErrorClassifier.classify(TimeoutError("Connection timed out")) == ErrorType.TIMEOUT
    assert ErrorClassifier.classify(ConnectionResetError("Connection reset by peer")) == ErrorType.CONNECTION_RESET
    assert ErrorClassifier.classify(RuntimeError("Task cancelled by user")) == ErrorType.CANCELLED
    assert ErrorClassifier.classify(ValueError("Corrupt moov atom in container")) == ErrorType.INVALID_MEDIA
    assert ErrorClassifier.classify(Exception("Random error")) == ErrorType.UNKNOWN


def test_retry_policy_429():
    policy = SmartRetryPolicy(max_retries=3, base_delay=0.5)
    decision = policy.evaluate(attempt=0, error=None, status_code=429)
    assert decision.should_retry
    assert decision.error_type == ErrorType.RATE_LIMITED
    assert decision.decrease_concurrency
    assert decision.delay_seconds >= 2.0


def test_retry_policy_416_reset_range():
    policy = SmartRetryPolicy(max_retries=3)
    decision = policy.evaluate(attempt=0, error=None, status_code=416)
    assert decision.should_retry
    assert decision.error_type == ErrorType.RANGE_NOT_SATISFIABLE
    assert decision.reset_range


def test_retry_policy_cancelled():
    policy = SmartRetryPolicy(max_retries=3)
    decision = policy.evaluate(attempt=0, error=RuntimeError("Operation cancelled"))
    assert not decision.should_retry
    assert decision.error_type == ErrorType.CANCELLED


def test_retry_policy_max_retries_exceeded():
    policy = SmartRetryPolicy(max_retries=2)
    decision = policy.evaluate(attempt=2, error=TimeoutError("Timed out"))
    assert not decision.should_retry
    assert "Exceeded max retries" in decision.reason


def test_execute_with_retry_succeeds_after_transient_failure():
    policy = SmartRetryPolicy(max_retries=3, base_delay=0.01, jitter=0.01)
    call_count = 0

    def flaky_func():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise TimeoutError("Temporary timeout")
        return "success"

    retries_recorded = []
    result = policy.execute_with_retry(
        flaky_func,
        on_retry=lambda att, dec: retries_recorded.append((att, dec.error_type)),
    )
    assert result == "success"
    assert call_count == 2
    assert len(retries_recorded) == 1
    assert retries_recorded[0][1] == ErrorType.TIMEOUT


def test_execute_with_retry_respects_cancellation():
    policy = SmartRetryPolicy(max_retries=3, base_delay=1.0)
    cancelled = True

    with pytest.raises(RuntimeError, match="cancelled"):
        policy.execute_with_retry(
            lambda: 1 / 0,
            is_cancelled=lambda: cancelled,
        )
