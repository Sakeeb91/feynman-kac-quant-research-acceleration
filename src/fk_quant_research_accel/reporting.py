"""Reporting helpers for experiment outputs."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def compute_score(record: dict[str, Any]) -> float:
    """
    Lower is better. Penalize missing values and unstable gradients.
    """
    train_loss = record.get("train_loss")
    grad_norm = record.get("grad_norm")
    status = record.get("status")

    if status != "completed":
        return float("inf")
    if train_loss is None:
        return float("inf")

    grad_penalty = 0.0 if grad_norm is None else abs(float(grad_norm)) * 0.01
    return float(train_loss) + grad_penalty


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
