from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import yaml

from fk_quant_research_accel.orchestrator import BatchConfig, Scenario, run_batch


class MockFKPinnClient:
    def __init__(
        self,
        *,
        fail_on_scenario: int | None = None,
        losses: list[float] | None = None,
        checkpoint_mode: str = "none",
    ) -> None:
        self.base_url = "http://mock-backend:8000"
        self.fail_on_scenario = fail_on_scenario
        self.losses = losses or []
        self.checkpoint_mode = checkpoint_mode
        self._id_to_index: dict[str, int] = {}

    def create_simulation(
        self,
        problem_id: str,
        parameters: dict[str, float | int | str],
        training_config: dict[str, float | int],
    ) -> dict[str, str]:
        _ = (problem_id, parameters, training_config)
        index = len(self._id_to_index)
        simulation_id = f"sim-{index}-{uuid4()}"
        self._id_to_index[simulation_id] = index
        return {"id": simulation_id, "status": "pending"}

    def get_simulation(self, simulation_id: str) -> dict[str, str]:
        _ = simulation_id
        return {"status": "completed"}

    def wait_until_terminal(
        self,
        simulation_id: str,
        poll_seconds: float = 1.5,
        max_wait_seconds: float = 1800.0,
    ) -> dict[str, str]:
        _ = (poll_seconds, max_wait_seconds)
        index = self._id_to_index[simulation_id]
        if self.fail_on_scenario is not None and index == self.fail_on_scenario:
            raise TimeoutError(f"mock timeout for scenario index={index}")
        return {"status": "completed"}

    def get_result(self, simulation_id: str) -> dict[str, dict]:
        index = self._id_to_index[simulation_id]
        loss = self.losses[index] if index < len(self.losses) else 0.02
        item: dict[str, object] = {
            "metrics": {"loss": loss, "grad_norm": 0.5, "lr": 1e-3},
            "progress": 1.0,
        }
        if self.checkpoint_mode == "inline":
            item["checkpoint"] = base64.b64encode(b"checkpoint-bytes").decode("utf-8")
        return {"item": item}


def _scenarios(count: int = 2) -> list[Scenario]:
    return [
        Scenario(dim=5 + idx, volatility=0.2, correlation=0.0, option_type="call")
        for idx in range(count)
    ]


def _single_batch_dir(artifacts_root: Path) -> Path:
    candidates = [path for path in artifacts_root.iterdir() if path.is_dir()]
    assert len(candidates) == 1
    return candidates[0]


def test_run_batch_creates_artifact_directory_structure(tmp_path) -> None:
    client = MockFKPinnClient()
    artifacts_root = tmp_path / "artifacts"

    run_batch(
        client=client,
        scenarios=_scenarios(2),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    batch_dir = _single_batch_dir(artifacts_root)
    scenario_dirs = [path for path in batch_dir.iterdir() if path.is_dir()]
    assert len(scenario_dirs) == 2
    manifest_path = batch_dir / "manifest.yaml"
    assert manifest_path.exists()
    with manifest_path.open("r", encoding="utf-8") as handle:
        parsed_manifest = yaml.safe_load(handle)
    assert parsed_manifest["batch_run_id"] == batch_dir.name


def test_run_batch_persists_results_to_sqlite(tmp_path) -> None:
    client = MockFKPinnClient()
    artifacts_root = tmp_path / "artifacts"

    run_batch(
        client=client,
        scenarios=_scenarios(2),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    db_path = artifacts_root / "experiments.db"
    conn = sqlite3.connect(db_path)
    try:
        batch_count = conn.execute("SELECT COUNT(*) FROM batch_runs").fetchone()[0]
        scenario_count = conn.execute("SELECT COUNT(*) FROM scenario_runs").fetchone()[0]
        statuses = [row[0] for row in conn.execute("SELECT status FROM scenario_runs").fetchall()]
    finally:
        conn.close()

    assert batch_count == 1
    assert scenario_count == 2
    assert statuses.count("completed") == 2


def test_run_batch_writes_result_json_per_scenario(tmp_path) -> None:
    client = MockFKPinnClient()
    artifacts_root = tmp_path / "artifacts"

    run_batch(
        client=client,
        scenarios=_scenarios(2),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    batch_dir = _single_batch_dir(artifacts_root)
    for scenario_dir in [path for path in batch_dir.iterdir() if path.is_dir()]:
        result_path = scenario_dir / "result.json"
        assert result_path.exists()
        with result_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        assert "simulation_id" in payload
        assert "status" in payload
        assert "score" in payload
        assert "dim" in payload
