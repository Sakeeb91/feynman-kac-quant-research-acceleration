"""Concurrent async orchestrator for durable batch execution."""

from __future__ import annotations

import base64
import json
import random
import time
from collections.abc import Awaitable
from collections.abc import Callable
from datetime import datetime
from datetime import timezone
from functools import partial
from pathlib import Path
from typing import Any
from typing import TypeVar

import anyio
import httpx
import structlog
from anyio import CapacityLimiter
from anyio import create_task_group
from tenacity import AsyncRetrying
from tenacity import stop_after_attempt
from tenacity import wait_exponential_jitter

from .async_client import AsyncFKPinnClient
from .models import ReproducibilityInfo
from .models import RunManifest
from .models import ScenarioStatus
from .models import capture_environment
from .models import capture_git_info
from .models import generate_batch_run_id
from .models import generate_scenario_run_id
from .models import write_manifest
from .orchestrator import BatchConfig
from .orchestrator import Scenario
from .reporting import compute_score
from .retry import RETRY_DEFAULTS
from .retry import is_retryable_error
from .store import ArtifactStore
from .store import MetadataStore


T = TypeVar("T")
TERMINAL_STATUSES = {
    ScenarioStatus.COMPLETED.value,
    ScenarioStatus.FAILED.value,
    ScenarioStatus.CANCELLED.value,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _known_statuses() -> set[str]:
    return {status.value for status in ScenarioStatus}


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
        "error_message": error_message,
        "checkpoint_path": None,
    }


