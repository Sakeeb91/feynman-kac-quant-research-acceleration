"""Built-in Black-Scholes problem specification."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem


class BlackScholesParams(ProblemParams):
    dim: int = Field(gt=0)
    volatility: float = Field(gt=0.0, le=5.0)
    correlation: float | list[list[float]]
    option_type: str = "call"


class BlackScholesSpec(BaseProblemSpec):
    @property
    def problem_id(self) -> str:
        return "black_scholes"

    @property
    def param_schema(self) -> type[ProblemParams]:
        return BlackScholesParams

    def generate_scenarios(
        self,
        grid_config: dict[str, Any],
        model_configs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        del grid_config, model_configs
        return []


register_problem(BlackScholesSpec())
