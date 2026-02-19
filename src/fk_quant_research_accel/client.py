"""HTTP client for interacting with a Feynman-Kac PINN backend."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


@dataclass(frozen=True)
class FKPinnClient:
    base_url: str
    timeout: float = 30.0

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def _get(self, path: str) -> dict[str, Any]:
        response = requests.get(self._url(path), timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self._url(path), json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def list_problems(self) -> dict[str, Any]:
        return self._get("/api/v1/problems")

    def create_simulation(
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
        return self._post("/api/v1/simulations", payload)

    def get_simulation(self, simulation_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/simulations/{simulation_id}")

    def get_result(self, simulation_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/results/{simulation_id}")

    def wait_until_terminal(
        self,
        simulation_id: str,
        poll_seconds: float = 1.5,
        max_wait_seconds: float = 1800.0,
    ) -> dict[str, Any]:
        """Poll a simulation until it reaches a terminal status or times out."""
        deadline = time.time() + max_wait_seconds
        while time.time() < deadline:
            simulation = self.get_simulation(simulation_id)
            if simulation["status"] in TERMINAL_STATUSES:
                return simulation
            time.sleep(poll_seconds)
        raise TimeoutError(f"Simulation {simulation_id} did not finish within timeout")
