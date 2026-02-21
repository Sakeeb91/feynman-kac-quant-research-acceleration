"""Async HTTP client for interacting with a Feynman-Kac PINN backend."""

from __future__ import annotations

from typing import Any

import httpx


class AsyncFKPinnClient:
    def __init__(self, base_url: str, timeout: float = 30.0, concurrency_limit: int = 20) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.concurrency_limit = concurrency_limit

        client_timeout = httpx.Timeout(connect=10.0, read=timeout, write=10.0, pool=5.0)
        limits = httpx.Limits(
            max_connections=concurrency_limit + 5,
            max_keepalive_connections=concurrency_limit,
            keepalive_expiry=30.0,
        )
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=client_timeout, limits=limits)

    async def _get(self, path: str) -> dict[str, Any]:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(path, json=payload)
        response.raise_for_status()
        return response.json()

    async def list_problems(self) -> dict[str, Any]:
        return await self._get("/api/v1/problems")

    async def get_simulation(self, simulation_id: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/simulations/{simulation_id}")

    async def get_result(self, simulation_id: str) -> dict[str, Any]:
        return await self._get(f"/api/v1/results/{simulation_id}")

    async def create_simulation(
        self,
        problem_id: str,
        parameters: dict[str, Any],
        training_config: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "problem_id": problem_id,
            "parameters": parameters,
            "training_config": training_config,
        }
        return await self._post("/api/v1/simulations", payload)
