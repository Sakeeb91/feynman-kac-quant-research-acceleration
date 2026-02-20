from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import yaml
import structlog
import pytest

from fk_quant_research_accel.logging import configure_logging
from fk_quant_research_accel.models.experiment import ExperimentManifest
from fk_quant_research_accel.orchestrator import (
    BatchConfig,
    Scenario,
    generate_scenarios_from_manifest,
    run_batch,
)


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


def setup_function() -> None:
    structlog.reset_defaults()
    configure_logging("INFO")


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


def test_run_batch_records_failed_scenario_with_error(tmp_path) -> None:
    client = MockFKPinnClient(fail_on_scenario=1)
    artifacts_root = tmp_path / "artifacts"

    rows = run_batch(
        client=client,
        scenarios=_scenarios(2),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    statuses = [row["status"] for row in rows]
    assert "completed" in statuses
    assert "failed" in statuses
    failed_row = next(row for row in rows if row["status"] == "failed")
    assert failed_row["error_message"] is not None

    conn = sqlite3.connect(artifacts_root / "experiments.db")
    try:
        scenario_rows = conn.execute(
            "SELECT status, error_message FROM scenario_runs ORDER BY created_at ASC"
        ).fetchall()
        completed_count, failed_count = conn.execute(
            "SELECT completed_count, failed_count FROM batch_runs"
        ).fetchone()
    finally:
        conn.close()

    assert len(scenario_rows) == 2
    assert {row[0] for row in scenario_rows} == {"completed", "failed"}
    assert completed_count == 1
    assert failed_count == 1


def test_run_batch_preserves_completed_results_when_later_scenario_fails(tmp_path) -> None:
    client = MockFKPinnClient(fail_on_scenario=1)
    artifacts_root = tmp_path / "artifacts"

    run_batch(
        client=client,
        scenarios=_scenarios(2),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    batch_dir = _single_batch_dir(artifacts_root)
    scenario_dirs = sorted([path for path in batch_dir.iterdir() if path.is_dir()])
    first_result = scenario_dirs[0] / "result.json"
    second_result = scenario_dirs[1] / "result.json"
    assert first_result.exists()
    assert second_result.exists()
    with first_result.open("r", encoding="utf-8") as handle:
        first_payload = json.load(handle)
    with second_result.open("r", encoding="utf-8") as handle:
        second_payload = json.load(handle)
    observed_statuses = {first_payload["status"], second_payload["status"]}
    assert observed_statuses == {"completed", "failed"}


def test_manifest_contains_reproducibility_metadata(tmp_path) -> None:
    client = MockFKPinnClient()
    artifacts_root = tmp_path / "artifacts"

    run_batch(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    batch_dir = _single_batch_dir(artifacts_root)
    with (batch_dir / "manifest.yaml").open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)

    assert manifest["batch_run_id"] == batch_dir.name
    assert "created_at" in manifest
    assert manifest["schema_versions"]["manifest_schema_version"] == 1
    assert "python_version" in manifest["reproducibility"]
    assert "os_info" in manifest["reproducibility"]
    assert isinstance(manifest["scenarios"], list)
    assert manifest["backend_url"] == "http://mock-backend:8000"


def test_run_batch_returns_sorted_results(tmp_path) -> None:
    client = MockFKPinnClient(losses=[0.2, 0.05, 0.15, 0.1])
    artifacts_root = tmp_path / "artifacts"

    rows = run_batch(
        client=client,
        scenarios=_scenarios(4),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    scores = [row["score"] for row in rows]
    assert scores == sorted(scores)


def test_run_batch_backward_compatible(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    client = MockFKPinnClient(checkpoint_mode="inline")

    rows = run_batch(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
    )

    assert len(rows) == 1
    assert rows[0]["status"] == "completed"


def test_run_batch_persists_checkpoint_when_available(tmp_path) -> None:
    client = MockFKPinnClient(checkpoint_mode="inline")
    artifacts_root = tmp_path / "artifacts"

    rows = run_batch(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
    )

    assert rows[0]["checkpoint_path"] is not None
    checkpoint_path = Path(rows[0]["checkpoint_path"])
    assert checkpoint_path.exists()
    assert checkpoint_path.read_bytes() == b"checkpoint-bytes"


def test_run_batch_includes_manifest_hash_when_provided(tmp_path) -> None:
    client = MockFKPinnClient()
    artifacts_root = tmp_path / "artifacts"
    manifest_hash = "abc123"

    run_batch(
        client=client,
        scenarios=_scenarios(1),
        batch_config=BatchConfig(),
        artifacts_dir=artifacts_root,
        experiment_manifest_hash=manifest_hash,
    )

    batch_dir = _single_batch_dir(artifacts_root)
    with (batch_dir / "manifest.yaml").open("r", encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle)

    assert manifest["experiment_manifest_hash"] == manifest_hash


def test_generate_scenarios_from_manifest_basic() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5, 10],
                "volatilities": [0.15, 0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
        }
    )

    scenarios = generate_scenarios_from_manifest(manifest)

    assert len(scenarios) == 4


def test_generate_scenarios_from_manifest_with_model_sweep() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5, 10],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
            "model_sweep": {
                "architectures": ["default", "resmlp"],
            },
        }
    )

    scenarios = generate_scenarios_from_manifest(manifest)

    assert len(scenarios) == 4
    assert all(scenario.model_config is not None for scenario in scenarios)


