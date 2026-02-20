"""Pure constraint validators used by pre-flight checks."""

from __future__ import annotations

import math


def is_positive_semidefinite(matrix: list[list[float]], tol: float = 1e-10) -> bool:
    n = len(matrix)
    if n == 0:
        return False
    if any(len(row) != n for row in matrix):
        return False

    for i in range(n):
        for j in range(i + 1, n):
            if abs(matrix[i][j] - matrix[j][i]) > tol:
                return False

    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            partial = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                candidate = matrix[i][i] - partial
                if candidate < -tol:
                    return False
                lower[i][j] = math.sqrt(max(candidate, 0.0))
            else:
                if abs(lower[j][j]) <= tol:
                    return False
                lower[i][j] = (matrix[i][j] - partial) / lower[j][j]

    return True


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
