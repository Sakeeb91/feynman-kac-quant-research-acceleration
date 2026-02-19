from __future__ import annotations

import uuid
from datetime import UTC, datetime

import yaml

from fk_quant_research_accel.models import (
    ManifestMetadata,
    ReproducibilityInfo,
    RunManifest,
    ScenarioStatus,
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
