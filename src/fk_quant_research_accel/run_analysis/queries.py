"""Read-model queries for run analysis CLI commands."""

from __future__ import annotations

import statistics
from typing import Any

from fk_quant_research_accel.store.metadata import MetadataStore


def list_runs_with_metrics(
    store: MetadataStore,
    **filter_kwargs: Any,
) -> list[dict[str, Any]]:
    runs = store.list_batch_runs(**filter_kwargs)
    enriched: list[dict[str, Any]] = []
    for run in runs:
        row = dict(run)
        scenario_rows = store.get_scenario_runs(str(row["batch_run_id"]))
        completed_scores = [
            float(scenario["score"])
            for scenario in scenario_rows
            if scenario.get("status") == "completed" and scenario.get("score") is not None
        ]
        row["median_score"] = (
            statistics.median(completed_scores) if completed_scores else None
        )
        enriched.append(row)
    return enriched
