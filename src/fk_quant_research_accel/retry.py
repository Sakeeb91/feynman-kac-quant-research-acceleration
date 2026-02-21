"""Retry configuration helpers for transient HTTP failures."""

from __future__ import annotations

from typing import Any
from typing import Callable
from typing import TypeVar

import httpx
import structlog
from tenacity import RetryCallState
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import stop_after_attempt
from tenacity import wait_exponential_jitter


T = TypeVar("T")


def _before_sleep_log(retry_state: RetryCallState) -> None:
    exception = retry_state.outcome.exception() if retry_state.outcome is not None else None
    structlog.get_logger().warning(
        "retrying_request",
        attempt=retry_state.attempt_number,
        error=str(exception) if exception is not None else None,
    )


RETRY_DEFAULTS: dict[str, Any] = {
    "max_attempts": 3,
    "initial_wait": 1.0,
    "max_wait": 60.0,
    "jitter": 5.0,
}


def is_retryable_error(exc: BaseException) -> bool:
    """Return whether an exception should trigger a retry."""
    if isinstance(
        exc,
        (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError),
    ):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500

    return False
