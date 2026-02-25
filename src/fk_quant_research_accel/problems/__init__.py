"""Problem-type extensibility module."""

from .protocol import BaseProblemSpec, ProblemParams, ProblemSpec
from .registry import get_problem_spec, list_problem_ids, register_problem

__all__ = [
    "ProblemSpec",
    "BaseProblemSpec",
    "ProblemParams",
    "get_problem_spec",
    "register_problem",
    "list_problem_ids",
]
