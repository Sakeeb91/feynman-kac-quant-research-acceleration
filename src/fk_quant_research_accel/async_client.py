"""Async HTTP client for interacting with a Feynman-Kac PINN backend."""

from __future__ import annotations

from typing import Any

import httpx


class AsyncFKPinnClient:
    def __init__(self, base_url: str, timeout: float = 30.0, concurrency_limit: int = 20) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.concurrency_limit = concurrency_limit

        self._client = httpx.AsyncClient(base_url=self.base_url)

    async def _get(self, path: str) -> dict[str, Any]:
        response = await self._client.get(path)
        response.raise_for_status()
        return response.json()

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._client.post(path, json=payload)
        response.raise_for_status()
        return response.json()
