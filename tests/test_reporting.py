from fk_quant_research_accel.orchestrator import generate_black_scholes_scenarios
from fk_quant_research_accel.reporting import compute_score


def test_generate_black_scholes_scenarios_cross_product() -> None:
    scenarios = generate_black_scholes_scenarios(
        dimensions=[5, 10],
        volatilities=[0.15, 0.2],
        correlations=[0.0, 0.3],
        option_types=["call", "put"],
    )
    assert len(scenarios) == 16


def test_compute_score_completed_has_finite_value() -> None:
    score = compute_score({"status": "completed", "train_loss": 0.2, "grad_norm": 1.0})
    assert score > 0.0
    assert score < 1.0


def test_compute_score_non_completed_is_infinite() -> None:
    score = compute_score({"status": "failed", "train_loss": 0.2, "grad_norm": 1.0})
    assert score == float("inf")
