from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from fk_quant_research_accel.packaging import (
    AcceptanceResult,
    ModelPackageManifest,
    PackageMetrics,
    check_acceptance,
)


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
