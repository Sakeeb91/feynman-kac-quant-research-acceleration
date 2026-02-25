"""Scenario alignment and two-run comparison helpers."""

from __future__ import annotations

import math


def delta_abs(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    try:
        lhs = float(a)
        rhs = float(b)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(lhs) or not math.isfinite(rhs):
        return None
    return lhs - rhs


def delta_pct(a: float | None, b: float | None) -> float | None:
    absolute = delta_abs(a, b)
    if absolute is None or b is None:
        return None
    base = float(b)
    if base == 0.0:
        return None
    return (absolute / abs(base)) * 100.0
