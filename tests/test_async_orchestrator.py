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


@pytest.mark.anyio
async def test_run_batch_async_basic(tmp_path) -> None:
    client = MockAsyncFKPinnClient()
    artifacts_dir = tmp_path / "artifacts"
    db_path = artifacts_dir / "experiments.db"

    rows = await run_batch_async(
        client=client,
        scenarios=_scenarios(3),
        batch_config=BatchConfig(),
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        concurrency_limit=2,
        max_retries=3,
        artifacts_dir=artifacts_dir,
        db_path=db_path,
    )

    assert len(rows) == 3
    assert all(row["status"] == "completed" for row in rows)
    scores = [row["score"] for row in rows]
    assert scores == sorted(scores)

    store = MetadataStore(db_path)
    try:
        batch_rows = store.connection.execute("SELECT status FROM batch_runs").fetchall()
        scenario_rows = store.connection.execute("SELECT status FROM scenario_runs").fetchall()
    finally:
        store.close()

    assert len(batch_rows) == 1
    assert batch_rows[0][0] == "completed"
    assert len(scenario_rows) == 3
    assert {row[0] for row in scenario_rows} == {"completed"}


@pytest.mark.anyio
async def test_concurrent_execution_respects_limit(tmp_path) -> None:
    class TrackingClient(MockAsyncFKPinnClient):
        def __init__(self) -> None:
            super().__init__()
            self._active = 0
            self.max_active = 0

        async def create_simulation(
            self,
            problem_id: str,
            parameters: dict[str, Any],
            training_config: dict[str, Any],
        ) -> dict[str, Any]:
            del problem_id, parameters, training_config
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            await anyio.sleep(0.01)
            return {"id": f"sim-{uuid4()}"}

        async def get_result(self, simulation_id: str) -> dict[str, Any]:
            payload = await super().get_result(simulation_id)
            self._active -= 1
            return payload

    client = TrackingClient()
    artifacts_dir = tmp_path / "artifacts"
    await run_batch_async(
        client=client,
        scenarios=_scenarios(5),
        batch_config=BatchConfig(),
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        concurrency_limit=2,
        artifacts_dir=artifacts_dir,
        db_path=artifacts_dir / "experiments.db",
    )

    assert client.max_active <= 2


@pytest.mark.anyio
async def test_single_failure_does_not_cancel_siblings(tmp_path) -> None:
    class PartialFailureClient(MockAsyncFKPinnClient):
        async def create_simulation(
            self,
            problem_id: str,
            parameters: dict[str, Any],
            training_config: dict[str, Any],
        ) -> dict[str, Any]:
            del problem_id, training_config
            if int(parameters["dim"]) == 6:
                raise RuntimeError("bad scenario")
            return {"id": f"sim-{parameters['dim']}-{uuid4()}"}

    client = PartialFailureClient()
    artifacts_dir = tmp_path / "artifacts"
    rows = await run_batch_async(
        client=client,
        scenarios=_scenarios(3),
        batch_config=BatchConfig(),
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        concurrency_limit=2,
        artifacts_dir=artifacts_dir,
        db_path=artifacts_dir / "experiments.db",
    )

    assert len(rows) == 3
    statuses = [row["status"] for row in rows]
    assert statuses.count("completed") == 2
    assert statuses.count("failed") == 1
    failed_row = next(row for row in rows if row["status"] == "failed")
    assert "bad scenario" in str(failed_row["error_message"])

    store = MetadataStore(artifacts_dir / "experiments.db")
    try:
        persisted = store.get_scenario_runs(store.connection.execute("SELECT batch_run_id FROM batch_runs").fetchone()[0])
    finally:
        store.close()
    assert len(persisted) == 3
    assert {row["status"] for row in persisted} == {"completed", "failed"}


@pytest.mark.anyio
async def test_transient_error_retried(tmp_path) -> None:
    class TransientPollingClient(MockAsyncFKPinnClient):
        def __init__(self) -> None:
            super().__init__()
            self.poll_calls = 0

        async def get_simulation(self, simulation_id: str) -> dict[str, Any]:
            del simulation_id
            self.poll_calls += 1
            if self.poll_calls == 1:
                raise httpx.TimeoutException("first timeout")
            return {"status": "completed"}

    client = TransientPollingClient()
    rows = await run_batch_async(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        max_retries=3,
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "artifacts" / "experiments.db",
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "completed"
    assert client.poll_calls >= 2


@pytest.mark.anyio
async def test_non_retryable_error_fails_immediately(tmp_path) -> None:
    class BadRequestClient(MockAsyncFKPinnClient):
        def __init__(self) -> None:
            super().__init__()
            self.create_calls = 0

        async def create_simulation(
            self,
            problem_id: str,
            parameters: dict[str, Any],
            training_config: dict[str, Any],
        ) -> dict[str, Any]:
            del problem_id, parameters, training_config
            self.create_calls += 1
            request = httpx.Request("POST", "http://mock-backend:8000/api/v1/simulations")
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError("bad request", request=request, response=response)

    client = BadRequestClient()
    rows = await run_batch_async(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        max_retries=3,
        artifacts_dir=tmp_path / "artifacts",
        db_path=tmp_path / "artifacts" / "experiments.db",
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "failed"
    assert "bad request" in str(rows[0]["error_message"])
    assert client.create_calls == 1


@pytest.mark.anyio
async def test_resume_batch_async_only_incomplete(tmp_path) -> None:
    class CountingClient(MockAsyncFKPinnClient):
        def __init__(self) -> None:
            super().__init__()
            self.create_calls = 0

        async def create_simulation(
            self,
            problem_id: str,
            parameters: dict[str, Any],
            training_config: dict[str, Any],
        ) -> dict[str, Any]:
            del problem_id, parameters, training_config
            self.create_calls += 1
            return {"id": f"sim-resume-{uuid4()}"}

    artifacts_dir = tmp_path / "artifacts"
    batch_run_id, scenario_run_ids, _ = _setup_batch_with_statuses(
        db_path=str(artifacts_dir / "experiments.db"),
        artifacts_dir=str(artifacts_dir),
        statuses=["completed", "failed", "pending"],
    )
    client = CountingClient()
    rows = await resume_batch_async(
        client=client,
        batch_run_id=batch_run_id,
        force=False,
        poll_seconds=0.0,
        max_wait_seconds=2.0,
        artifacts_dir=artifacts_dir,
        db_path=artifacts_dir / "experiments.db",
    )

    assert len(rows) == 1
    assert client.create_calls == 1

    store = MetadataStore(artifacts_dir / "experiments.db")
    try:
        scenarios = {row["scenario_run_id"]: row for row in store.get_scenario_runs(batch_run_id)}
    finally:
        store.close()

    assert scenarios[scenario_run_ids[0]]["status"] == "completed"
    assert scenarios[scenario_run_ids[1]]["status"] == "failed"
    assert scenarios[scenario_run_ids[2]]["status"] == "completed"
