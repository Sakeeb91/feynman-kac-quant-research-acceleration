"""Scenario generation and durable batch execution for quant experiments."""

from __future__ import annotations

import base64
import json
import itertools
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from typing import cast

import requests
import structlog

from .client import FKPinnClient
from .diagnostics.health import diagnose_convergence
from .models import (
    ExperimentManifest,
    ReproducibilityInfo,
    RunManifest,
    ScoringConfig,
    ScoringStrategy,
    ScenarioStatus,
    capture_environment,
    capture_git_info,
    generate_batch_run_id,
    generate_scenario_run_id,
    write_manifest,
)
from .scoring.pareto import assign_pareto_scores
from .scoring.registry import get_scorer
from .store import ArtifactStore, MetadataStore


@dataclass(frozen=True)
class Scenario:
    dim: int
    volatility: float
    correlation: float | list[list[float]]
    option_type: str = "call"
    model_config: dict[str, Any] | None = None

    def as_parameters(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "dim": self.dim,
            "volatility": self.volatility,
            "correlation": self.correlation,
            "option_type": self.option_type,
        }
        if self.model_config is not None:
            params["model_config"] = self.model_config
        return params


@dataclass(frozen=True)
class BatchConfig:
    n_steps: int = 40
    batch_size: int = 64
    n_mc_paths: int = 256
    learning_rate: float = 1e-3

    def to_payload(self) -> dict[str, Any]:
        return {
            "n_steps": self.n_steps,
            "batch_size": self.batch_size,
            "n_mc_paths": self.n_mc_paths,
            "learning_rate": self.learning_rate,
        }


def generate_black_scholes_scenarios(
    dimensions: list[int],
    volatilities: list[float],
    correlations: list[float],
    option_types: list[str] | None = None,
) -> list[Scenario]:
    if option_types is None:
        option_types = ["call"]
    scenarios = [
        Scenario(dim=d, volatility=v, correlation=c, option_type=o)
        for d, v, c, o in itertools.product(dimensions, volatilities, correlations, option_types)
    ]
    return scenarios


def _validate_model_sweep_axis_lengths(manifest: ExperimentManifest) -> None:
    architectures = manifest.model_sweep.architectures
    expected = len(architectures)
    axis_map: dict[str, list[Any] | None] = {
        "hidden_sizes": manifest.model_sweep.hidden_sizes,
        "activations": manifest.model_sweep.activations,
        "optimizers": manifest.model_sweep.optimizers,
    }
    for axis_name, axis_values in axis_map.items():
        if axis_values is None:
            continue
        if len(axis_values) != expected:
            raise ValueError(
                f"model_sweep.{axis_name} must match architectures length "
                f"({expected}), got {len(axis_values)}."
            )


def _build_model_configs(manifest: ExperimentManifest) -> list[dict[str, Any]]:
    _validate_model_sweep_axis_lengths(manifest)
    configs: list[dict[str, Any]] = []
    architectures = manifest.model_sweep.architectures

    for index, architecture in enumerate(architectures):
        config: dict[str, Any] = {"architecture": architecture}
        if manifest.model_sweep.hidden_sizes is not None:
            config["hidden_size"] = manifest.model_sweep.hidden_sizes[index]
        if manifest.model_sweep.activations is not None:
            config["activation"] = manifest.model_sweep.activations[index]
        if manifest.model_sweep.optimizers is not None:
            config["optimizer"] = manifest.model_sweep.optimizers[index]
        configs.append(config)

    return configs


def generate_scenarios_from_manifest(manifest: ExperimentManifest) -> list[Scenario]:
    correlations = manifest.scenario_grid.correlations
    if correlations and isinstance(correlations[0], list):
        correlation_axis: tuple[float | list[list[float]], ...] = (
            cast(list[list[float]], correlations),
        )
    else:
        correlation_axis = tuple(cast(list[float], correlations))

    model_configs = _build_model_configs(manifest)
    scenarios: list[Scenario] = []
    for dim, volatility, correlation, option_type, model_config in itertools.product(
        manifest.scenario_grid.dimensions,
        manifest.scenario_grid.volatilities,
        correlation_axis,
        manifest.scenario_grid.option_types,
        model_configs,
    ):
        scenarios.append(
            Scenario(
                dim=dim,
                volatility=volatility,
                correlation=correlation,
                option_type=getattr(option_type, "value", option_type),
                model_config=dict(model_config),
            )
        )
    return scenarios


