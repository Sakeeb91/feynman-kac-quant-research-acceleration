"""Scorer registry and factory helpers."""

from __future__ import annotations

import importlib
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
    if config.custom_scorer:
        return _import_custom_scorer(config.custom_scorer)

    # Ensure decorators in scorers.py run before registry lookup.
    import fk_quant_research_accel.scoring.scorers

    if config.strategy == ScoringStrategy.LOSS_BASED:
        from fk_quant_research_accel.scoring.scorers import score_loss_based

        def configured_loss_scorer(record: dict[str, Any]) -> float:
            return score_loss_based(record, grad_norm_weight=config.grad_norm_weight)

        return configured_loss_scorer

    strategy = config.strategy
    try:
        return _SCORER_REGISTRY[strategy]
    except KeyError as exc:
        raise ValueError(f"Unknown scoring strategy: {strategy!r}") from exc


def _import_custom_scorer(dotted_path: str) -> ScorerFn:
    if "." not in dotted_path:
        raise ValueError(
            f"Custom scorer path must be dotted module path like 'pkg.module.fn': {dotted_path!r}"
        )
    module_path, attr_name = dotted_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # pragma: no cover - exact import error type depends on module
        raise ValueError(f"Failed to import custom scorer module {module_path!r}: {exc}") from exc

    try:
        scorer = getattr(module, attr_name)
    except AttributeError as exc:
        raise ValueError(
            f"Custom scorer attribute {attr_name!r} not found in module {module_path!r}"
        ) from exc

    if not callable(scorer):
        raise ValueError(f"Custom scorer {dotted_path!r} is not callable")

    return scorer
