"""Pareto sorting for multi-objective ranking."""

from __future__ import annotations

import math
from typing import Any


def dominates(a: list[float], b: list[float]) -> bool:
    if len(a) != len(b):
        return False
    return all(x <= y for x, y in zip(a, b, strict=True)) and any(
        x < y for x, y in zip(a, b, strict=True)
    )


def non_dominated_sort(
    records: list[dict[str, Any]],
    objectives: list[str],
) -> list[list[int]]:
    valid_indices: list[int] = []
    invalid_indices: list[int] = []
    objective_vectors: dict[int, list[float]] = {}

    for index, record in enumerate(records):
        vector: list[float] = []
        valid = True
        for objective in objectives:
            raw_value = record.get(objective)
            if raw_value is None:
                valid = False
                break
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                valid = False
                break
            if not math.isfinite(value):
                valid = False
                break
            vector.append(value)

        if not valid:
            invalid_indices.append(index)
            continue

        valid_indices.append(index)
        objective_vectors[index] = vector

    if not valid_indices:
        return [invalid_indices] if invalid_indices else []

    domination_counts: dict[int, int] = {index: 0 for index in valid_indices}
    dominated_sets: dict[int, list[int]] = {index: [] for index in valid_indices}

    for i, left in enumerate(valid_indices):
        for right in valid_indices[i + 1 :]:
            left_vector = objective_vectors[left]
            right_vector = objective_vectors[right]

            if dominates(left_vector, right_vector):
                dominated_sets[left].append(right)
                domination_counts[right] += 1
            elif dominates(right_vector, left_vector):
                dominated_sets[right].append(left)
                domination_counts[left] += 1

    fronts: list[list[int]] = [
        [index for index in valid_indices if domination_counts[index] == 0]
    ]

    front_idx = 0
    while front_idx < len(fronts) and fronts[front_idx]:
        next_front: list[int] = []
        for index in fronts[front_idx]:
            for dominated in dominated_sets[index]:
                domination_counts[dominated] -= 1
                if domination_counts[dominated] == 0:
                    next_front.append(dominated)
        if next_front:
            fronts.append(next_front)
        front_idx += 1

    if invalid_indices:
        fronts.append(invalid_indices)

    return fronts


def assign_pareto_scores(
    records: list[dict[str, Any]],
    objectives: list[str] | None = None,
) -> list[float]:
    if not records:
        return []

    objective_fields = objectives or ["train_loss", "grad_norm"]
    fronts = non_dominated_sort(records, objective_fields)
    scores = [float("inf")] * len(records)

    for front_index, front in enumerate(fronts):
        if not front:
            continue

        def _secondary_rank(index: int) -> float:
            total = 0.0
            for objective in objective_fields:
                raw_value = records[index].get(objective)
                if raw_value is None:
                    return float("inf")
                value = float(raw_value)
                if not math.isfinite(value):
                    return float("inf")
                total += value
            return total

        ordered_front = sorted(front, key=_secondary_rank)
        denominator = max(1, len(ordered_front))
        for position, index in enumerate(ordered_front):
            scores[index] = float(front_index) + (position / denominator)

    return scores
