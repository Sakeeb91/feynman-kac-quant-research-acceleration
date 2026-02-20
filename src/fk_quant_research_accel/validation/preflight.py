"""Manifest pre-flight validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from itertools import product

from fk_quant_research_accel.models.experiment import ExperimentManifest
from fk_quant_research_accel.validation.constraints import (
    validate_correlation_matrix,
    validate_dimension_option_compatibility,
    validate_scalar_correlations,
    validate_volatility_range,
)


@dataclass(frozen=True)
class PreflightError:
    field: str
    value: Any
    message: str


def validate_manifest(manifest: ExperimentManifest) -> list[PreflightError]:
    errors: list[PreflightError] = []
    grid = manifest.scenario_grid

    for message in validate_volatility_range(grid.volatilities):
        errors.append(
            PreflightError(
                field="scenario_grid.volatilities",
                value=grid.volatilities,
                message=message,
            )
        )

    first = grid.correlations[0]
    if isinstance(first, list):
        matrix = grid.correlations
        for message in validate_correlation_matrix(matrix):
            errors.append(
                PreflightError(
                    field="scenario_grid.correlations.matrix",
                    value=matrix,
                    message=message,
                )
            )
        for dim in grid.dimensions:
            for message in validate_correlation_matrix(matrix, expected_dim=dim):
                errors.append(
                    PreflightError(
                        field="scenario_grid.correlations.matrix",
                        value={"expected_dim": dim, "matrix": matrix},
                        message=message,
                    )
                )
    else:
        scalars = grid.correlations
        for message in validate_scalar_correlations(scalars):
            errors.append(
                PreflightError(
                    field="scenario_grid.correlations.scalar",
                    value=scalars,
                    message=message,
                )
            )

    for dim, option_type in product(grid.dimensions, grid.option_types):
        option_value = getattr(option_type, "value", option_type)
        for message in validate_dimension_option_compatibility(dim=dim, option_type=option_value):
            errors.append(
                PreflightError(
                    field="scenario_grid.option_types",
                    value={"dim": dim, "option_type": option_value},
                    message=message,
                )
            )

    return errors
