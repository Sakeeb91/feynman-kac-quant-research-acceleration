"""Built-in Black-Scholes problem specification."""

from __future__ import annotations

import itertools
from typing import Any
from typing import cast

from pydantic import Field

from fk_quant_research_accel.problems.protocol import BaseProblemSpec, ProblemParams
from fk_quant_research_accel.problems.registry import register_problem
from fk_quant_research_accel.validation.constraints import (
    validate_correlation_matrix,
    validate_dimension_option_compatibility,
    validate_scalar_correlations,
    validate_volatility_range,
)


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

    def validate(self, params: dict[str, Any]) -> list[str]:
        errors = super().validate(params)

        dim = params.get("dim")
        volatility = params.get("volatility")
        correlation = params.get("correlation")
        option_type = str(params.get("option_type", "call"))

        if isinstance(volatility, (int, float)):
            errors.extend(validate_volatility_range([float(volatility)]))

        if isinstance(correlation, list):
            if correlation and isinstance(correlation[0], list):
                matrix = cast(list[list[float]], correlation)
                errors.extend(validate_correlation_matrix(matrix, expected_dim=dim if isinstance(dim, int) else None))
            else:
                scalar_values = [float(value) for value in correlation if isinstance(value, (int, float))]
                errors.extend(validate_scalar_correlations(scalar_values))
        elif isinstance(correlation, (int, float)):
            errors.extend(validate_scalar_correlations([float(correlation)]))

        if isinstance(dim, int):
            errors.extend(validate_dimension_option_compatibility(dim=dim, option_type=option_type))

        return errors


register_problem(BlackScholesSpec())
