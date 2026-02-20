"""Manifest pre-flight validation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any, cast

from fk_quant_research_accel.models.experiment import ExperimentManifest
from fk_quant_research_accel.validation.constraints import (
    validate_correlation_matrix,
    validate_dimension_option_compatibility,
    validate_scalar_correlations,
    validate_volatility_range,
)

__all__ = ["PreflightError", "validate_manifest"]


@dataclass(frozen=True)
class PreflightError:
    field: str
    value: Any
    message: str


def _append_messages(
    errors: list[PreflightError],
    field: str,
    value: Any,
    messages: list[str],
) -> None:
    for message in messages:
        errors.append(PreflightError(field=field, value=value, message=message))


def _coerce_option_type(option_type: Any) -> str:
    return cast(str, getattr(option_type, "value", option_type))


def validate_manifest(manifest: ExperimentManifest) -> list[PreflightError]:
    errors: list[PreflightError] = []
    grid = manifest.scenario_grid

    _append_messages(
        errors=errors,
        field="scenario_grid.volatilities",
        value=grid.volatilities,
        messages=validate_volatility_range(grid.volatilities),
    )

    first = grid.correlations[0]
    if isinstance(first, list):
        matrix = cast(list[list[float]], grid.correlations)
        _append_messages(
            errors=errors,
            field="scenario_grid.correlations.matrix",
            value=matrix,
            messages=validate_correlation_matrix(matrix),
        )
        for dim in grid.dimensions:
            dim_messages = [
                message
                for message in validate_correlation_matrix(matrix, expected_dim=dim)
                if "dimension mismatch" in message.lower()
            ]
            _append_messages(
                errors=errors,
                field="scenario_grid.correlations.matrix",
                value={"expected_dim": dim, "matrix": matrix},
                messages=dim_messages,
            )
    else:
        scalars = cast(list[float], grid.correlations)
        _append_messages(
            errors=errors,
            field="scenario_grid.correlations.scalar",
            value=scalars,
            messages=validate_scalar_correlations(scalars),
        )

    for dim, option_type in product(grid.dimensions, grid.option_types):
        option_value = _coerce_option_type(option_type)
        for message in validate_dimension_option_compatibility(dim=dim, option_type=option_value):
            errors.append(
                PreflightError(
                    field="scenario_grid.option_types",
                    value={"dim": dim, "option_type": option_value},
                    message=message,
                )
            )

    return errors
