"""Scoring registry and built-in scoring strategies."""

from .pareto import assign_pareto_scores
from .registry import ScorerFn, get_scorer

__all__ = ["get_scorer", "ScorerFn", "assign_pareto_scores"]
