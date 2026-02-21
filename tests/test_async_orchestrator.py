from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from typing import Any
from uuid import uuid4

import anyio
import httpx
import pytest

from fk_quant_research_accel.async_orchestrator import resume_batch_async
from fk_quant_research_accel.async_orchestrator import run_batch_async
from fk_quant_research_accel.models import generate_batch_run_id
from fk_quant_research_accel.models import generate_scenario_run_id
from fk_quant_research_accel.orchestrator import BatchConfig
from fk_quant_research_accel.orchestrator import Scenario
from fk_quant_research_accel.store.metadata import MetadataStore


class MockAsyncFKPinnClient:
    def __init__(self) -> None:
        self.base_url = "http://mock-backend:8000"
        self._is_closed = False

    async def __aenter__(self) -> MockAsyncFKPinnClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        await self.aclose()

    async def aclose(self) -> None:
        self._is_closed = True

    async def create_simulation(
        self,
        problem_id: str,
        parameters: dict[str, Any],
        training_config: dict[str, Any],
    ) -> dict[str, Any]:
        del problem_id, parameters, training_config
        return {"id": f"sim-{uuid4()}"}

    async def get_simulation(self, simulation_id: str) -> dict[str, Any]:
        del simulation_id
        return {"status": "completed"}

    async def get_result(self, simulation_id: str) -> dict[str, Any]:
        del simulation_id
        return {
            "item": {
                "metrics": {"loss": 0.01, "grad_norm": 0.1, "lr": 1e-3},
                "progress": 1.0,
            }
        }


def _scenarios(count: int) -> list[Scenario]:
    return [
        Scenario(dim=5 + idx, volatility=0.2, correlation=0.0, option_type="call")
        for idx in range(count)
    ]


def _setup_batch_with_statuses(
    db_path: str,
    artifacts_dir: str,
    statuses: list[str],
) -> tuple[str, list[str], list[Scenario]]:
    store = MetadataStore(db_path)
    batch_run_id = str(generate_batch_run_id())
    scenarios = _scenarios(len(statuses))
    scenario_run_ids: list[str] = []

    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
        config_json=json.dumps(BatchConfig().to_payload(), sort_keys=True),
        manifest_schema_version=1,
        git_sha=None,
        git_dirty=None,
        python_version="3.14",
        os_info="test-os",
        seed=None,
        scenario_count=len(statuses),
        artifact_path=artifacts_dir,
        concurrency_limit=3,
    )

    for scenario, status in zip(scenarios, statuses, strict=True):
        scenario_run_id = str(generate_scenario_run_id())
        scenario_run_ids.append(scenario_run_id)
        store.create_scenario_run(
            scenario_run_id=scenario_run_id,
            batch_run_id=batch_run_id,
            scenario_json=json.dumps(scenario.as_parameters(), sort_keys=True),
            created_at=datetime.now(UTC).isoformat(),
        )
        if status == "submitted":
            store.update_scenario_status(scenario_run_id, status, simulation_id=f"sim-{uuid4()}")
        elif status != "pending":
            store.persist_scenario_result(
                scenario_run_id=scenario_run_id,
                status=status,
                result_json=json.dumps({"status": status}),
                score=0.1 if status == "completed" else float("inf"),
                error_message="failed" if status == "failed" else None,
                completed_at=datetime.now(UTC).isoformat(),
            )
    store.close()
    return batch_run_id, scenario_run_ids, scenarios
