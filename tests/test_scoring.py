from __future__ import annotations

from fk_quant_research_accel.models import ConvergenceHealth
from fk_quant_research_accel.models.experiment import ScoringConfig
from fk_quant_research_accel.models.result import CompletedScenarioResult


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
