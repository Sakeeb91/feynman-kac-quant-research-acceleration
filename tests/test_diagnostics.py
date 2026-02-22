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
