"""Convergence health classification heuristics."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import mean, stdev
from typing import Any

from fk_quant_research_accel.models.enums import ConvergenceHealth

GRAD_NORM_EXPLODING_THRESHOLD = 1e6
GRAD_NORM_HEALTHY_THRESHOLD = 10.0
LOSS_STAGNATION_THRESHOLD = 1.0
LOSS_HEALTHY_THRESHOLD = 0.1


def _is_finite(value: Any) -> bool:
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _diagnose_from_history(
    loss_history: Sequence[Any],
    grad_history: Sequence[Any] | None = None,
) -> ConvergenceHealth:
    raise NotImplementedError


def _diagnose_from_final_state(
    train_loss: Any,
    grad_norm: Any,
    val_loss: Any,
) -> ConvergenceHealth:
    raise NotImplementedError


def diagnose_convergence(record: dict[str, Any]) -> ConvergenceHealth:
    status = str(record.get("status", "")).lower()
    if status == "failed":
        return ConvergenceHealth.EXPLODING

    train_loss = record.get("train_loss")
    grad_norm = record.get("grad_norm")

    if train_loss is not None and not _is_finite(train_loss):
        return ConvergenceHealth.EXPLODING
    if grad_norm is not None and not _is_finite(grad_norm):
        return ConvergenceHealth.EXPLODING

    extra_metrics = record.get("extra_metrics")
    if isinstance(extra_metrics, dict):
        loss_history = extra_metrics.get("loss_history")
        grad_history = extra_metrics.get("grad_norm_history")
        if isinstance(loss_history, list) and len(loss_history) >= 5:
            return _diagnose_from_history(loss_history, grad_history)

    return _diagnose_from_final_state(train_loss, grad_norm, record.get("val_loss"))
