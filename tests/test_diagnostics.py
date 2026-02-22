from __future__ import annotations

from fk_quant_research_accel.diagnostics.health import diagnose_convergence
from fk_quant_research_accel.models import ConvergenceHealth


def test_diagnose_exploding_nan_loss() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": float("nan")})

    assert health == ConvergenceHealth.EXPLODING


def test_diagnose_exploding_inf_loss() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": float("inf")})

    assert health == ConvergenceHealth.EXPLODING


def test_diagnose_exploding_huge_grad_norm() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": 0.2, "grad_norm": 1e7})

    assert health == ConvergenceHealth.EXPLODING


def test_diagnose_exploding_failed_status() -> None:
    health = diagnose_convergence({"status": "failed", "train_loss": 0.2, "grad_norm": 0.1})

    assert health == ConvergenceHealth.EXPLODING


def test_diagnose_stagnating_high_loss_tiny_grad() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": 5.0, "grad_norm": 1e-8})

    assert health == ConvergenceHealth.STAGNATING


def test_diagnose_oscillating_val_loss_gap() -> None:
    health = diagnose_convergence(
        {
            "status": "completed",
            "train_loss": 0.05,
            "val_loss": 0.2,
        }
    )

    assert health == ConvergenceHealth.OSCILLATING


def test_diagnose_oscillating_large_grad_norm() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": 0.05, "grad_norm": 15.0})

    assert health == ConvergenceHealth.OSCILLATING


def test_diagnose_healthy_low_loss_moderate_grad() -> None:
    health = diagnose_convergence({"status": "completed", "train_loss": 0.01, "grad_norm": 0.5})

    assert health == ConvergenceHealth.HEALTHY


def test_diagnose_healthy_no_metrics() -> None:
    health = diagnose_convergence({"status": "completed"})

    assert health == ConvergenceHealth.HEALTHY


def test_diagnose_from_history_exploding() -> None:
    health = diagnose_convergence(
        {
            "status": "completed",
            "extra_metrics": {
                "loss_history": [0.5, 0.3, float("nan"), 0.1, 0.05],
            },
        }
    )

    assert health == ConvergenceHealth.EXPLODING


def test_diagnose_from_history_stagnating() -> None:
    health = diagnose_convergence(
        {
            "status": "completed",
            "extra_metrics": {
                "loss_history": [1.0] * 20,
            },
        }
    )

    assert health == ConvergenceHealth.STAGNATING


def test_diagnose_from_history_oscillating() -> None:
    health = diagnose_convergence(
        {
            "status": "completed",
            "extra_metrics": {
                "loss_history": [0.1, 1.0, 0.1, 1.0, 0.1, 1.0, 0.1, 1.0, 0.1, 1.0],
            },
        }
    )

    assert health == ConvergenceHealth.OSCILLATING


def test_diagnose_from_history_healthy() -> None:
    health = diagnose_convergence(
        {
            "status": "completed",
            "extra_metrics": {
                "loss_history": [1.0, 0.5, 0.3, 0.2, 0.15, 0.1, 0.08, 0.06, 0.05, 0.04],
            },
        }
    )

    assert health == ConvergenceHealth.HEALTHY