async def _run_store(call: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    return await anyio.to_thread.run_sync(partial(call, *args, **kwargs))


async def _fetch_checkpoint(
    simulation_id: str,
    result_item: dict[str, Any],
    scenario_dir: Path,
    artifact_store: ArtifactStore,
) -> Path | None:
    checkpoint_dir = scenario_dir / "checkpoint"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = checkpoint_dir / "model_checkpoint.pt"
    log = structlog.get_logger().bind(simulation_id=simulation_id)
    checkpoint_url = result_item.get("checkpoint_url")
    checkpoint_inline = result_item.get("checkpoint")

    try:
        if checkpoint_url:
            async with httpx.AsyncClient(timeout=30.0) as download_client:
                response = await download_client.get(str(checkpoint_url))
                response.raise_for_status()
                await _run_store(artifact_store.atomic_write_bytes, checkpoint_path, response.content)
            return checkpoint_path

        if checkpoint_inline:
            decoded = base64.b64decode(checkpoint_inline)
            await _run_store(artifact_store.atomic_write_bytes, checkpoint_path, decoded)
            return checkpoint_path

        log.debug("checkpoint_not_available")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("checkpoint_fetch_failed", error=str(exc))
        return None


async def _retry_call(
    op: Callable[[], Awaitable[T]],
    *,
    max_retries: int,
) -> tuple[T, int]:
    attempts = 0
    max_attempts = max(1, max_retries)
    retrying = AsyncRetrying(
        wait=wait_exponential_jitter(
            initial=float(RETRY_DEFAULTS["initial_wait"]),
            max=float(RETRY_DEFAULTS["max_wait"]),
            jitter=float(RETRY_DEFAULTS["jitter"]),
        ),
        stop=stop_after_attempt(max_attempts),
        retry=lambda retry_state: (
            retry_state.outcome is not None
            and retry_state.outcome.failed
            and is_retryable_error(retry_state.outcome.exception())
        ),
        reraise=True,
    )
    async for attempt in retrying:
        with attempt:
            attempts += 1
            value = await op()
    return value, attempts


async def _submit_and_poll_scenario(
    *,
    client: AsyncFKPinnClient,
    store: MetadataStore,
    artifact_store: ArtifactStore,
    scenario: Scenario,
    scenario_run_id: str,
    scenario_dir: Path,
    batch_config: BatchConfig,
    poll_seconds: float,
    max_wait_seconds: float,
    max_retries: int,
) -> dict[str, Any]:
    simulation_response, submit_attempts = await _retry_call(
        lambda: client.create_simulation(
            problem_id="black_scholes",
            parameters=scenario.as_parameters(),
            training_config=batch_config.to_payload(),
        ),
        max_retries=max_retries,
    )
    simulation_id = str(simulation_response.get("id", ""))
    await _run_store(
        store.update_scenario_status,
        scenario_run_id,
        ScenarioStatus.SUBMITTED.value,
        simulation_id,
        _now_iso(),
    )
    await _run_store(
        store.update_scenario_retry_count,
        scenario_run_id,
        max(0, submit_attempts - 1),
    )
    retry_count = max(0, submit_attempts - 1)
    deadline = time.monotonic() + max_wait_seconds
    latest_simulation: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_simulation, poll_attempts = await _retry_call(
            lambda: client.get_simulation(simulation_id),
            max_retries=max_retries,
        )
        retry_count = max(retry_count, poll_attempts - 1)
        await _run_store(store.update_scenario_retry_count, scenario_run_id, retry_count)
        status = str(latest_simulation.get("status", ScenarioStatus.RUNNING.value))
        if status in TERMINAL_STATUSES:
            break
        jitter = random.uniform(0.0, poll_seconds * 0.3) if poll_seconds > 0 else 0.0
        await anyio.sleep(poll_seconds + jitter)
    else:
        raise TimeoutError(
            f"Simulation {simulation_id} did not finish within {max_wait_seconds} seconds"
        )

    result_envelope, result_attempts = await _retry_call(
        lambda: client.get_result(simulation_id),
        max_retries=max_retries,
    )
    retry_count = max(retry_count, result_attempts - 1)
    await _run_store(store.update_scenario_retry_count, scenario_run_id, retry_count)

    result_item = result_envelope.get("item") or {}
    metrics = result_item.get("metrics") or {}
    status = str(latest_simulation.get("status", ScenarioStatus.COMPLETED.value))
    if status not in _known_statuses():
        status = ScenarioStatus.COMPLETED.value

    record = {
        "simulation_id": simulation_id,
        "status": status,
        "dim": scenario.dim,
        "volatility": scenario.volatility,
        "correlation": scenario.correlation,
        "option_type": scenario.option_type,
        "progress": result_item.get("progress", 0.0),
        "train_loss": metrics.get("loss", metrics.get("train_loss")),
        "val_loss": metrics.get("val_loss"),
        "lr": metrics.get("lr"),
        "grad_norm": metrics.get("grad_norm"),
        "error_message": result_item.get("error"),
        "checkpoint_path": None,
    }
    record["score"] = compute_score(record)
    completed_at = _now_iso()

    checkpoint_path = await _fetch_checkpoint(
        simulation_id=simulation_id,
        result_item=result_item,
        scenario_dir=scenario_dir,
        artifact_store=artifact_store,
    )
    if checkpoint_path is not None:
        record["checkpoint_path"] = str(checkpoint_path)

    await _run_store(
        store.persist_scenario_result,
        scenario_run_id,
        record["status"],
        json.dumps(record, sort_keys=True),
        record["score"],
        record["error_message"],
        completed_at,
        record["checkpoint_path"],
    )
    await _run_store(artifact_store.atomic_write_json, scenario_dir / "result.json", record)
    return record


async def _execute_scenario_safe(
    *,
    client: AsyncFKPinnClient,
    store: MetadataStore,
    artifact_store: ArtifactStore,
    scenario: Scenario,
    scenario_run_id: str,
    scenario_dir: Path,
    batch_config: BatchConfig,
    poll_seconds: float,
    max_wait_seconds: float,
    limiter: CapacityLimiter,
    max_retries: int,
    results: list[dict[str, Any]],
) -> None:
    log = structlog.get_logger().bind(scenario_run_id=scenario_run_id)
    async with limiter:
        simulation_id = ""
        try:
            record = await _submit_and_poll_scenario(
                client=client,
                store=store,
                artifact_store=artifact_store,
                scenario=scenario,
                scenario_run_id=scenario_run_id,
                scenario_dir=scenario_dir,
                batch_config=batch_config,
                poll_seconds=poll_seconds,
                max_wait_seconds=max_wait_seconds,
                max_retries=max_retries,
            )
            simulation_id = str(record["simulation_id"])
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            record = _build_failure_record(scenario, simulation_id, error_message)
            await _run_store(
                store.persist_scenario_result,
                scenario_run_id,
                ScenarioStatus.FAILED.value,
                json.dumps(record, sort_keys=True),
                record["score"],
                error_message,
                _now_iso(),
                None,
            )
            await _run_store(artifact_store.atomic_write_json, scenario_dir / "result.json", record)
            log.error("scenario_failed", error=error_message, exc_info=True)
    results.append(record)


async def _execute_scenarios_concurrent(
    *,
    client: AsyncFKPinnClient,
    store: MetadataStore,
    artifact_store: ArtifactStore,
    batch_config: BatchConfig,
    execution_items: list[tuple[Scenario, str, Path]],
    poll_seconds: float,
    max_wait_seconds: float,
    concurrency_limit: int,
    max_retries: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    limiter = CapacityLimiter(concurrency_limit)
    async with create_task_group() as task_group:
        for scenario, scenario_run_id, scenario_dir in execution_items:
            task_group.start_soon(
                partial(
                    _execute_scenario_safe,
                    client=client,
                    store=store,
                    artifact_store=artifact_store,
                    scenario=scenario,
                    scenario_run_id=scenario_run_id,
                    scenario_dir=scenario_dir,
                    batch_config=batch_config,
                    poll_seconds=poll_seconds,
                    max_wait_seconds=max_wait_seconds,
                    limiter=limiter,
                    max_retries=max_retries,
                    results=results,
                )
            )
    return results


async def run_batch_async(
    client: AsyncFKPinnClient,
    scenarios: list[Scenario],
    batch_config: BatchConfig,
    poll_seconds: float = 2.0,
    max_wait_seconds: float = 1800.0,
    concurrency_limit: int = 20,
    max_retries: int = 3,
    artifacts_dir: str | Path = "artifacts",
    db_path: str | Path | None = None,
    seed: int | None = None,
    experiment_manifest_hash: str | None = None,
) -> list[dict[str, Any]]:
    batch_run_id = str(generate_batch_run_id())
    log = structlog.get_logger().bind(batch_run_id=batch_run_id)
    artifact_store = ArtifactStore(artifacts_dir)
    batch_dir = artifact_store.create_batch_dir(batch_run_id)
    effective_db_path = Path(db_path) if db_path is not None else artifact_store.root / "experiments.db"
    store: MetadataStore | None = None
    try:
        store = MetadataStore(effective_db_path)
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
        await _run_store(
            store.create_batch_run,
            batch_run_id,
            manifest.created_at.isoformat(),
            json.dumps(batch_config.to_payload(), sort_keys=True),
            manifest.schema_versions.manifest_schema_version,
            git_sha,
            git_dirty,
            environment["python_version"],
            environment["os_info"],
            seed,
            len(scenarios),
            str(batch_dir),
            concurrency_limit,
        )
        log.info(
            "batch_started",
            scenario_count=len(scenarios),
            artifact_dir=str(batch_dir),
            manifest_path=str(manifest_path),
        )
        execution_items: list[tuple[Scenario, str, Path]] = []
        for scenario in scenarios:
            scenario_run_id = str(generate_scenario_run_id())
            scenario_dir = artifact_store.create_scenario_dir(batch_run_id, scenario_run_id)
            await _run_store(
                store.create_scenario_run,
                scenario_run_id,
                batch_run_id,
                json.dumps(scenario.as_parameters(), sort_keys=True),
                _now_iso(),
            )
            execution_items.append((scenario, scenario_run_id, scenario_dir))

        async with client:
            records = await _execute_scenarios_concurrent(
                client=client,
                store=store,
                artifact_store=artifact_store,
                batch_config=batch_config,
                execution_items=execution_items,
                poll_seconds=poll_seconds,
                max_wait_seconds=max_wait_seconds,
                concurrency_limit=concurrency_limit,
                max_retries=max_retries,
            )

        await _run_store(store.update_batch_status, batch_run_id, "completed")
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
        if store is not None:
            await _run_store(store.close)


async def resume_batch_async(
    client: AsyncFKPinnClient,
    batch_run_id: str,
    concurrency_limit: int = 20,
    max_retries: int = 3,
    poll_seconds: float = 2.0,
    max_wait_seconds: float = 1800.0,
    force: bool = False,
    db_path: str | Path | None = None,
    artifacts_dir: str | Path = "artifacts",
) -> list[dict[str, Any]]:
    log = structlog.get_logger().bind(batch_run_id=batch_run_id)
    artifact_store = ArtifactStore(artifacts_dir)
    effective_db_path = Path(db_path) if db_path is not None else artifact_store.root / "experiments.db"
    store: MetadataStore | None = None
    try:
        store = MetadataStore(effective_db_path)
        batch_row = await _run_store(store.get_batch_run, batch_run_id)
        if batch_row is None:
            raise ValueError(f"Batch run '{batch_run_id}' not found")

        if force:
            scenario_rows = await _run_store(store.get_scenario_runs, batch_run_id)
        else:
            scenario_rows = await _run_store(store.get_incomplete_scenario_runs, batch_run_id)
        if not scenario_rows:
            log.info("resume_no_work")
            return []

        config_json = str(batch_row.get("config_json", "{}"))
        config_payload = json.loads(config_json)
        batch_config = BatchConfig(**config_payload)

        execution_items: list[tuple[Scenario, str, Path]] = []
        for row in scenario_rows:
            scenario_run_id = str(row["scenario_run_id"])
            scenario_payload = json.loads(str(row["scenario_json"]))
            scenario = Scenario(**scenario_payload)
            scenario_dir = artifact_store.get_scenario_dir(batch_run_id, scenario_run_id)
            scenario_dir.mkdir(parents=True, exist_ok=True)
            execution_items.append((scenario, scenario_run_id, scenario_dir))

        async with client:
            records = await _execute_scenarios_concurrent(
                client=client,
                store=store,
                artifact_store=artifact_store,
                batch_config=batch_config,
                execution_items=execution_items,
                poll_seconds=poll_seconds,
                max_wait_seconds=max_wait_seconds,
                concurrency_limit=concurrency_limit,
                max_retries=max_retries,
            )

        await _run_store(store.update_batch_status, batch_run_id, "completed")
        completed_count = sum(1 for row in records if row["status"] == ScenarioStatus.COMPLETED.value)
        failed_count = len(records) - completed_count
        log.info(
            "resume_completed",
            resumed=len(records),
            completed=completed_count,
            failed=failed_count,
            force=force,
        )
        return sorted(records, key=lambda row: row["score"])
    finally:
        if store is not None:
            await _run_store(store.close)
