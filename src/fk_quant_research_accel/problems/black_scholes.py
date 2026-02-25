"""Built-in Black-Scholes problem specification."""

from __future__ import annotations

import itertools
from typing import Any
from typing import cast

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
        dimensions = list(grid_config.get("dimensions", []))
        volatilities = list(grid_config.get("volatilities", []))
        correlations = grid_config.get("correlations", [])
        option_types = list(grid_config.get("option_types", ["call"]))

        if correlations and isinstance(correlations[0], list):
            correlation_axis: tuple[float | list[list[float]], ...] = (
                cast(list[list[float]], correlations),
            )
        else:
            correlation_axis = tuple(cast(list[float], correlations))

        scenarios: list[dict[str, Any]] = []
        for dim, volatility, correlation, option_type, model_config in itertools.product(
            dimensions,
            volatilities,
            correlation_axis,
            option_types,
            model_configs,
        ):
            scenarios.append(
                {
                    "dim": dim,
                    "volatility": volatility,
                    "correlation": correlation,
                    "option_type": option_type,
                    "model_config": dict(model_config),
                }
            )
        return scenarios


register_problem(BlackScholesSpec())
