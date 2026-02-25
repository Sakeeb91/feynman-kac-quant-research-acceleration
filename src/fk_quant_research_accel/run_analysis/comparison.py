"""Scenario alignment and two-run comparison helpers."""

from __future__ import annotations

import json
import math
from typing import Any

from fk_quant_research_accel.store.metadata import MetadataStore


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


def _extract_metrics(result_json_str: str | None) -> dict[str, Any]:
    if not result_json_str:
        return {
            "score": None,
            "train_loss": None,
            "grad_norm": None,
            "progress": None,
            "convergence_health": None,
            "status": None,
        }
    try:
        payload = json.loads(result_json_str)
    except json.JSONDecodeError:
        return {
            "score": None,
            "train_loss": None,
            "grad_norm": None,
            "progress": None,
            "convergence_health": None,
            "status": None,
        }
    return {
        "score": payload.get("score"),
        "train_loss": payload.get("train_loss"),
        "grad_norm": payload.get("grad_norm"),
        "progress": payload.get("progress"),
        "convergence_health": payload.get("convergence_health"),
        "status": payload.get("status"),
    }


def compute_comparison(
    store: MetadataStore,
    run_a_id: str,
    run_b_id: str,
    include_all_status: bool = False,
) -> dict[str, Any]:
    scenarios_a = store.get_scenario_runs(run_a_id)
    scenarios_b = store.get_scenario_runs(run_b_id)
    if not include_all_status:
        scenarios_a = [row for row in scenarios_a if row.get("status") == "completed"]
        scenarios_b = [row for row in scenarios_b if row.get("status") == "completed"]

    matched_pairs, only_a, only_b = align_scenarios(scenarios_a, scenarios_b)
    matched: list[dict[str, Any]] = []
    for row_a, row_b in matched_pairs:
        metrics_a = _extract_metrics(row_a.get("result_json"))
        metrics_b = _extract_metrics(row_b.get("result_json"))
        matched.append(
            {
                "scenario": json.loads(str(row_a.get("scenario_json", "{}"))),
                "run_a_score": metrics_a["score"],
                "run_b_score": metrics_b["score"],
                "delta_abs_score": delta_abs(metrics_a["score"], metrics_b["score"]),
                "delta_pct_score": delta_pct(metrics_a["score"], metrics_b["score"]),
                "run_a_train_loss": metrics_a["train_loss"],
                "run_b_train_loss": metrics_b["train_loss"],
                "delta_abs_train_loss": delta_abs(metrics_a["train_loss"], metrics_b["train_loss"]),
                "delta_pct_train_loss": delta_pct(metrics_a["train_loss"], metrics_b["train_loss"]),
                "run_a_grad_norm": metrics_a["grad_norm"],
                "run_b_grad_norm": metrics_b["grad_norm"],
                "delta_abs_grad_norm": delta_abs(metrics_a["grad_norm"], metrics_b["grad_norm"]),
                "delta_pct_grad_norm": delta_pct(metrics_a["grad_norm"], metrics_b["grad_norm"]),
                "run_a_progress": metrics_a["progress"],
                "run_b_progress": metrics_b["progress"],
                "delta_abs_progress": delta_abs(metrics_a["progress"], metrics_b["progress"]),
                "delta_pct_progress": delta_pct(metrics_a["progress"], metrics_b["progress"]),
                "status_mismatch": metrics_a["status"] != metrics_b["status"],
                "run_a_status": metrics_a["status"],
                "run_b_status": metrics_b["status"],
            }
        )

    return {
        "matched": matched,
        "only_a": only_a,
        "only_b": only_b,
        "summary": {
            "matched_count": len(matched),
            "only_a_count": len(only_a),
            "only_b_count": len(only_b),
            "a_wins": 0,
            "b_wins": 0,
        },
    }
