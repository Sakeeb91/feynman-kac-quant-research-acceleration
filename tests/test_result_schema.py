from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from fk_quant_research_accel.models.result import (
    CompletedScenarioResult,
    ErrorStats,
    FailedScenarioResult,
)


def _completed_payload() -> dict[str, Any]:
    return {
        "status": "completed",
        "scenario_run_id": "scenario-1",
        "batch_run_id": "batch-1",
        "simulation_id": "sim-1",
        "scenario_params": {"dim": 5, "volatility": 0.2},
        "train_loss": 0.05,
        "grad_norm": 0.12,
        "runtime_seconds": 3.5,
        "rank_score": 0.07,
    }


def _failed_payload() -> dict[str, Any]:
    return {
        "status": "failed",
        "scenario_run_id": "scenario-1",
        "batch_run_id": "batch-1",
        "scenario_params": {"dim": 5, "volatility": 0.2},
        "error_message": "backend timeout",
    }


def test_completed_result_requires_all_metrics() -> None:
    payload = _completed_payload()
    payload.pop("train_loss")

    with pytest.raises(ValidationError):
        CompletedScenarioResult.model_validate(payload)


def test_completed_result_requires_grad_norm() -> None:
    payload = _completed_payload()
    payload.pop("grad_norm")

    with pytest.raises(ValidationError):
        CompletedScenarioResult.model_validate(payload)


def test_completed_result_requires_runtime_seconds() -> None:
    payload = _completed_payload()
    payload.pop("runtime_seconds")

    with pytest.raises(ValidationError):
        CompletedScenarioResult.model_validate(payload)


def test_completed_result_requires_rank_score() -> None:
    payload = _completed_payload()
    payload.pop("rank_score")

    with pytest.raises(ValidationError):
        CompletedScenarioResult.model_validate(payload)


def test_completed_result_accepts_full_payload() -> None:
    payload = _completed_payload()
    payload.update(
        {
            "val_loss": 0.06,
            "lr": 1e-3,
            "progress": 1.0,
            "checkpoint_path": "artifacts/model.pt",
            "extra_metrics": {"epochs": 40},
        }
    )

    result = CompletedScenarioResult.model_validate(payload)

    assert result.status == "completed"
    assert result.train_loss == pytest.approx(0.05)
    assert result.grad_norm == pytest.approx(0.12)
    assert result.extra_metrics["epochs"] == 40


def test_completed_result_error_stats_optional_fields() -> None:
    stats = ErrorStats()

    assert stats.pde_residual is None
    assert stats.boundary_error is None
    assert stats.relative_l2_error is None


def test_failed_result_requires_error_message() -> None:
    payload = _failed_payload()
    payload.pop("error_message")

    with pytest.raises(ValidationError):
        FailedScenarioResult.model_validate(payload)


def test_failed_result_metrics_optional() -> None:
    result = FailedScenarioResult.model_validate(_failed_payload())

    assert result.status == "failed"
    assert result.runtime_seconds == pytest.approx(0.0)
