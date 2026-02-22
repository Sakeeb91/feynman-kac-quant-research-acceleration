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
