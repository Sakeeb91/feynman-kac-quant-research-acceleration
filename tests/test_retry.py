from __future__ import annotations

import httpx

from fk_quant_research_accel.retry import is_retryable_error


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/resource")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError("bad response", request=request, response=response)


def test_timeout_exception_is_retryable() -> None:
    assert is_retryable_error(httpx.TimeoutException("timeout")) is True
