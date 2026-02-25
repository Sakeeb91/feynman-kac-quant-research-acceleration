"""Scenario alignment and two-run comparison helpers."""

from __future__ import annotations

import json
import math
from typing import Any


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


def _normalize_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, sort_keys=True)
    return value


def _scenario_key(scenario_json: str) -> tuple[Any, Any, Any, Any, Any]:
    payload = json.loads(scenario_json)
    return (
        payload.get("dim"),
        payload.get("volatility"),
        _normalize_value(payload.get("correlation")),
        payload.get("option_type"),
        _normalize_value(payload.get("model_config")),
    )


def align_scenarios(
    scenarios_a: list[dict[str, Any]],
    scenarios_b: list[dict[str, Any]],
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, Any]], list[dict[str, Any]]]:
    map_a = {_scenario_key(str(row.get("scenario_json", "{}"))): row for row in scenarios_a}
    map_b = {_scenario_key(str(row.get("scenario_json", "{}"))): row for row in scenarios_b}

    matched: list[tuple[dict[str, Any], dict[str, Any]]] = []
    only_a: list[dict[str, Any]] = []
    only_b: list[dict[str, Any]] = []

    for key in sorted(map_a.keys(), key=str):
        if key in map_b:
            matched.append((map_a[key], map_b[key]))
        else:
            only_a.append(map_a[key])
    for key in sorted(map_b.keys(), key=str):
        if key not in map_a:
            only_b.append(map_b[key])
    return matched, only_a, only_b