def test_generate_scenarios_from_manifest_model_config_in_params() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
            "model_sweep": {
                "architectures": ["resmlp"],
                "hidden_sizes": [[128, 128]],
                "activations": ["gelu"],
                "optimizers": ["adamw"],
            },
        }
    )

    scenario = generate_scenarios_from_manifest(manifest)[0]
    params = scenario.as_parameters()

    assert "model_config" in params
    assert params["model_config"]["architecture"] == "resmlp"
    assert params["model_config"]["hidden_size"] == [128, 128]


def test_generate_scenarios_from_manifest_default_model_sweep() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
        }
    )

    scenarios = generate_scenarios_from_manifest(manifest)

    assert len(scenarios) == 1
    assert scenarios[0].model_config is not None
    assert scenarios[0].model_config["architecture"] == "default"


def test_generate_scenarios_from_manifest_correlation_matrix() -> None:
    correlation_matrix = [
        [1.0, 0.3],
        [0.3, 1.0],
    ]
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [2],
                "volatilities": [0.2],
                "correlations": correlation_matrix,
                "option_types": ["call"],
            },
        }
    )

    scenarios = generate_scenarios_from_manifest(manifest)

    assert len(scenarios) == 1
    assert scenarios[0].correlation == correlation_matrix


def test_scenario_backward_compat() -> None:
    scenario = Scenario(dim=5, volatility=0.2, correlation=0.3)

    assert scenario.option_type == "call"
    assert scenario.model_config is None


def test_generate_scenarios_from_manifest_rejects_mismatched_model_axes() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
            "model_sweep": {
                "architectures": ["default", "resmlp"],
                "hidden_sizes": [[64, 64]],
            },
        }
    )

    with pytest.raises(ValueError):
        generate_scenarios_from_manifest(manifest)


def test_generate_scenarios_from_manifest_maps_model_axes_by_index() -> None:
    manifest = ExperimentManifest.model_validate(
        {
            "backend_url": "http://localhost:8000",
            "scenario_grid": {
                "dimensions": [5],
                "volatilities": [0.2],
                "correlations": [0.0],
                "option_types": ["call"],
            },
            "model_sweep": {
                "architectures": ["default", "resmlp"],
                "hidden_sizes": [[64, 64], [128, 128]],
                "activations": ["tanh", "gelu"],
                "optimizers": ["adam", "adamw"],
            },
        }
    )

    scenarios = generate_scenarios_from_manifest(manifest)
    configs = [scenario.model_config for scenario in scenarios]

    assert len(scenarios) == 2
    assert {"architecture": "default", "hidden_size": [64, 64], "activation": "tanh", "optimizer": "adam"} in configs
    assert {"architecture": "resmlp", "hidden_size": [128, 128], "activation": "gelu", "optimizer": "adamw"} in configs
