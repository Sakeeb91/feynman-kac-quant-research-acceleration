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
    errors: list[str] = []
    n = len(matrix)

    if n == 0:
        return ["Correlation matrix cannot be empty."]

    if any(len(row) != n for row in matrix):
        errors.append("Correlation matrix must be square.")
        return errors

    if expected_dim is not None and n != expected_dim:
        errors.append(
            f"Correlation matrix dimension mismatch: expected {expected_dim}, got {n}."
        )

    for idx in range(n):
        if abs(matrix[idx][idx] - 1.0) > 1e-10:
            errors.append(f"Correlation matrix diagonal must be 1.0 at [{idx},{idx}].")

    for i in range(n):
        for j in range(i + 1, n):
            value = matrix[i][j]
            if value < -1.0 or value > 1.0:
                errors.append(
                    f"Correlation matrix entry [{i},{j}]={value} outside [-1.0, 1.0]."
                )

    if not is_positive_semidefinite(matrix):
        errors.append("Correlation matrix must be positive semi-definite.")

    return errors


def validate_volatility_range(
    volatilities: list[float],
    low: float = 0.0,
    high: float = 5.0,
) -> list[str]:
    errors: list[str] = []
    for idx, volatility in enumerate(volatilities):
        if volatility <= low or volatility > high:
            errors.append(
                f"Volatility at index {idx}={volatility} must be in ({low}, {high}]."
            )
    return errors


def validate_dimension_option_compatibility(dim: int, option_type: str) -> list[str]:
    normalized = option_type.strip().lower()
    basket_like = {"basket", "basket_call", "basket_put"}
    if normalized in basket_like and dim < 2:
        return [
            f"Option type '{option_type}' requires dim >= 2, got dim={dim}.",
        ]
    return []


def validate_scalar_correlations(correlations: list[float]) -> list[str]:
    errors: list[str] = []
    for idx, correlation in enumerate(correlations):
        if correlation < -1.0 or correlation > 1.0:
            errors.append(
                f"Scalar correlation at index {idx}={correlation} outside [-1.0, 1.0]."
            )
    return errors
