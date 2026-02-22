"""Reporting helpers for experiment outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from fk_quant_research_accel.models.experiment import ScoringConfig
from fk_quant_research_accel.scoring.registry import get_scorer


def compute_score(
    record: dict[str, Any],
    scoring_config: ScoringConfig | None = None,
) -> float:
    """
    Lower is better. Penalize missing values and unstable gradients.
    """
    config = scoring_config or ScoringConfig()
    scorer = get_scorer(config)
    return scorer(record)


def write_csv(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if not records:
        output.write_text("", encoding="utf-8")
        return output

    fieldnames = list(records[0].keys())
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return output
