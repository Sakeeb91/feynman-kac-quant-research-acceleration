from __future__ import annotations

import uuid
from datetime import UTC, datetime

import yaml

from fk_quant_research_accel.models import (
    ManifestMetadata,
    ReproducibilityInfo,
    RunManifest,
    ScenarioResult,
    ScenarioStatus,
    capture_environment,
    capture_git_info,
    generate_batch_run_id,
    generate_scenario_run_id,
    write_manifest,
)


def test_generate_batch_run_id_is_uuid_and_unique() -> None:
    first = generate_batch_run_id()
    second = generate_batch_run_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    uuid.UUID(first)
    uuid.UUID(second)
    assert first != second


def test_generate_scenario_run_id_is_uuid_and_unique() -> None:
    first = generate_scenario_run_id()
    second = generate_scenario_run_id()

    assert isinstance(first, str)
    assert isinstance(second, str)
    uuid.UUID(first)
    uuid.UUID(second)
    assert first != second


def test_scenario_status_values_match_contract() -> None:
    assert ScenarioStatus.PENDING.value == "pending"
    assert ScenarioStatus.SUBMITTED.value == "submitted"
    assert ScenarioStatus.RUNNING.value == "running"
    assert ScenarioStatus.COMPLETED.value == "completed"
    assert ScenarioStatus.FAILED.value == "failed"
    assert ScenarioStatus.CANCELLED.value == "cancelled"


def _build_manifest() -> RunManifest:
    return RunManifest(
        batch_run_id=str(generate_batch_run_id()),
        created_at=datetime.now(UTC),
        schema_versions=ManifestMetadata(),
        reproducibility=ReproducibilityInfo(
            git_sha="abc123",
            git_dirty=False,
            python_version="3.12.0",
            os_info="test-os",
            seed=42,
            packages={"pytest": "8.0.0"},
        ),
        batch_config={"n_steps": 20},
        scenarios=[{"dim": 5, "volatility": 0.2, "correlation": 0.0, "option_type": "call"}],
        backend_url="http://localhost:8000",
    )


def test_manifest_model_dump_roundtrip() -> None:
    manifest = _build_manifest()
    dumped = manifest.model_dump(mode="json")
    restored = RunManifest.model_validate(dumped)
    assert restored == manifest


def test_write_manifest_produces_yaml(tmp_path) -> None:
    manifest = _build_manifest()
    path = write_manifest(manifest, tmp_path)

    assert path.exists()
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)

    assert loaded["batch_run_id"] == manifest.batch_run_id
    assert loaded["schema_versions"]["manifest_schema_version"] == 1


def test_scenario_result_supports_full_and_minimal_payloads() -> None:
    full = ScenarioResult(
        scenario_run_id=str(generate_scenario_run_id()),
        batch_run_id=str(generate_batch_run_id()),
        simulation_id="sim-1",
        status=ScenarioStatus.COMPLETED,
        scenario_params={"dim": 10},
        train_loss=0.1,
        val_loss=0.12,
        grad_norm=0.3,
        lr=1e-3,
        progress=1.0,
        score=0.11,
        error_message=None,
        checkpoint_path="checkpoint/model.pt",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        extra_metrics={"foo": 1},
    )
    assert full.status == ScenarioStatus.COMPLETED
    assert full.extra_metrics["foo"] == 1

    minimal = ScenarioResult(
        scenario_run_id=str(generate_scenario_run_id()),
        batch_run_id=str(generate_batch_run_id()),
        status=ScenarioStatus.PENDING,
        scenario_params={"dim": 5},
    )
    assert minimal.progress == 0.0
    assert minimal.train_loss is None


def test_capture_git_info_type_contract() -> None:
    git_sha, git_dirty = capture_git_info()
    assert git_sha is None or isinstance(git_sha, str)
    assert git_dirty is None or isinstance(git_dirty, bool)


def test_capture_environment_contains_required_keys() -> None:
    environment = capture_environment()
    assert "python_version" in environment
    assert "os_info" in environment
    assert isinstance(environment["packages"], dict)
