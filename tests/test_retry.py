from __future__ import annotations

import httpx
import pytest

from fk_quant_research_accel.retry import is_retryable_error
from fk_quant_research_accel.retry import make_retry_decorator


def _http_status_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "https://example.test/resource")
    response = httpx.Response(status_code=status_code, request=request)
    return httpx.HTTPStatusError("bad response", request=request, response=response)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (httpx.TimeoutException("timeout"), True),
        (httpx.ConnectError("connect failed"), True),
        (httpx.RemoteProtocolError("protocol mismatch"), True),
        (_http_status_error(500), True),
        (_http_status_error(502), True),
        (_http_status_error(400), False),
        (_http_status_error(404), False),
        (ValueError("bad input"), False),
        (RuntimeError("boom"), False),
    ],
)
def test_is_retryable_error(exc: BaseException, expected: bool) -> None:
    assert is_retryable_error(exc) is expected


def test_make_retry_decorator_smoke() -> None:
    decorator = make_retry_decorator(max_attempts=1)

    @decorator
    def _run() -> str:
        return "ok"

    assert _run() == "ok"
