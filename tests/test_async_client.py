from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

import fk_quant_research_accel.async_client as async_client_module
from fk_quant_research_accel.async_client import AsyncFKPinnClient


@pytest.mark.anyio
async def test_async_client_instantiates_with_defaults() -> None:
    client = AsyncFKPinnClient(base_url="http://example.test")
    try:
        assert client.base_url == "http://example.test"
        assert client.timeout == 30.0
        assert client.concurrency_limit == 20
    finally:
        await client.aclose()


def test_async_client_sets_limits_from_concurrency(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class StubAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def get(self, *args: Any, **kwargs: Any) -> httpx.Response:
            del args, kwargs
            raise AssertionError("unexpected request")

        async def post(self, *args: Any, **kwargs: Any) -> httpx.Response:
            del args, kwargs
            raise AssertionError("unexpected request")

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(async_client_module.httpx, "AsyncClient", StubAsyncClient)

    AsyncFKPinnClient(base_url="http://example.test", timeout=12.0, concurrency_limit=7)

    limits = captured["limits"]
    timeout = captured["timeout"]
    assert limits.max_connections == 12
    assert limits.max_keepalive_connections == 7
    assert limits.keepalive_expiry == 30.0
    assert timeout.connect == 10.0
    assert timeout.read == 12.0
    assert timeout.write == 10.0
    assert timeout.pool == 5.0


@pytest.mark.anyio
async def test_async_client_context_manager_closes_client() -> None:
    client = AsyncFKPinnClient(base_url="http://example.test")
    async with client as opened:
        assert opened is client
        assert opened._client.is_closed is False

    assert client._client.is_closed is True


@pytest.mark.anyio
async def test_async_client_methods_make_expected_http_calls() -> None:
    observed_calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v1/simulations":
            payload = json.loads(request.content.decode("utf-8"))
            observed_calls.append((request.method, request.url.path, payload))
            return httpx.Response(200, json={"id": "sim-123"})

        observed_calls.append((request.method, request.url.path, None))

        if request.method == "GET" and request.url.path == "/api/v1/simulations/sim-123":
            return httpx.Response(200, json={"status": "completed"})
        if request.method == "GET" and request.url.path == "/api/v1/results/sim-123":
            return httpx.Response(200, json={"item": {"progress": 1.0}})
        if request.method == "GET" and request.url.path == "/api/v1/problems":
            return httpx.Response(200, json={"items": [{"id": "black_scholes"}]})

        return httpx.Response(404, json={"detail": "not found"})

    transport = httpx.MockTransport(handler)
    client = AsyncFKPinnClient(base_url="http://backend.test")
    original_client = client._client
    client._client = httpx.AsyncClient(base_url=client.base_url, transport=transport)
    await original_client.aclose()

    try:
        create_response = await client.create_simulation(
            problem_id="black_scholes",
            parameters={"dim": 5},
            training_config={"n_steps": 10},
        )
        simulation_response = await client.get_simulation("sim-123")
        result_response = await client.get_result("sim-123")
        problems_response = await client.list_problems()
    finally:
        await client.aclose()

    assert create_response == {"id": "sim-123"}
    assert simulation_response == {"status": "completed"}
    assert result_response == {"item": {"progress": 1.0}}
    assert problems_response == {"items": [{"id": "black_scholes"}]}

    assert observed_calls == [
        (
            "POST",
            "/api/v1/simulations",
            {
                "problem_id": "black_scholes",
                "parameters": {"dim": 5},
                "training_config": {"n_steps": 10},
            },
        ),
        ("GET", "/api/v1/simulations/sim-123", None),
        ("GET", "/api/v1/results/sim-123", None),
        ("GET", "/api/v1/problems", None),
    ]
