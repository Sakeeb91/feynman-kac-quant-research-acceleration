from __future__ import annotations

from pydantic import BaseModel

from fk_quant_research_accel.problems.protocol import ProblemParams


def test_problem_params_is_pydantic_model() -> None:
    assert issubclass(ProblemParams, BaseModel)
