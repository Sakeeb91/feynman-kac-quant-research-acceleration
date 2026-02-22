"""Scorer registry and factory helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fk_quant_research_accel.models.experiment import ScoringConfig
from fk_quant_research_accel.models.enums import ScoringStrategy

ScorerFn = Callable[[dict[str, Any]], float]

_SCORER_REGISTRY: dict[ScoringStrategy, ScorerFn] = {}


def register_scorer(strategy: ScoringStrategy) -> Callable[[ScorerFn], ScorerFn]:
    def decorator(func: ScorerFn) -> ScorerFn:
        _SCORER_REGISTRY[strategy] = func
        return func

    return decorator


def get_scorer(config: ScoringConfig) -> ScorerFn:
    strategy = config.strategy
    try:
        return _SCORER_REGISTRY[strategy]
    except KeyError as exc:
        raise ValueError(f"Unknown scoring strategy: {strategy!r}") from exc


def _import_custom_scorer(dotted_path: str) -> ScorerFn:
    raise ValueError(f"Invalid custom scorer path: {dotted_path!r}")
