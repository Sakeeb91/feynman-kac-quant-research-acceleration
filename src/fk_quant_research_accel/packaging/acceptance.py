"""Acceptance threshold checks for exported model packages."""

from __future__ import annotations

import math
from typing import Any

from .manifest import AcceptanceResult


def _is_finite_number(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def check_acceptance(
    metrics: dict[str, Any],
    convergence_health: str,
    checkpoint_path: str | None,
) -> AcceptanceResult:
    checks = [
        {
            "name": "convergence_healthy",
            "passed": convergence_health == "healthy",
            "actual": convergence_health,
            "expected": "healthy",
        },
        {
            "name": "loss_finite",
            "passed": _is_finite_number(metrics.get("train_loss")),
            "actual": metrics.get("train_loss"),
            "expected": "finite",
        },
        {
            "name": "score_finite",
            "passed": _is_finite_number(metrics.get("score")),
            "actual": metrics.get("score"),
            "expected": "finite",
        },
        {
            "name": "checkpoint_present",
            "passed": checkpoint_path is not None,
            "actual": checkpoint_path,
            "expected": "present",
        },
    ]
    return AcceptanceResult(passed=all(check["passed"] for check in checks), checks=checks)
