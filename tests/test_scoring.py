from __future__ import annotations

import math

import pytest

from fk_quant_research_accel.models import ConvergenceHealth
from fk_quant_research_accel.models.experiment import ScoringConfig
from fk_quant_research_accel.models.enums import ScoringStrategy
from fk_quant_research_accel.models.result import CompletedScenarioResult
from fk_quant_research_accel.scoring.registry import get_scorer


def test_convergence_health_enum_values() -> None:
    assert [member.value for member in ConvergenceHealth] == [
        "healthy",
        "oscillating",
        "stagnating",
        "exploding",
    ]


def test_scoring_config_custom_scorer_field() -> None:
    assert ScoringConfig().custom_scorer is None
    config = ScoringConfig(custom_scorer="my.pkg.fn")
    assert config.custom_scorer == "my.pkg.fn"


def test_scoring_config_pareto_objectives_field() -> None:
    assert ScoringConfig().pareto_objectives == ["train_loss", "grad_norm"]
    config = ScoringConfig(pareto_objectives=["runtime_seconds", "train_loss"])
    assert config.pareto_objectives == ["runtime_seconds", "train_loss"]


def test_completed_result_convergence_health_field() -> None:
    payload = {
        "status": "completed",
        "scenario_run_id": "scenario-1",
        "batch_run_id": "batch-1",
        "simulation_id": "sim-1",
        "scenario_params": {"dim": 5},
        "train_loss": 0.05,
        "grad_norm": 0.12,
        "runtime_seconds": 3.5,
        "rank_score": 0.07,
        "convergence_health": "healthy",
    }

    result = CompletedScenarioResult.model_validate(payload)

    assert result.convergence_health == "healthy"
    assert CompletedScenarioResult.model_validate({
        k: v for k, v in payload.items() if k != "convergence_health"
    }).convergence_health is None


def test_get_scorer_loss_based() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.LOSS_BASED))

    score = scorer({"status": "completed", "train_loss": 0.05, "grad_norm": 1.0})

    assert score == pytest.approx(0.06)


def test_get_scorer_loss_based_custom_weight() -> None:
    scorer = get_scorer(
        ScoringConfig(strategy=ScoringStrategy.LOSS_BASED, grad_norm_weight=0.1)
    )

    score = scorer({"status": "completed", "train_loss": 0.05, "grad_norm": 1.0})

    assert score == pytest.approx(0.15)


def test_get_scorer_loss_based_failed_status() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.LOSS_BASED))

    assert scorer({"status": "failed"}) == float("inf")


def test_get_scorer_loss_based_missing_loss() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.LOSS_BASED))

    assert scorer({"status": "completed", "train_loss": None}) == float("inf")


def test_get_scorer_convergence_rate() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.CONVERGENCE_RATE))

    score = scorer(
        {
            "status": "completed",
            "train_loss": 0.1,
            "runtime_seconds": 100.0,
        }
    )

    assert score == pytest.approx(0.1 * math.log1p(100.0))


def test_get_scorer_convergence_rate_zero_runtime() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.CONVERGENCE_RATE))

    score = scorer(
        {
            "status": "completed",
            "train_loss": 0.1,
            "runtime_seconds": 0,
        }
    )

    assert score == pytest.approx(0.1 * math.log1p(1.0))


def test_get_scorer_pareto_placeholder() -> None:
    scorer = get_scorer(ScoringConfig(strategy=ScoringStrategy.PARETO_MULTI_OBJECTIVE))

    score = scorer({"status": "completed", "train_loss": 0.123})

    assert score == pytest.approx(0.123)


def test_get_scorer_unknown_strategy() -> None:
    config = ScoringConfig.model_construct(
        strategy="not_registered",
        grad_norm_weight=0.01,
        custom_scorer=None,
        pareto_objectives=["train_loss", "grad_norm"],
    )

    with pytest.raises(ValueError):
        get_scorer(config)
