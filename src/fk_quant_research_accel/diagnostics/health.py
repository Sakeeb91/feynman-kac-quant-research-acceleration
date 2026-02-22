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
    values: list[float] = []
    for value in loss_history:
        if not _is_finite(value):
            return ConvergenceHealth.EXPLODING
        values.append(float(value))

    if len(values) < 5:
        return ConvergenceHealth.HEALTHY

    if grad_history:
        for grad in grad_history:
            if not _is_finite(grad):
                return ConvergenceHealth.EXPLODING
            if abs(float(grad)) > GRAD_NORM_EXPLODING_THRESHOLD:
                return ConvergenceHealth.EXPLODING

    spread = max(values) - min(values)
    if spread <= 1e-6:
        return ConvergenceHealth.STAGNATING

    first = values[0]
    last = values[-1]
    if abs(first) > 0 and abs(last - first) / abs(first) < 0.01:
        return ConvergenceHealth.STAGNATING

    downward_steps = sum(1 for left, right in zip(values, values[1:], strict=True) if right <= left)
    if last <= first and downward_steps >= int(0.6 * (len(values) - 1)):
        return ConvergenceHealth.HEALTHY

    average = mean(values)
    if len(values) >= 2 and average != 0.0:
        coefficient_of_variation = abs(stdev(values) / average)
        diffs = [right - left for left, right in zip(values, values[1:], strict=True)]
        signs = [1 if diff > 0 else -1 for diff in diffs if diff != 0]
        direction_changes = sum(
            1 for prev, curr in zip(signs, signs[1:], strict=True) if prev != curr
        )
        oscillation_threshold = max(2, len(values) // 4)
        if coefficient_of_variation > 0.8 and direction_changes >= oscillation_threshold:
            return ConvergenceHealth.OSCILLATING

    return ConvergenceHealth.HEALTHY


def _diagnose_from_final_state(
    train_loss: Any,
    grad_norm: Any,
    val_loss: Any,
) -> ConvergenceHealth:
    train_loss_value = float(train_loss) if _is_finite(train_loss) else None
    grad_norm_value = abs(float(grad_norm)) if _is_finite(grad_norm) else None
    val_loss_value = float(val_loss) if _is_finite(val_loss) else None

    if grad_norm_value is not None and grad_norm_value > GRAD_NORM_EXPLODING_THRESHOLD:
        return ConvergenceHealth.EXPLODING

    if (
        train_loss_value is not None
        and train_loss_value >= LOSS_STAGNATION_THRESHOLD
        and grad_norm_value is not None
        and grad_norm_value < 1e-6
    ):
        return ConvergenceHealth.STAGNATING

    if (
        train_loss_value is not None
        and val_loss_value is not None
        and train_loss_value > 0.0
        and (val_loss_value / train_loss_value) > 3.0
    ):
        return ConvergenceHealth.OSCILLATING

    if grad_norm_value is not None and grad_norm_value > GRAD_NORM_HEALTHY_THRESHOLD:
        return ConvergenceHealth.OSCILLATING

    if train_loss_value is not None and train_loss_value <= LOSS_HEALTHY_THRESHOLD:
        return ConvergenceHealth.HEALTHY

    return ConvergenceHealth.HEALTHY


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
