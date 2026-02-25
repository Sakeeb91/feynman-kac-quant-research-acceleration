"""Problem specification registry."""

from __future__ import annotations

import difflib

from fk_quant_research_accel.problems.protocol import ProblemSpec

_PROBLEM_REGISTRY: dict[str, ProblemSpec] = {}


def _ensure_builtin_registration() -> None:
    from fk_quant_research_accel.problems.black_scholes import BlackScholesSpec
    from fk_quant_research_accel.problems.harmonic_oscillator import HarmonicOscillatorSpec

    if "black_scholes" not in _PROBLEM_REGISTRY:
        register_problem(BlackScholesSpec())
    if "harmonic_oscillator" not in _PROBLEM_REGISTRY:
        register_problem(HarmonicOscillatorSpec())


def register_problem(spec: ProblemSpec) -> ProblemSpec:
    problem_id = spec.problem_id
    if problem_id in _PROBLEM_REGISTRY:
        raise ValueError(f"Problem spec already registered: {problem_id!r}")
    _PROBLEM_REGISTRY[problem_id] = spec
    return spec


def get_problem_spec(problem_id: str) -> ProblemSpec:
    _ensure_builtin_registration()
    try:
        return _PROBLEM_REGISTRY[problem_id]
    except KeyError as exc:
        valid_ids = sorted(_PROBLEM_REGISTRY)
        message = f"Unknown problem_id: {problem_id!r}."
        if valid_ids:
            message += f" Valid IDs: {', '.join(valid_ids)}."
            nearest = difflib.get_close_matches(problem_id, valid_ids, n=1)
            if nearest:
                message += f" Did you mean '{nearest[0]}'?"
        raise ValueError(message) from exc


def list_problem_ids() -> list[str]:
    _ensure_builtin_registration()
    return sorted(_PROBLEM_REGISTRY.keys())
