"""Pure constraint validators used by pre-flight checks."""

from __future__ import annotations


def is_positive_semidefinite(matrix: list[list[float]], tol: float = 1e-10) -> bool:
    del matrix, tol
    return False


def validate_correlation_matrix(
    matrix: list[list[float]],
    expected_dim: int | None = None,
) -> list[str]:
    del matrix, expected_dim
    return []


def validate_volatility_range(
    volatilities: list[float],
    low: float = 0.0,
    high: float = 5.0,
) -> list[str]:
    del volatilities, low, high
    return []


def validate_dimension_option_compatibility(dim: int, option_type: str) -> list[str]:
    del dim, option_type
    return []


def validate_scalar_correlations(correlations: list[float]) -> list[str]:
    del correlations
    return []