def _build_failure_record(
    scenario: Scenario,
    simulation_id: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "simulation_id": simulation_id,
        "status": ScenarioStatus.FAILED.value,
        "dim": scenario.dim,
        "volatility": scenario.volatility,
        "correlation": scenario.correlation,
        "option_type": scenario.option_type,
        "progress": 0.0,
        "train_loss": None,
        "val_loss": None,
        "lr": None,
        "grad_norm": None,
        "score": float("inf"),
        "convergence_health": "exploding",
        "error_message": error_message,
        "checkpoint_path": None,
    }


def _fetch_checkpoint(
    client: FKPinnClient,
    simulation_id: str,
    scenario_dir: Path,
    artifact_store: ArtifactStore | None = None,
) -> Path | None:
    log = structlog.get_logger().bind(simulation_id=simulation_id)
    checkpoint_dir = scenario_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "model_checkpoint.pt"
    if artifact_store is None:
        artifact_store = ArtifactStore(scenario_dir.parents[1])

    try:
        result_envelope = client.get_result(simulation_id)
        item = result_envelope.get("item") or {}
        checkpoint_url = item.get("checkpoint_url")
        checkpoint_inline = item.get("checkpoint")

        if checkpoint_url:
            response = requests.get(str(checkpoint_url), timeout=30.0)
            response.raise_for_status()
            artifact_store.atomic_write_bytes(checkpoint_path, response.content)
            return checkpoint_path

        if checkpoint_inline:
            artifact_store.atomic_write_bytes(checkpoint_path, base64.b64decode(checkpoint_inline))
            return checkpoint_path

        log.debug("checkpoint_not_available")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("checkpoint_fetch_failed", error=str(exc))
        return None


