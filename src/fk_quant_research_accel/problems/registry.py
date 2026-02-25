"""Problem specification registry."""

from __future__ import annotations

from fk_quant_research_accel.problems.protocol import ProblemSpec

_PROBLEM_REGISTRY: dict[str, ProblemSpec] = {}


def register_problem(spec: ProblemSpec) -> ProblemSpec:
    problem_id = spec.problem_id
    if problem_id in _PROBLEM_REGISTRY:
        raise ValueError(f"Problem spec already registered: {problem_id!r}")
    _PROBLEM_REGISTRY[problem_id] = spec
    return spec


def get_problem_spec(problem_id: str) -> ProblemSpec:
    try:
        return _PROBLEM_REGISTRY[problem_id]
    except KeyError as exc:
        raise ValueError(f"Unknown problem_id: {problem_id!r}") from exc


def list_problem_ids() -> list[str]:
    return sorted(_PROBLEM_REGISTRY.keys())
