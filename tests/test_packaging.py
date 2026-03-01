from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from fk_quant_research_accel.packaging import (
    AcceptanceResult,
    ModelPackageManifest,
    ModelPackager,
    PackageMetrics,
    check_acceptance,
)
from fk_quant_research_accel.store.metadata import MetadataStore


def _setup_packaging_fixture(
    tmp_path: Path,
    *,
    missing_winner_checkpoint: bool = False,
    all_failed: bool = False,
) -> dict[str, Any]:
    artifacts_dir = tmp_path / "artifacts"
    db_path = tmp_path / "experiments.db"
    output_dir = tmp_path / "packages"
    batch_run_id = "11111111-1111-1111-1111-111111111111"
    winner_scenario_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    other_scenario_id = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    store = MetadataStore(db_path)
    batch_artifact_dir = artifacts_dir / batch_run_id
    batch_artifact_dir.mkdir(parents=True, exist_ok=True)

    training_config = {
        "n_steps": 40,
        "batch_size": 64,
        "n_mc_paths": 256,
        "learning_rate": 1e-3,
    }
    store.create_batch_run(
        batch_run_id=batch_run_id,
        created_at=datetime.now(UTC).isoformat(),
        config_json=json.dumps(training_config, sort_keys=True),
        manifest_schema_version=1,
        git_sha="abc123",
        git_dirty=False,
        python_version="3.12.0",
        os_info="test-os",
        seed=7,
        scenario_count=2,
        artifact_path=str(batch_artifact_dir),
        problem_id="black_scholes",
    )

    manifest_payload = {
        "batch_run_id": batch_run_id,
        "created_at": "2026-02-25T00:00:00+00:00",
        "reproducibility": {
            "git_sha": "abc123",
            "git_dirty": False,
            "python_version": "3.12.0",
            "os_info": "test-os",
            "seed": 7,
            "packages": {"pydantic": "2.12.5", "PyYAML": "6.0.3"},
        },
    }
    (batch_artifact_dir / "manifest.yaml").write_text(
        yaml.safe_dump(manifest_payload, sort_keys=True),
        encoding="utf-8",
    )

    winner_status = "failed" if all_failed else "completed"
    other_status = "failed" if all_failed else "completed"

    winner_scenario = {"dim": 5, "volatility": 0.2, "correlation": 0.0, "option_type": "call"}
    other_scenario = {"dim": 10, "volatility": 0.3, "correlation": 0.1, "option_type": "put"}

    winner_result = {
        "status": winner_status,
        "train_loss": 0.1,
        "val_loss": 0.2,
        "grad_norm": 0.3,
        "score": 0.05 if not all_failed else float("inf"),
        "convergence_health": "healthy",
        "progress": 1.0,
    }
    other_result = {
        "status": other_status,
        "train_loss": 0.2,
        "val_loss": 0.3,
        "grad_norm": 0.4,
        "score": 0.10 if not all_failed else float("inf"),
        "convergence_health": "healthy",
        "progress": 1.0,
    }

    winner_scenario_dir = batch_artifact_dir / winner_scenario_id
    winner_scenario_dir.mkdir(parents=True, exist_ok=True)
    winner_checkpoint = winner_scenario_dir / "checkpoint" / "model_checkpoint.pt"
    if not missing_winner_checkpoint and not all_failed:
        winner_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        winner_checkpoint.write_bytes(b"winner-checkpoint")

    other_scenario_dir = batch_artifact_dir / other_scenario_id
    other_scenario_dir.mkdir(parents=True, exist_ok=True)
    other_checkpoint = other_scenario_dir / "checkpoint" / "model_checkpoint.pt"
    if not all_failed:
        other_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        other_checkpoint.write_bytes(b"other-checkpoint")

    (winner_scenario_dir / "result.json").write_text(
        json.dumps(winner_result, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (other_scenario_dir / "result.json").write_text(
        json.dumps(other_result, sort_keys=True, indent=2),
        encoding="utf-8",
    )

    winner_checkpoint_path = str(winner_checkpoint) if not all_failed else None
    if missing_winner_checkpoint:
        winner_checkpoint_path = str(winner_checkpoint)
    other_checkpoint_path = str(other_checkpoint) if not all_failed else None

    store.create_scenario_run(
        scenario_run_id=winner_scenario_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps(winner_scenario, sort_keys=True),
        created_at=datetime.now(UTC).isoformat(),
    )
    store.persist_scenario_result(
        scenario_run_id=winner_scenario_id,
        status=winner_status,
        result_json=json.dumps(winner_result, sort_keys=True),
        score=None if all_failed else 0.05,
        completed_at=datetime.now(UTC).isoformat(),
        checkpoint_path=winner_checkpoint_path,
    )

    store.create_scenario_run(
        scenario_run_id=other_scenario_id,
        batch_run_id=batch_run_id,
        scenario_json=json.dumps(other_scenario, sort_keys=True),
        created_at=datetime.now(UTC).isoformat(),
    )
    store.persist_scenario_result(
        scenario_run_id=other_scenario_id,
        status=other_status,
        result_json=json.dumps(other_result, sort_keys=True),
        score=None if all_failed else 0.10,
        completed_at=datetime.now(UTC).isoformat(),
        checkpoint_path=other_checkpoint_path,
    )

    return {
        "store": store,
        "artifacts_dir": artifacts_dir,
        "output_dir": output_dir,
        "batch_run_id": batch_run_id,
        "winner_scenario_id": winner_scenario_id,
        "other_scenario_id": other_scenario_id,
        "winner_checkpoint": winner_checkpoint,
        "other_checkpoint": other_checkpoint,
    }


def test_package_metrics_accepts_partial_fields_and_is_frozen() -> None:
    metrics = PackageMetrics(
        train_loss=0.1,
        score=0.05,
        convergence_health="healthy",
    )

    assert metrics.train_loss == 0.1
    assert metrics.val_loss is None
    assert metrics.grad_norm is None
    assert metrics.progress is None

    with pytest.raises(Exception):
        metrics.score = 0.2  # type: ignore[misc]


def test_acceptance_result_schema() -> None:
    acceptance = AcceptanceResult(
        passed=True,
        checks=[
            {
                "name": "convergence_healthy",
                "passed": True,
                "actual": "healthy",
                "expected": "healthy",
            }
        ],
    )

    assert acceptance.passed is True
    assert len(acceptance.checks) == 1


def test_model_package_manifest_roundtrip_and_contents_are_relative() -> None:
    manifest = ModelPackageManifest(
        created_at=datetime(2026, 2, 25, tzinfo=UTC),
        batch_run_id="11111111-1111-1111-1111-111111111111",
        scenario_run_id="22222222-2222-2222-2222-222222222222",
        problem_id="black_scholes",
        checkpoint_file="checkpoint/model_checkpoint.pt",
        checkpoint_sha256="deadbeef",
        training_config={"n_steps": 40, "batch_size": 64},
        scenario_config={"dim": 5, "volatility": 0.2},
        seed=7,
        reproducibility={
            "git_sha": "abc123",
            "python_version": "3.12.1",
            "os_info": "test-os",
            "packages": {"pydantic": "2.0"},
        },
        metrics=PackageMetrics(
            train_loss=0.1,
            val_loss=0.2,
            grad_norm=0.3,
            score=0.05,
            convergence_health="healthy",
            progress=1.0,
        ),
        acceptance=AcceptanceResult(
            passed=True,
            checks=[
                {
                    "name": "convergence_healthy",
                    "passed": True,
                    "actual": "healthy",
                    "expected": "healthy",
                }
            ],
        ),
        contents=[
            "checkpoint/model_checkpoint.pt",
            "config/training_config.yaml",
            "environment/reproducibility.yaml",
            "validation/acceptance.yaml",
        ],
    )

    dumped = manifest.model_dump(mode="json")
    restored = ModelPackageManifest.model_validate(dumped)

    assert restored == manifest
    assert manifest.package_version == 1
    assert all(not Path(item).is_absolute() for item in manifest.contents)

    with pytest.raises(Exception):
        manifest.problem_id = "harmonic_oscillator"  # type: ignore[misc]


def test_check_acceptance_healthy_passes() -> None:
    result = check_acceptance(
        metrics={"train_loss": 0.1, "score": 0.05},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )

    assert result.passed is True
    assert [check["name"] for check in result.checks] == [
        "convergence_healthy",
        "loss_finite",
        "score_finite",
        "checkpoint_present",
    ]
    assert all(check["passed"] is True for check in result.checks)


def test_check_acceptance_unhealthy_convergence_fails() -> None:
    result = check_acceptance(
        metrics={"train_loss": 0.1, "score": 0.05},
        convergence_health="oscillating",
        checkpoint_path="/tmp/checkpoint.pt",
    )

    assert result.passed is False
    convergence = next(check for check in result.checks if check["name"] == "convergence_healthy")
    assert convergence["passed"] is False


def test_check_acceptance_non_finite_loss_fails() -> None:
    result_none = check_acceptance(
        metrics={"train_loss": None, "score": 0.05},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )
    result_inf = check_acceptance(
        metrics={"train_loss": float("inf"), "score": 0.05},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )

    assert result_none.passed is False
    assert result_inf.passed is False
    assert next(check for check in result_none.checks if check["name"] == "loss_finite")["passed"] is False
    assert next(check for check in result_inf.checks if check["name"] == "loss_finite")["passed"] is False


def test_check_acceptance_non_finite_score_fails() -> None:
    result_none = check_acceptance(
        metrics={"train_loss": 0.1, "score": None},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )
    result_inf = check_acceptance(
        metrics={"train_loss": 0.1, "score": float("inf")},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )

    assert result_none.passed is False
    assert result_inf.passed is False
    assert next(check for check in result_none.checks if check["name"] == "score_finite")["passed"] is False
    assert next(check for check in result_inf.checks if check["name"] == "score_finite")["passed"] is False


def test_check_acceptance_checkpoint_presence() -> None:
    missing_checkpoint = check_acceptance(
        metrics={"train_loss": 0.1, "score": 0.05},
        convergence_health="healthy",
        checkpoint_path=None,
    )
    present_checkpoint = check_acceptance(
        metrics={"train_loss": 0.1, "score": 0.05},
        convergence_health="healthy",
        checkpoint_path="/tmp/checkpoint.pt",
    )

    missing_check = next(
        check for check in missing_checkpoint.checks if check["name"] == "checkpoint_present"
    )
    present_check = next(
        check for check in present_checkpoint.checks if check["name"] == "checkpoint_present"
    )

    assert missing_checkpoint.passed is False
    assert missing_check["passed"] is False
    assert present_checkpoint.passed is True
    assert present_check["passed"] is True


def test_packager_exports_winning_scenario(tmp_path: Path) -> None:
    context = _setup_packaging_fixture(tmp_path)
    store = context["store"]
    try:
        packager = ModelPackager(store=store, artifacts_dir=context["artifacts_dir"])
        package_dir = packager.export_package(
            batch_run_id=context["batch_run_id"],
            output_dir=context["output_dir"],
        )

        expected_name = (
            f"model_pkg_{context['batch_run_id'][:8]}_{context['winner_scenario_id'][:8]}"
        )
        assert package_dir.name == expected_name

        manifest_path = package_dir / "MANIFEST.yaml"
        manifest_payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        assert manifest_payload["batch_run_id"] == context["batch_run_id"]
        assert manifest_payload["scenario_run_id"] == context["winner_scenario_id"]
        assert manifest_payload["problem_id"] == "black_scholes"

        copied_checkpoint = package_dir / "checkpoint" / "model_checkpoint.pt"
        assert copied_checkpoint.exists()
        assert copied_checkpoint.read_bytes() == context["winner_checkpoint"].read_bytes()

        training_config = yaml.safe_load(
            (package_dir / "config" / "training_config.yaml").read_text(encoding="utf-8")
        )
        assert training_config["n_steps"] == 40

        scenario_config = yaml.safe_load(
            (package_dir / "config" / "scenario_config.yaml").read_text(encoding="utf-8")
        )
        assert scenario_config["dim"] == 5

        reproducibility = yaml.safe_load(
            (package_dir / "environment" / "reproducibility.yaml").read_text(encoding="utf-8")
        )
        assert reproducibility["git_sha"] == "abc123"
        assert reproducibility["python_version"] == "3.12.0"
        assert reproducibility["os_info"] == "test-os"

        assert (package_dir / "environment" / "seed.txt").read_text(encoding="utf-8").strip() == "7"

        metrics = yaml.safe_load((package_dir / "validation" / "metrics.yaml").read_text(encoding="utf-8"))
        assert metrics["score"] == pytest.approx(0.05)

        acceptance = yaml.safe_load(
            (package_dir / "validation" / "acceptance.yaml").read_text(encoding="utf-8")
        )
        assert acceptance["passed"] is True

        readme = (package_dir / "README.txt").read_text(encoding="utf-8")
        assert context["batch_run_id"] in readme
        assert context["winner_scenario_id"] in readme
    finally:
        store.close()


def test_packager_missing_checkpoint(tmp_path: Path) -> None:
    context = _setup_packaging_fixture(tmp_path, missing_winner_checkpoint=True)
    store = context["store"]
    try:
        packager = ModelPackager(store=store, artifacts_dir=context["artifacts_dir"])
        package_dir = packager.export_package(
            batch_run_id=context["batch_run_id"],
            output_dir=context["output_dir"],
        )

        checkpoint_dir = package_dir / "checkpoint"
        assert not checkpoint_dir.exists() or not any(checkpoint_dir.iterdir())

        manifest_payload = yaml.safe_load((package_dir / "MANIFEST.yaml").read_text(encoding="utf-8"))
        assert manifest_payload["checkpoint_file"] is None

        acceptance_payload = yaml.safe_load(
            (package_dir / "validation" / "acceptance.yaml").read_text(encoding="utf-8")
        )
        assert acceptance_payload["passed"] is False
        checkpoint_check = next(
            check
            for check in acceptance_payload["checks"]
            if check["name"] == "checkpoint_present"
        )
        assert checkpoint_check["passed"] is False
    finally:
        store.close()


def test_packager_specific_scenario(tmp_path: Path) -> None:
    context = _setup_packaging_fixture(tmp_path)
    store = context["store"]
    try:
        packager = ModelPackager(store=store, artifacts_dir=context["artifacts_dir"])
        package_dir = packager.export_package(
            batch_run_id=context["batch_run_id"],
            output_dir=context["output_dir"],
            scenario_run_id=context["other_scenario_id"],
        )

        manifest_payload = yaml.safe_load((package_dir / "MANIFEST.yaml").read_text(encoding="utf-8"))
        assert manifest_payload["scenario_run_id"] == context["other_scenario_id"]

        copied_checkpoint = package_dir / "checkpoint" / "model_checkpoint.pt"
        assert copied_checkpoint.read_bytes() == context["other_checkpoint"].read_bytes()
    finally:
        store.close()


def test_packager_no_completed_scenarios(tmp_path: Path) -> None:
    context = _setup_packaging_fixture(tmp_path, all_failed=True)
    store = context["store"]
    try:
        packager = ModelPackager(store=store, artifacts_dir=context["artifacts_dir"])
        with pytest.raises(ValueError, match="No completed scenarios"):
            packager.export_package(
                batch_run_id=context["batch_run_id"],
                output_dir=context["output_dir"],
            )
    finally:
        store.close()


def test_packager_output_dir_collision(tmp_path: Path) -> None:
    context = _setup_packaging_fixture(tmp_path)
    store = context["store"]
    try:
        packager = ModelPackager(store=store, artifacts_dir=context["artifacts_dir"])
        first = packager.export_package(
            batch_run_id=context["batch_run_id"],
            output_dir=context["output_dir"],
        )

        with pytest.raises(FileExistsError):
            packager.export_package(
                batch_run_id=context["batch_run_id"],
                output_dir=context["output_dir"],
            )

        overwritten = packager.export_package(
            batch_run_id=context["batch_run_id"],
            output_dir=context["output_dir"],
            force=True,
        )

        assert overwritten == first
        assert overwritten.exists()
    finally:
        store.close()