def run_batch(
    client: FKPinnClient,
    scenarios: list[Scenario],
    batch_config: BatchConfig,
    poll_seconds: float = 1.5,
    max_wait_seconds: float = 1800.0,
    artifacts_dir: str | Path = "artifacts",
    db_path: str | Path | None = None,
    seed: int | None = None,
    experiment_manifest_hash: str | None = None,
    scoring_config: ScoringConfig | None = None,
) -> list[dict[str, Any]]:
    """Submit all scenarios and incrementally persist terminal results."""
    effective_scoring_config = scoring_config or ScoringConfig()
    scorer = get_scorer(effective_scoring_config)
    batch_run_id = str(generate_batch_run_id())
    log = structlog.get_logger().bind(batch_run_id=batch_run_id)

    artifact_store = ArtifactStore(artifacts_dir)
    batch_dir = artifact_store.create_batch_dir(batch_run_id)
    effective_db_path = Path(db_path) if db_path is not None else artifact_store.root / "experiments.db"
    metadata_store: MetadataStore | None = None
    records: list[dict[str, Any]] = []

    try:
        metadata_store = MetadataStore(effective_db_path)
        git_sha, git_dirty = capture_git_info()
        environment = capture_environment()
        manifest = RunManifest(
            batch_run_id=batch_run_id,
            created_at=datetime.now(timezone.utc),
            reproducibility=ReproducibilityInfo(
                git_sha=git_sha,
                git_dirty=git_dirty,
                python_version=environment["python_version"],
                os_info=environment["os_info"],
                seed=seed,
                packages=environment["packages"],
            ),
            batch_config=batch_config.to_payload(),
            scenarios=[scenario.as_parameters() for scenario in scenarios],
            backend_url=client.base_url,
            experiment_manifest_hash=experiment_manifest_hash,
        )
        manifest_path = write_manifest(manifest, artifact_store.root)

        metadata_store.create_batch_run(
            batch_run_id=batch_run_id,
            created_at=manifest.created_at.isoformat(),
            config_json=json.dumps(batch_config.to_payload(), sort_keys=True),
            manifest_schema_version=manifest.schema_versions.manifest_schema_version,
            git_sha=git_sha,
            git_dirty=git_dirty,
            python_version=environment["python_version"],
            os_info=environment["os_info"],
            seed=seed,
            scenario_count=len(scenarios),
            artifact_path=str(batch_dir),
        )
        log.info(
            "batch_started",
            scenario_count=len(scenarios),
            artifact_dir=str(batch_dir),
            manifest_path=str(manifest_path),
        )

        scenario_map: list[tuple[Scenario, str, Path]] = []
        for scenario in scenarios:
            scenario_run_id = str(generate_scenario_run_id())
            scenario_dir = artifact_store.create_scenario_dir(batch_run_id, scenario_run_id)
            metadata_store.create_scenario_run(
                scenario_run_id=scenario_run_id,
                batch_run_id=batch_run_id,
                scenario_json=json.dumps(scenario.as_parameters(), sort_keys=True),
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            scenario_map.append((scenario, scenario_run_id, scenario_dir))

        submitted: list[tuple[Scenario, str, str, Path]] = []
        for scenario, scenario_run_id, scenario_dir in scenario_map:
            simulation = client.create_simulation(
                problem_id="black_scholes",
                parameters=scenario.as_parameters(),
                training_config=batch_config.to_payload(),
            )
            simulation_id = simulation["id"]
            metadata_store.update_scenario_status(
                scenario_run_id=scenario_run_id,
                status=ScenarioStatus.SUBMITTED.value,
                simulation_id=simulation_id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            submitted.append((scenario, scenario_run_id, simulation_id, scenario_dir))
            log.info(
                "scenario_submitted",
                scenario_run_id=scenario_run_id,
                simulation_id=simulation_id,
            )

        for scenario, scenario_run_id, simulation_id, scenario_dir in submitted:
            try:
                simulation = client.wait_until_terminal(
                    simulation_id=simulation_id,
                    poll_seconds=poll_seconds,
                    max_wait_seconds=max_wait_seconds,
                )
                result_envelope = client.get_result(simulation_id)
                result = result_envelope.get("item") or {}
                metrics = result.get("metrics") or {}

                status = str(simulation.get("status", ScenarioStatus.COMPLETED.value))
                if status not in {member.value for member in ScenarioStatus}:
                    status = ScenarioStatus.COMPLETED.value

                record = {
                    "simulation_id": simulation_id,
                    "status": status,
                    "dim": scenario.dim,
                    "volatility": scenario.volatility,
                    "correlation": scenario.correlation,
                    "option_type": scenario.option_type,
                    "progress": result.get("progress", 0.0),
                    "train_loss": metrics.get("loss", metrics.get("train_loss")),
                    "val_loss": metrics.get("val_loss"),
                    "lr": metrics.get("lr"),
                    "grad_norm": metrics.get("grad_norm"),
                    "error_message": result.get("error"),
                    "checkpoint_path": None,
                }
                record["score"] = scorer(record)
                record["convergence_health"] = diagnose_convergence(record).value
                completed_at = datetime.now(timezone.utc).isoformat()

                metadata_store.persist_scenario_result(
                    scenario_run_id=scenario_run_id,
                    status=record["status"],
                    result_json=json.dumps(record, sort_keys=True),
                    score=record["score"],
                    error_message=record["error_message"],
                    completed_at=completed_at,
                )
                artifact_store.atomic_write_json(scenario_dir / "result.json", record)

                checkpoint_path = _fetch_checkpoint(
                    client,
                    simulation_id,
                    scenario_dir,
                    artifact_store=artifact_store,
                )
                if checkpoint_path is not None:
                    record["checkpoint_path"] = str(checkpoint_path)
                    artifact_store.atomic_write_json(scenario_dir / "result.json", record)
                    metadata_store.persist_scenario_result(
                        scenario_run_id=scenario_run_id,
                        status=record["status"],
                        result_json=json.dumps(record, sort_keys=True),
                        score=record["score"],
                        error_message=record["error_message"],
                        completed_at=completed_at,
                        checkpoint_path=str(checkpoint_path),
                    )

                if record["status"] == ScenarioStatus.COMPLETED.value:
                    log.info(
                        "scenario_completed",
                        scenario_run_id=scenario_run_id,
                        score=record["score"],
                    )
                else:
                    log.warning(
                        "scenario_terminal_non_completed",
                        scenario_run_id=scenario_run_id,
                        simulation_status=record["status"],
                    )
            except Exception as exc:  # noqa: BLE001
                error_message = str(exc)
                record = _build_failure_record(
                    scenario=scenario,
                    simulation_id=simulation_id,
                    error_message=error_message,
                )
                completed_at = datetime.now(timezone.utc).isoformat()
                metadata_store.persist_scenario_result(
                    scenario_run_id=scenario_run_id,
                    status=ScenarioStatus.FAILED.value,
                    result_json=json.dumps(record, sort_keys=True),
                    score=record["score"],
                    error_message=error_message,
                    completed_at=completed_at,
                )
                artifact_store.atomic_write_json(scenario_dir / "result.json", record)
                log.error(
                    "scenario_failed",
                    scenario_run_id=scenario_run_id,
                    simulation_id=simulation_id,
                    error=error_message,
                    exc_info=True,
                )

            records.append(record)

        metadata_store.update_batch_status(batch_run_id, "completed")
        completed_count = sum(1 for row in records if row["status"] == ScenarioStatus.COMPLETED.value)
        failed_count = len(records) - completed_count
        log.info(
            "batch_completed",
            total=len(records),
            completed=completed_count,
            failed=failed_count,
        )
        return sorted(records, key=lambda row: row["score"])
    finally:
        if metadata_store is not None:
            metadata_store.close()
