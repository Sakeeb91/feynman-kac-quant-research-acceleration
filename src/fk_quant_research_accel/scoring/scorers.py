"""Built-in scoring implementations."""

from __future__ import annotations

import math
from typing import Any

from fk_quant_research_accel.models.enums import ScoringStrategy
from fk_quant_research_accel.scoring.registry import register_scorer


@register_scorer(ScoringStrategy.LOSS_BASED)
def score_loss_based(record: dict[str, Any], *, grad_norm_weight: float = 0.01) -> float:
    train_loss = record.get("train_loss")
    grad_norm = record.get("grad_norm")
    status = record.get("status")

    if status != "completed":
        return float("inf")
    if train_loss is None:
        return float("inf")

    grad_penalty = 0.0 if grad_norm is None else abs(float(grad_norm)) * grad_norm_weight
    return float(train_loss) + grad_penalty


@register_scorer(ScoringStrategy.CONVERGENCE_RATE)
def score_convergence_rate(record: dict[str, Any]) -> float:
    train_loss = record.get("train_loss")
    status = record.get("status")
    runtime_seconds = record.get("runtime_seconds")

    if status != "completed" or train_loss is None:
        return float("inf")

    runtime = 1.0
    if runtime_seconds is not None:
        runtime = max(1.0, float(runtime_seconds))

    return float(train_loss) * math.log1p(runtime)


@register_scorer(ScoringStrategy.PARETO_MULTI_OBJECTIVE)
def score_pareto_placeholder(record: dict[str, Any]) -> float:
    status = record.get("status")
    train_loss = record.get("train_loss")
    if status != "completed" or train_loss is None:
        return float("inf")
    return float(train_loss)
