from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from fk_quant_research_accel.models.result import CompletedScenarioResult


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
