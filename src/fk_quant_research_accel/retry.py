"""Retry configuration helpers for transient HTTP failures."""

from __future__ import annotations

from typing import Any

import httpx


RETRY_DEFAULTS: dict[str, Any] = {
    "max_attempts": 3,
    "initial_wait": 1.0,
    "max_wait": 60.0,
    "jitter": 5.0,
}


def is_retryable_error(exc: BaseException) -> bool:
    """Return whether an exception should trigger a retry."""
    del exc
    return False
